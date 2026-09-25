"""Generate reproducible temperature events, or send them as direct HTTP batches."""

import argparse
import http.client
import json
import math
import os
import platform
import subprocess
import sys
import time
import urllib.error
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from events import (
    SIMULATOR_VERSION,
    Scenario,
    TemperatureProfile,
    batches,
    encode_batch,
    integer,
)
from send_batch import post_batch, validate_target


def run_scenario(
    scenario: Scenario,
    batch_size: int,
    *,
    send=None,
    emit=None,
    paced: bool = True,
    clock=time.monotonic,
    sleep=time.sleep,
) -> dict:
    """Bound memory to one batch; stop on uncertainty without automatic retries."""
    integer(batch_size, "batch_size", 1, 500)
    started = clock()
    summary = {
        "planned": scenario.count,
        "generated": 0,
        "sent": 0,
        "emitted": 0,
        "counts": {"accepted": 0, "duplicate": 0, "rejected": 0},
        "rejection_reasons": {},
        "unconfirmed": 0,
        "unsent": scenario.count,
        "failures": 0,
        "max_schedule_lag_seconds": 0.0,
        "cancelled": False,
    }
    try:
        for batch in batches(scenario, batch_size):
            events = batch["events"]
            size = len(events)
            summary["generated"] += size
            body = encode_batch(batch)
            if send is None:
                if emit is not None:
                    emit(body)
                summary["emitted"] += size
                continue
            if paced:
                deadline = (
                    started + (summary["generated"] - 1) * scenario.interval_ms / 1000
                )
                sleep(max(0.0, deadline - clock()))
                summary["max_schedule_lag_seconds"] = max(
                    summary["max_schedule_lag_seconds"], clock() - deadline
                )
            summary["sent"] += size
            summary["unconfirmed"] += size
            _, outcomes = send(body, events)
            for outcome in outcomes:
                category, _, reason = outcome.partition(":")
                summary["counts"][category] += 1
                if category == "rejected":
                    reasons = summary["rejection_reasons"]
                    reasons[reason] = reasons.get(reason, 0) + 1
            summary["unconfirmed"] -= size
    except KeyboardInterrupt:
        summary["cancelled"] = True
    except (
        urllib.error.URLError,
        http.client.HTTPException,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
    ):
        summary["failures"] += 1
        summary["error"] = "Transport/output failure; replay unchanged configuration"
    summary["unsent"] = scenario.count - summary["sent"]
    elapsed = max(0.0, clock() - started)
    summary["duration_seconds"] = round(elapsed, 6)
    summary["sent_events_per_second"] = (
        round(summary["sent"] / elapsed, 3) if elapsed else 0.0
    )
    summary["max_schedule_lag_seconds"] = round(summary["max_schedule_lag_seconds"], 6)
    return summary


def source_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", "simulator"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        return result.stdout.strip() + ("-dirty" if status.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--run-id", required=True, help="New ID for an independent run")
    parser.add_argument("--boot-id", help="Optional explicit initial boot ID")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval-ms", type=int, default=1000)
    parser.add_argument("--start-time", default="2026-01-01T00:00:00Z")
    parser.add_argument(
        "--reboot-every", type=int, default=0, help="Events per boot; 0=off"
    )
    parser.add_argument(
        "--profile", choices=("constant", "ramp", "sine"), default="constant"
    )
    parser.add_argument("--temperature", type=float, default=25.0, help="Base Celsius")
    parser.add_argument(
        "--step", type=float, default=0.1, help="Ramp Celsius per sample"
    )
    parser.add_argument(
        "--amplitude", type=float, default=5.0, help="Sine Celsius amplitude"
    )
    parser.add_argument("--period", type=int, default=60, help="Sine period in samples")
    parser.add_argument(
        "--noise", type=float, default=0.0, help="Uniform noise +/- Celsius"
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--mode", choices=("generate", "http"), default="generate")
    parser.add_argument(
        "--fast", action="store_true", help="Skip HTTP wall-clock pacing"
    )
    parser.add_argument("--api-base-url", default=os.environ.get("API_BASE_URL"))
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="HTTP timeout seconds"
    )
    args = parser.parse_args()
    base_url = args.api_base_url or "http://127.0.0.1:8000/api"
    token = os.environ.get("GATEWAY_API_KEY", "")
    try:
        scenario = Scenario(
            device_id=args.device_id,
            run_id=args.run_id,
            boot_id=args.boot_id,
            seed=args.seed,
            count=args.count,
            interval_ms=args.interval_ms,
            start_time=datetime.fromisoformat(args.start_time),
            reboot_every=args.reboot_every,
            profile=TemperatureProfile(
                kind=args.profile,
                temperature=args.temperature,
                step=args.step,
                amplitude=args.amplitude,
                period=args.period,
                noise=args.noise,
            ),
        )
        integer(args.batch_size, "batch_size", 1, 500)
        if not math.isfinite(args.timeout) or not 0 < args.timeout <= 300:
            raise ValueError("timeout must be finite and between 0 (exclusive) and 300")
        if args.mode == "http":
            validate_target(base_url, token)
    except (ValueError, OverflowError) as error:
        parser.error(str(error))

    def send(body, events):
        return post_batch(base_url, token, body, events, args.timeout)

    summary = run_scenario(
        scenario,
        args.batch_size,
        send=send if args.mode == "http" else None,
        emit=lambda body: print(body.decode("utf-8"), flush=True),
        paced=not args.fast,
    )
    config = asdict(scenario)
    config["start_time"] = scenario.start_time.isoformat()
    summary.update(
        mode=args.mode,
        simulator_version=SIMULATOR_VERSION,
        python_version=platform.python_version(),
        source_revision=source_revision(),
        configuration=config,
        batch_size=args.batch_size,
        paced=args.mode == "http" and not args.fast,
        timeout_seconds=args.timeout,
        target=base_url if args.mode == "http" else None,
    )
    print(
        json.dumps(summary), file=sys.stderr if args.mode == "generate" else sys.stdout
    )
    failed = (
        summary["failures"] or summary["unconfirmed"] or summary["counts"]["rejected"]
    )
    raise SystemExit(130 if summary["cancelled"] else int(bool(failed)))


if __name__ == "__main__":
    main()
