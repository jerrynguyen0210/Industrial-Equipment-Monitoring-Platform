import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime

from events import Scenario, TemperatureProfile, batches, encode_batch, generate_events


class EventGenerationTests(unittest.TestCase):
    def setUp(self):
        self.scenario = Scenario(
            device_id="device-test", run_id="scenario-test", count=5
        )

    def test_seeded_noise_has_a_known_sequence_and_replays_byte_for_byte(self):
        scenario = replace(self.scenario, seed=7, profile=TemperatureProfile(noise=0.5))
        first = list(batches(scenario, 3))
        second = list(batches(scenario, 3))
        self.assertEqual(
            list(map(encode_batch, first)), list(map(encode_batch, second))
        )
        self.assertEqual(
            [event["value"] for batch in first for event in batch["events"]],
            [24.823833, 24.650849, 25.150934, 24.572436, 25.035882],
        )
        changed = list(generate_events(replace(scenario, seed=8)))
        self.assertNotEqual(first[0]["events"][0]["value"], changed[0]["value"])

    def test_temperature_profiles_follow_sample_index_across_reboots(self):
        for profile, expected in (
            (TemperatureProfile(temperature=-5), [-5, -5, -5, -5, -5]),
            (TemperatureProfile(kind="ramp", step=-0.5), [25, 24.5, 24, 23.5, 23]),
            (
                TemperatureProfile(kind="sine", amplitude=2, period=4),
                [25, 27, 25, 23, 25],
            ),
        ):
            with self.subTest(profile=profile):
                events = generate_events(
                    replace(self.scenario, profile=profile, reboot_every=2)
                )
                self.assertEqual([event["value"] for event in events], expected)

    def test_sequence_does_not_reset_at_batch_boundaries(self):
        scenario = replace(self.scenario, count=501)
        generated = list(batches(scenario, 500))
        self.assertEqual([len(batch["events"]) for batch in generated], [500, 1])
        events = [event for batch in generated for event in batch["events"]]
        self.assertEqual(
            [event["sequence_number"] for event in events], list(range(501))
        )
        self.assertEqual(len({event["boot_id"] for event in events}), 1)
        self.assertEqual(events[-1]["device_uptime_ms"], 500000)
        self.assertEqual(events[-1]["measured_at"], "2026-01-01T00:08:20.000000Z")

    def test_reboot_changes_boot_before_reset_and_preserves_virtual_time(self):
        scenario = replace(
            self.scenario, boot_id="explicit-boot", reboot_every=2, interval_ms=250
        )
        events = list(generate_events(scenario))
        self.assertEqual(events, list(generate_events(scenario)))
        self.assertEqual([e["sequence_number"] for e in events], [0, 1, 0, 1, 0])
        self.assertEqual([e["device_uptime_ms"] for e in events], [0, 250, 0, 250, 0])
        self.assertEqual(events[0]["boot_id"], "explicit-boot")
        self.assertEqual(len({e["boot_id"] for e in events}), 3)
        self.assertEqual(len({(e["boot_id"], e["sequence_number"]) for e in events}), 5)
        self.assertEqual(events[-1]["measured_at"], "2026-01-01T00:00:01.000000Z")
        for event in events:
            self.assertEqual(event["gateway_received_at"], event["measured_at"])
            self.assertNotIn("backend_received_at", event)

    def test_run_and_device_names_isolate_generated_boots(self):
        variants = [
            self.scenario,
            replace(self.scenario, run_id="other-run"),
            replace(self.scenario, device_id="other-device"),
        ]
        self.assertEqual(
            len({next(generate_events(s))["boot_id"] for s in variants}), 3
        )

    def test_offset_start_normalizes_to_utc_and_json_round_trips(self):
        scenario = replace(
            self.scenario,
            start_time=datetime.fromisoformat("2026-09-25T09:30:00+09:30"),
        )
        batch = next(batches(scenario, 5))
        self.assertEqual(batch, json.loads(encode_batch(batch)))
        self.assertEqual(
            batch["events"][0]["measured_at"], "2026-09-25T00:00:00.000000Z"
        )

    def test_batch_size_preserves_seeded_events_and_fractional_start_time(self):
        scenario = replace(
            self.scenario,
            start_time=datetime.fromisoformat("2026-09-25T00:00:00.123456Z"),
            seed=7,
            reboot_every=2,
            profile=TemperatureProfile(kind="sine", noise=0.5),
        )
        expected = list(generate_events(scenario))
        self.assertEqual(expected[0]["measured_at"], "2026-09-25T00:00:00.123456Z")
        for size in (1, 2, 500):
            with self.subTest(size=size):
                self.assertEqual(
                    [
                        event
                        for batch in batches(scenario, size)
                        for event in batch["events"]
                    ],
                    expected,
                )

    def test_invalid_configuration_is_rejected_before_generation(self):
        for overrides in (
            {"device_id": ""},
            {"boot_id": "x" * 129},
            {"run_id": "bad\0id"},
            {"count": 0},
            {"count": 1_000_001},
            {"count": True},
            {"interval_ms": 0},
            {"interval_ms": 2**63},
            {"reboot_every": -1},
            {"start_time": datetime(2026, 1, 1)},
            {"start_time": datetime.max.replace(tzinfo=UTC)},
            {"profile": TemperatureProfile(kind="ramp", temperature=1e308, step=1e308)},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                replace(self.scenario, **overrides)
        for overrides in (
            {"kind": "unknown"},
            {"temperature": float("nan")},
            {"step": float("inf")},
            {"amplitude": -1},
            {"noise": -1},
            {"period": 0},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                TemperatureProfile(**overrides)
        for size in (0, 501):
            with self.subTest(size=size), self.assertRaises(ValueError):
                next(batches(self.scenario, size))
