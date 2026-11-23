"""Applica una singola decisione di rischio alto al client SDN e all'helper."""

import argparse
import json
import uuid

from .helper_result import EXAMPLES, GROUPS
from .helper_status import IDENTIFIER, apply_profile
from .policy import AdaptivePolicy


def handle_alarm(decision, run_id, policy_id, version, block_classic, send_profile=apply_profile):
    target = decision["target_id"]
    if (decision["reason"] != "high_risk" or decision["desired_profile"] != "HYBRID"
            or decision["decision"] not in ("BLOCK", "REQUEST_PROFILE") or target not in ("iot", "drone")):
        raise ValueError("Attesa una decisione di rischio alto per il target")
    if (not IDENTIFIER.fullmatch(run_id) or run_id in (".", "..") or not IDENTIFIER.fullmatch(policy_id)
            or type(version) is not int or version < 1):
        raise ValueError("Identificativi o versione di policy non validi")

    result = {"target_id": target, "policy_id": policy_id, "policy_version": version,
              "desired_profile": "HYBRID", "helper_requested": False, "outcome": "UNKNOWN"}
    try:
        rule = block_classic(target, blocked=True)
    except (OSError, ValueError, RuntimeError) as error:
        return dict(result, sdn="UNKNOWN", detail=str(error))
    if (not isinstance(rule, dict) or rule.get("target_id") != target or rule.get("action") != "block"
            or rule.get("status") != "RULE_VERIFIED" or rule.get("verification") != "flow_stats"):
        return dict(result, sdn="UNKNOWN")
    result["sdn"] = "RULE_VERIFIED"
    if decision["decision"] == "BLOCK":
        return dict(result, outcome="BLOCKED", unsupported_by=decision["unsupported_by"])

    identity = json.dumps([run_id, target, policy_id, version, "set_profile"], separators=(",", ":"))
    command = {"schema_version": 1, "message_type": "request", "run_id": run_id,
               "target_id": target, "request_id": uuid.uuid5(uuid.NAMESPACE_OID, identity).hex,
               "policy_id": policy_id, "policy_version": version, "action": "set_profile",
               "required_profile": "HYBRID", "reason": decision["reason"], "timeout_ms": 10000}
    result["helper_requested"] = True
    helper = send_profile(command)
    return dict(result, helper=helper, outcome=helper["outcome"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("example", help="Usa switch e helper simulati")
    live = modes.add_parser("apply", help="Applica il blocco reale e contatta l'helper della VM")
    live.add_argument("run_id")
    live.add_argument("target", choices=("iot", "drone"))
    live.add_argument("policy_id")
    live.add_argument("version", type=int)
    live.add_argument("--client", required=True, nargs="+", choices=GROUPS)
    live.add_argument("--server", required=True, nargs="+", choices=GROUPS)
    args = parser.parse_args()
    if args.mode == "example":
        with EXAMPLES.open(encoding="utf-8") as source:
            case = next(s for s in json.load(source)["scenarios"] if s["name"] == "hybrid_success")
        req = case["request"]
        target, run_id = req["target_id"], req["run_id"]
        policy_id, version = req["policy_id"], req["policy_version"]
        client = server = list(GROUPS)

        def block(target, blocked):
            return {"target_id": target, "action": "block", "status": "RULE_VERIFIED",
                    "verification": "flow_stats"}

        def send(command):
            def reply(query):
                return dict(case["response"], request_id=query["request_id"])
            return apply_profile(command, reply)
    else:
        try:
            from controller.sdn_client import set_classic_block as block
        except ModuleNotFoundError as error:
            parser.error("Client SDN non disponibile: aggiungi il worktree SDN a PYTHONPATH (%s)" % error)
        target, run_id = args.target, args.run_id
        policy_id, version = args.policy_id, args.version
        client, server = args.client, args.server
        send = apply_profile

    # Con rischio alto la decisione è obbligatoria per ogni batteria e rete.
    decision = AdaptivePolicy().decide(target, "high", minimum_profile="CLASSIC", battery_pct=100,
                                       network="nominal", client_profiles=client, server_profiles=server)
    try:
        result = handle_alarm(decision, run_id, policy_id, version, block, send)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(dict(result, mode=args.mode), indent=2))
    return int(result["outcome"] not in ("HYBRID_ACTIVE", "BLOCKED"))


if __name__ == "__main__":
    raise SystemExit(main())
