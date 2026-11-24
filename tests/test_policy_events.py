"""Controlli del responsabile A, con controller e helper sostituiti in memoria."""
import json
import unittest
from unittest.mock import Mock

from orchestrator.policy import AdaptivePolicy
from orchestrator.risk_events import process_events


PROFILES = ["CLASSIC", "HYBRID"]


class PolicyTests(unittest.TestCase):
    def test_selection_matrix(self):
        cases = [
            ("high", "CLASSIC", 15, "degraded", "HYBRID", "high_risk"),
            ("low", "HYBRID", 15, "degraded", "HYBRID", "service_minimum"),
            ("low", "CLASSIC", 29, "nominal", "CLASSIC", "low_battery"),
            ("low", "CLASSIC", 30, "nominal", "HYBRID", "default_preference"),
            ("low", "CLASSIC", 90, "degraded", "CLASSIC", "degraded_network"),
        ]
        for event, minimum, battery, network, expected, reason in cases:
            with self.subTest(event=event, minimum=minimum, battery=battery, network=network):
                result = AdaptivePolicy().decide("drone", event, minimum_profile=minimum,
                    battery_pct=battery, network=network, client_profiles=PROFILES,
                    server_profiles=PROFILES)
                self.assertEqual((result["decision"], result["desired_profile"], result["reason"]),
                                 ("REQUEST_PROFILE", expected, reason))


class EventTests(unittest.TestCase):
    def setUp(self):
        def verify(target, blocked):
            return dict(target_id=target, action="block" if blocked else "unblock",
                        status="RULE_VERIFIED", verification="flow_stats")
        self.block = Mock(side_effect=verify)
        self.send = Mock(return_value={"outcome": "UNKNOWN"})

    def events(self, entries, client=PROFILES, server=PROFILES):
        lines = [json.dumps(dict(event_id=identifier, target_id=target, severity=level,
                                 source="test", timestamp="2026-11-23T10:00:00Z"))
                 for identifier, target, level in entries]
        return list(process_events(lines, "test-policy", "drone", client, server,
                                   self.block, self.send, battery=15))

    def test_unsupported_peer(self):
        for client, server, peer in [(["CLASSIC"], PROFILES, "drone"),
                                     (PROFILES, ["CLASSIC"], "server")]:
            with self.subTest(peer=peer):
                result, = self.events([("E1", "drone", "high")], client, server)
                self.assertEqual((result["outcome"], result["unsupported_by"]), ("BLOCKED", [peer]))
                self.block.assert_called_with("drone", blocked=True)
                self.send.assert_not_called()

    def test_wrong_target(self):
        result, = self.events([("E1", "ignoto", "high")])
        self.assertEqual(result["event_status"], "REJECTED")
        self.block.assert_not_called()
        self.send.assert_not_called()

    def test_duplicate_and_conflicting_id(self):
        rows = self.events([("E1", "drone", "high"), ("E1", "drone", "high"),
                            ("E1", "drone", "reset")])
        self.assertEqual([r["event_status"] for r in rows],
                         ["PROCESSED", "DUPLICATE", "EVENT_ID_CONFLICT"])
        self.block.assert_called_once_with("drone", blocked=True)
        self.send.assert_called_once()

    def test_alarm_latched_until_reset(self):
        rows = self.events([("E1", "drone", "high"), ("E2", "drone", "low"),
                            ("E3", "drone", "reset")])
        self.assertEqual([r["sdn_action"] for r in rows], ["block", "keep", "unblock"])
        self.assertEqual([r["alarm_active"] for r in rows], [True, True, False])
        self.assertEqual([r["policy_version"] for r in rows], [1, 1, 2])
        self.assertEqual(rows[0]["outcome"], "UNKNOWN")
        self.assertEqual(rows[-1]["desired_profile"], "CLASSIC")

    def test_no_helper_after_sdn_error(self):
        self.block.side_effect = OSError("controller simulato indisponibile")
        result, = self.events([("E1", "drone", "high")])
        self.assertEqual((result["sdn"], result["outcome"]), ("UNKNOWN", "UNKNOWN"))
        self.send.assert_not_called()
