import json
import unittest
from unittest.mock import Mock, patch

from orchestrator.risk_events import process_events


def event(sec, level="telemetry", **fields):
    row = dict(event_id="E{}".format(sec), target_id="drone", severity=level,
               source="test", timestamp="2026-11-24T10:00:{:02d}Z".format(sec))
    if level == "telemetry":
        row.update(network="nominal", battery_pct=25)
    return json.dumps(dict(row, **fields))


class TelemetryTests(unittest.TestCase):
    def run_events(self, events, **config):
        now = 0
        def lines():
            nonlocal now
            for sec, row in events:
                now = sec * 10**9
                yield row

        def sdn(target, blocked):
            return dict(target_id=target, action="block" if blocked else "unblock",
                        status="RULE_VERIFIED", verification="flow_stats")

        self.helper = Mock(side_effect=lambda c: {"outcome": c["required_profile"] + "_ACTIVE"})
        with patch("orchestrator.risk_events.time.monotonic_ns", side_effect=lambda: now):
            return list(process_events(lines(), "prova", "drone", ["CLASSIC", "HYBRID"],
                                       ["CLASSIC", "HYBRID"], sdn, self.helper, battery=35, **config))

    def test_switch_after_two_confirming_samples(self):
        rows = self.run_events([(0, event(0, "low")), (1, event(1)), (10, event(10)),
                                (11, event(11))])
        self.assertEqual([r["event_status"] for r in rows], ["PROCESSED", "PENDING", "PENDING", "PROCESSED"])
        self.assertEqual([r["sdn_action"] for r in rows], ["block", "keep", "keep", "unblock"])
        self.assertEqual([r["policy_version"] for r in rows], [1, 1, 1, 2])
        self.assertEqual(self.helper.call_count, 2)

    def test_return_to_original_conditions_restarts_window(self):
        rows = self.run_events([(0, event(0, "low")), (1, event(1)), (7, event(7, battery_pct=35)),
                                (9, event(9)), (12, event(12)), (19, event(19))])
        self.assertEqual(rows[2]["sdn_action"], "keep")
        self.assertEqual(rows[4]["event_status"], "PENDING")
        self.assertEqual(rows[5]["outcome"], "CLASSIC_ACTIVE")
        self.assertEqual(self.helper.call_count, 2)

    def test_network_and_minimum(self):
        seq = [(0, event(0, "low")), (1, event(1, battery_pct=80, network="degraded")),
               (11, event(11, battery_pct=80, network="degraded"))]
        self.assertEqual(self.run_events(seq)[-1]["outcome"], "CLASSIC_ACTIVE")
        rows = self.run_events(seq, minimum="HYBRID")
        self.assertEqual(rows[-1]["sdn_action"], "keep")
        self.assertEqual(self.helper.call_count, 1)

    def test_alarm_interrupts_pending_change_and_stays_latched(self):
        rows = self.run_events([(0, event(0, "low")), (1, event(1)), (2, event(2, "high")),
                                (12, event(12)), (13, event(13, "low"))])
        self.assertEqual(rows[2]["outcome"], "HYBRID_ACTIVE")
        self.assertTrue(rows[-1]["alarm_active"])
        self.assertTrue(all(r["sdn_action"] != "unblock" for r in rows))

    def test_invalid_stale_duplicate_and_future_sender_time_do_not_confirm(self):
        rows = self.run_events([(0, event(0, "low")), (1, event(5)), (2, event(5)),
                                (3, event(4)), (4, event(10, battery_pct=True)),
                                (5, event(55)), (6, event(56, network="altro"))])
        self.assertEqual([r["event_status"] for r in rows[2:]],
                         ["DUPLICATE", "REJECTED", "REJECTED", "PENDING", "REJECTED"])
        self.assertEqual(self.helper.call_count, 1)
