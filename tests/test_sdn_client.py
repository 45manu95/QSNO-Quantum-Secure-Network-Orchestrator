"""Test della verifica delle regole, senza controller o rete."""

import unittest
from unittest.mock import patch

from controller import sdn_client


def iot_rule():
    """Una nuova copia della regola attesa per ogni test."""
    return {
        "cookie": 4097,
        "table_id": 0,
        "priority": 100,
        "idle_timeout": 0,
        "hard_timeout": 0,
        "match": {
            "dl_type": 2048,
            "nw_src": "10.0.0.2",
            "nw_dst": "10.0.0.1",
            "nw_proto": 6,
            "tp_dst": 4433,
        },
        "actions": [],
    }


class VerifyClassicBlockTests(unittest.TestCase):
    def verify(self, flows, blocked):
        # Il tempo simulato consente una lettura e poi scade:
        # nessuna attesa reale nei test.
        with patch.object(
            sdn_client, "get_switch_flows", return_value=flows
        ), patch.object(
            sdn_client.time,
            "monotonic",
            side_effect=[0, 0, 0, 6, 6],
        ), patch.object(sdn_client.time, "sleep"):
            sdn_client.verify_classic_block(
                "iot", blocked=blocked, timeout=5
            )

    def test_correct_block_is_accepted(self):
        self.verify([iot_rule()], blocked=True)

    def test_wrong_rules_are_rejected(self):
        changes = {
            "forwarding_instead_of_drop": {
                "actions": ["OUTPUT:1"]
            },
            "wrong_priority": {"priority": 1},
            "wrong_table": {"table_id": 1},
            "expiring_rule": {"hard_timeout": 30},
        }

        for name, change in changes.items():
            with self.subTest(case=name):
                rule = iot_rule()
                rule.update(change)
                with self.assertRaises(TimeoutError):
                    self.verify([rule], blocked=True)

    def test_wrong_port_is_rejected(self):
        rule = iot_rule()
        rule["match"]["tp_dst"] = 4443

        with self.assertRaises(TimeoutError):
            self.verify([rule], blocked=True)

    def test_missing_block_is_rejected(self):
        with self.assertRaises(TimeoutError):
            self.verify([], blocked=True)

    def test_unblock_fails_if_rule_remains(self):
        with self.assertRaises(TimeoutError):
            self.verify([iot_rule()], blocked=False)

    def test_unblock_ignores_other_client_cookie(self):
        drone_rule = iot_rule()
        drone_rule["cookie"] = 4098
        drone_rule["match"]["nw_src"] = "10.0.0.3"

        self.verify([drone_rule], blocked=False)

    def test_read_failure_is_not_success(self):
        with patch.object(
            sdn_client,
            "get_switch_flows",
            side_effect=RuntimeError("Switch non disponibile"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "Switch non disponibile"
            ):
                sdn_client.verify_classic_block(
                    "iot", blocked=False
                )

    def test_block_appears_after_first_read(self):
        with patch.object(
            sdn_client,
            "get_switch_flows",
            side_effect=[[], [iot_rule()]],
        ) as read_flows, patch.object(
            sdn_client.time, "monotonic", return_value=0
        ), patch.object(sdn_client.time, "sleep") as sleep:
            sdn_client.verify_classic_block(
                "iot", blocked=True, timeout=5
            )

        self.assertEqual(read_flows.call_count, 2)
        sleep.assert_called_once_with(0.2)


if __name__ == "__main__":
    unittest.main()