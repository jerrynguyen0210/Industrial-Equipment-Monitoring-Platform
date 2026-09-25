"""Deterministic virtual device and temperature profiles; no I/O or wall clock."""

import json
import math
import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import islice
from uuid import NAMESPACE_URL, uuid5

SIMULATOR_VERSION = "1"
MAX_COUNTER = 2**63 - 1
MAX_EVENTS = 1_000_000


def identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or "\0" in value:
        raise ValueError(f"{name} must contain 1 to 128 characters without NUL")


def integer(value: int, name: str, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")


@dataclass(frozen=True)
class TemperatureProfile:
    kind: str = "constant"
    temperature: float = 25.0
    step: float = 0.1
    amplitude: float = 5.0
    period: int = 60
    noise: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in ("constant", "ramp", "sine"):
            raise ValueError("profile must be constant, ramp or sine")
        for name in ("temperature", "step", "amplitude", "noise"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.amplitude < 0 or self.noise < 0:
            raise ValueError("amplitude and noise must be nonnegative")
        integer(self.period, "period", 1, MAX_EVENTS)

    def baseline(self, index: int) -> float:
        if self.kind == "ramp":
            return self.temperature + self.step * index
        if self.kind == "sine":
            return self.temperature + self.amplitude * math.sin(
                math.tau * (index % self.period) / self.period
            )
        return self.temperature


@dataclass(frozen=True)
class Scenario:
    device_id: str
    run_id: str
    boot_id: str | None = None
    seed: int = 0
    count: int = 10
    interval_ms: int = 1000
    start_time: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    reboot_every: int = 0
    profile: TemperatureProfile = field(default_factory=TemperatureProfile)

    def __post_init__(self) -> None:
        identifier(self.device_id, "device_id")
        identifier(self.run_id, "run_id")
        if self.boot_id is not None:
            identifier(self.boot_id, "boot_id")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        integer(self.count, "count", 1, MAX_EVENTS)
        integer(self.interval_ms, "interval_ms", 1, MAX_COUNTER)
        integer(self.reboot_every, "reboot_every", 0, MAX_EVENTS)
        if self.start_time.tzinfo is None or self.start_time.utcoffset() is None:
            raise ValueError("start_time must include a timezone")
        try:
            start = self.start_time.astimezone(UTC)
            duration_ms = (self.count - 1) * self.interval_ms
            integer(duration_ms, "scenario duration in ms", 0, MAX_COUNTER)
            start + timedelta(milliseconds=duration_ms)
        except (OverflowError, ValueError):
            raise ValueError(
                "scenario timestamps/counters exceed supported range"
            ) from None
        object.__setattr__(self, "start_time", start)
        # Fail before any HTTP writes if even the profile's bounds are nonfinite.
        bounds = [self.profile.baseline(0), self.profile.baseline(self.count - 1)]
        if self.profile.kind == "sine":
            bounds = [
                self.profile.temperature - self.profile.amplitude,
                self.profile.temperature + self.profile.amplitude,
            ]
        if not all(
            math.isfinite(value + sign * self.profile.noise)
            for value in bounds
            for sign in (-1, 1)
        ):
            raise ValueError("profile generates nonfinite temperatures")


def generate_events(scenario: Scenario) -> Iterator[dict]:
    """Sample at virtual intervals; only a reboot resets sequence and uptime."""
    rng = random.Random(scenario.seed)
    boot_number = 0
    boot_start = 0
    initial = scenario.boot_id

    def boot_id(number: int) -> str:
        if number == 0 and initial is not None:
            return initial
        name = json.dumps(
            [SIMULATOR_VERSION, scenario.run_id, scenario.device_id, initial, number]
        )
        derived = str(uuid5(NAMESPACE_URL, name))
        # Even an explicitly supplied initial UUID cannot prevent an ID change.
        return "reboot-" + derived if derived == initial else derived

    current_boot = boot_id(0)
    for index in range(scenario.count):
        if index and scenario.reboot_every and index % scenario.reboot_every == 0:
            boot_number += 1
            current_boot = boot_id(boot_number)
            boot_start = index
        measured_at = (
            (scenario.start_time + timedelta(milliseconds=index * scenario.interval_ms))
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
        # One stable random draw per reading, including when noise is zero.
        noise = (2 * rng.random() - 1) * scenario.profile.noise
        yield {
            "device_id": scenario.device_id,
            "boot_id": current_boot,
            "sequence_number": index - boot_start,
            "measured_at": measured_at,
            "device_uptime_ms": (index - boot_start) * scenario.interval_ms,
            "gateway_received_at": measured_at,
            "metric": "temperature",
            "value": round(scenario.profile.baseline(index) + noise, 6),
            "unit": "celsius",
            "quality": {"reading": "valid", "clock": "synchronised"},
        }


def batches(scenario: Scenario, batch_size: int) -> Iterator[dict]:
    integer(batch_size, "batch_size", 1, 500)
    events = generate_events(scenario)
    while batch := list(islice(events, batch_size)):
        yield {"schema_version": 1, "events": batch}


def encode_batch(batch: dict) -> bytes:
    return json.dumps(batch, allow_nan=False, separators=(",", ":")).encode("utf-8")
