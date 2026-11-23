import json
import unittest
from copy import deepcopy

from orchestrator.helper_result import EXAMPLES, interpret_set_profile


class HelperResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with EXAMPLES.open(encoding="utf-8") as source:
            cls.scenarios = {s["name"]: s for s in json.load(source)["scenarios"]}

    def test_contract_examples(self):
        expected = {
            "start_classic": {"outcome": "CLASSIC_ACTIVE", "connection_id": "conn-iot-001"},
            "hybrid_success": {"outcome": "HYBRID_ACTIVE", "connection_id": "conn-iot-002"},
            "hybrid_timeout": {"outcome": "BLOCKED", "code": "timeout", "phase": "tls_handshake"},
            "hybrid_ack_timeout": {"outcome": "BLOCKED", "code": "timeout", "phase": "application_ack"},
            "stale_policy": {"outcome": "REJECTED", "code": "stale_policy"},
        }
        for name, result in expected.items():
            with self.subTest(name=name):
                case = self.scenarios[name]
                self.assertEqual(interpret_set_profile(case["request"], case["response"]), result)

    def test_no_reply_is_unknown(self):
        request = self.scenarios["hybrid_success"]["request"]
        self.assertEqual(interpret_set_profile(request, None), {"outcome": "UNKNOWN"})

    def test_wrong_request_or_incomplete_evidence_is_unknown(self):
        case = self.scenarios["hybrid_success"]
        for location, key, value in [
            ("response", "request_id", "other"),
            ("state", "policy_version", 1),
            ("state", "observed_group", "X25519"),
            ("state", "application_ack", False),
            ("state", "certificate_ok", False),
            ("state", "connection_id", None),
        ]:
            with self.subTest(key=key):
                response = deepcopy(case["response"])
                target = response if location == "response" else response["state"]
                target[key] = value
                self.assertEqual(interpret_set_profile(case["request"], response), {"outcome": "UNKNOWN"})
