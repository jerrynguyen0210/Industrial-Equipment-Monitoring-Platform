"""Export and exercise bounded telemetry-batch.v1 edge cases over HTTP."""

import argparse
import copy
import http.client
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulator.send_batch import (  # noqa: E402
    NoRedirect,
    classify_response,
    validate_target,
)

CATALOG = Path(__file__).parent / "fixtures/telemetry-scenarios.json"


def load_scenarios(
    run_id: str, device_id: str = "device-demo-001", names: list[str] | None = None
) -> list[dict]:
    """Expand declarative overrides without consulting the backend or wall clock."""
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]{0,47}", run_id):
        raise ValueError("Run ID must be 1-48 ASCII letters, digits or hyphens")
    if not device_id or len(device_id) > 128 or "\0" in device_id:
        raise ValueError("Device ID must be 1-128 characters without NUL")
    unknown_device = f"qa-unknown-{run_id}"
    if device_id == unknown_device:
        raise ValueError("Registered and unknown device IDs must differ")
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    scenarios = catalog["scenarios"]
    available = {scenario["name"] for scenario in scenarios}
    if names and (set(names) - available):
        raise ValueError(
            "Unknown scenario: " + ", ".join(sorted(set(names) - available))
        )
    expanded = []
    for scenario in scenarios:
        if names and scenario["name"] not in names:
            continue
        scenario = copy.deepcopy(scenario)
        for step in scenario["steps"]:
            events = []
            for overrides in step.pop("events"):
                event = copy.deepcopy(catalog["base_event"]) | overrides
                event["device_id"] = (
                    unknown_device
                    if event["device_id"] == "$unknown_device"
                    else device_id
                )
                event["boot_id"] = f"qa-{run_id}-{scenario['name']}"
                events.append(event)
            step["batch"] = {"schema_version": 1, "events": events}
        expanded.append(scenario)
    return expanded


def encode_batch(batch: dict) -> bytes:
    return (json.dumps(batch, indent=2, allow_nan=False) + "\n").encode("utf-8")


def export_scenarios(scenarios: list[dict], directory: Path, run_id: str) -> None:
    # A new directory preserves evidence from prior runs, including failed ones.
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"contract": "telemetry-batch.v1", "run_id": run_id, "scenarios": []}
    for scenario in scenarios:
        exported = {key: value for key, value in scenario.items() if key != "steps"}
        exported["steps"] = []
        for index, step in enumerate(scenario["steps"], 1):
            filename = f"{scenario['name']}-{index:02}-{step['name']}.json"
            (directory / filename).write_bytes(encode_batch(step["batch"]))
            exported["steps"].append(
                {"fixture": filename, "http_status": 200, "expected": step["expected"]}
            )
        manifest["scenarios"].append(exported)
    (directory / "expected.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def run_scenarios(
    scenarios: list[dict], base_url: str, token: str, timeout: float
) -> list[dict]:
    reports = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for scenario in scenarios:
        report = {"scenario": scenario["name"], "passed": True, "steps": []}
        for step in scenario["steps"]:
            result = {"step": step["name"], "expected": step["expected"]}
            request = urllib.request.Request(
                base_url.rstrip("/") + "/v1/telemetry/batches",
                data=encode_batch(step["batch"]),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with opener.open(request, timeout=timeout) as response:
                    result["http_status"] = response.status
                    if response.status != 200:
                        raise ValueError("Unexpected HTTP status")
                    payload = json.load(response)
                result["actual"] = classify_response(step["batch"]["events"], payload)
                result["batch_id"] = payload["batch_id"]
                result["passed"] = result["actual"] == step["expected"]
            except urllib.error.HTTPError as error:
                result.update(
                    http_status=error.code, passed=False, error="HTTP failure"
                )
                error.close()
            except (OSError, http.client.HTTPException, ValueError, TypeError):
                # Do not echo credentials, response bodies or exception URLs.
                result.update(
                    passed=False, error="Transport or response contract failure"
                )
            report["steps"].append(result)
            if not result["passed"]:
                report["passed"] = False
                report["skipped_steps"] = len(scenario["steps"]) - len(report["steps"])
                break  # Later steps require the earlier commit to be confirmed.
        reports.append(report)
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true", help="List cases without sending"
    )
    parser.add_argument("--scenario", action="append", help="Select a case; repeatable")
    parser.add_argument("--run-id", default=None, help="Fresh identity namespace")
    parser.add_argument("--device-id", default="device-demo-001")
    parser.add_argument("--api-base-url", default=None, help="Override API_BASE_URL")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument(
        "--export-only", action="store_true", help="Generate without HTTP"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "test-results/telemetry"
    )
    args = parser.parse_args()
    run_id = args.run_id or uuid4().hex
    try:
        scenarios = load_scenarios(run_id, args.device_id, args.scenario)
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("Timeout must be finite and positive")
        if args.list:
            for scenario in scenarios:
                print(f"{scenario['name']}: {scenario['purpose']}")
            return
        base_url = args.api_base_url or os.environ.get(
            "API_BASE_URL", "http://127.0.0.1:8000/api"
        )
        token = os.environ.get("GATEWAY_API_KEY", "")
        if not args.export_only:
            validate_target(base_url, token)
        directory = args.output_dir.resolve() / run_id
        export_scenarios(scenarios, directory, run_id)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    summary = {
        "mode": "export-only" if args.export_only else "api-only",
        "contract": "telemetry-batch.v1",
        "run_id": run_id,
        "fixtures": str(directory),
    }
    if not args.export_only:
        reports = run_scenarios(scenarios, base_url, token, args.timeout)
        summary.update(
            passed=all(report["passed"] for report in reports), results=reports
        )
        (directory / "report.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary))
    raise SystemExit(0 if summary.get("passed", True) else 1)


if __name__ == "__main__":
    main()
