"""Applica eventi high, low e reset, uno per riga JSON, per una prova e un target."""

import argparse
import json
import sys
from datetime import datetime

from .helper_result import EXAMPLES, GROUPS
from .helper_status import IDENTIFIER, apply_profile, unique_fields
from .high_risk import apply_decision
from .policy import AdaptivePolicy


def process_events(lines, run_id, target, client, server, block, send=apply_profile, *,
                   minimum="CLASSIC", battery=100, network="nominal"):
    policy = AdaptivePolicy()
    seen = {}
    version = 0
    previous_decision = None
    last_high = None
    for line in lines:
        try:
            event = json.loads(line, object_pairs_hook=unique_fields)
            fields = {"event_id", "target_id", "severity", "source", "timestamp"}
            if not isinstance(event, dict) or set(event) != fields:
                raise ValueError("Campi evento non validi")
            if not all(isinstance(value, str) for value in event.values()):
                raise ValueError("I campi evento devono essere stringhe")
            event_id = event["event_id"]
            if not IDENTIFIER.fullmatch(event_id) or not event["source"].strip():
                raise ValueError("ID evento o sorgente non validi")
            severity = event["severity"]
            if event["target_id"] != target or severity not in ("high", "low", "reset"):
                raise ValueError("Target o tipo di evento non valido")
            stamp = event["timestamp"]
            when = datetime.fromisoformat(stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp)
            if when.utcoffset() is None:
                raise ValueError("Il timestamp deve includere il fuso orario")
        except (ValueError, RecursionError) as error:
            yield {"event_status": "REJECTED", "detail": str(error)}
            continue
        if event_id in seen:
            previous, original_version = seen[event_id]
            status = "DUPLICATE" if previous == event else "EVENT_ID_CONFLICT"
            yield {"event_id": event_id, "event_status": status, "original_policy_version": original_version}
            continue
        if severity == "reset" and last_high is not None and when < last_high:
            seen[event_id] = (event, version)
            yield {"event_id": event_id, "event_status": "REJECTED", "detail": "Reset anteriore all'allarme"}
            continue
        if severity == "high":
            last_high = max(last_high, when) if last_high else when
        decision = policy.decide(target, severity, minimum_profile=minimum, battery_pct=battery,
                                 network=network, client_profiles=client, server_profiles=server)
        info = {"event_id": event_id, "event_status": "PROCESSED", "severity": severity,
                "alarm_active": target in policy.active_alarms, "reason": decision["reason"]}
        required_action = (decision["decision"], decision["desired_profile"])
        if severity != "high" and required_action == previous_decision:
            seen[event_id] = (event, version)
            yield dict(info, policy_version=version, desired_profile=decision["desired_profile"],
                       sdn_action="keep", helper_requested=False)
            continue
        version += 1
        seen[event_id] = (event, version)
        result = apply_decision(decision, run_id, event_id, version, block, send)
        previous_decision = required_action if result["sdn"] == "RULE_VERIFIED" else None
        yield {**info, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("example", help="Consegna due volte E17 con SDN e helper simulati")
    modes.add_parser("reset-example", help="Prova high, low e reset con batteria simulata al 15 percento")
    live = modes.add_parser("listen", help="Legge stdin e applica gli allarmi sulla VM")
    live.add_argument("run_id", help="Nuova prova, dedicata a questo processo e all'helper")
    live.add_argument("target", choices=("iot", "drone"))
    live.add_argument("--client", nargs="+", required=True, choices=GROUPS)
    live.add_argument("--server", nargs="+", required=True, choices=GROUPS)
    live.add_argument("--minimum", choices=GROUPS, default="CLASSIC")
    live.add_argument("--battery", type=float, default=100)
    live.add_argument("--network", choices=("nominal", "degraded"), default="nominal")
    args = parser.parse_args()
    if args.mode in ("example", "reset-example"):
        with EXAMPLES.open(encoding="utf-8") as source:
            cases = {s["name"]: s for s in json.load(source)["scenarios"]}
        case = cases["hybrid_success"]
        req = case["request"]
        target, run_id = req["target_id"], req["run_id"]
        client = server = list(GROUPS)
        line = json.dumps({"event_id": "E17", "target_id": target, "severity": "high",
                           "source": "ids-simulato", "timestamp": "2026-11-23T10:00:00Z"})
        lines = (line, line)
        minimum, battery, network = "CLASSIC", 15, "nominal"
        if args.mode == "reset-example":
            base = json.loads(line)
            lines = [json.dumps(dict(base, event_id="E%d" % (17 + i), severity=kind,
                                     timestamp="2026-11-23T10:00:0%dZ" % i))
                     for i, kind in enumerate(("high", "low", "reset"))]

        def block(target, blocked):
            return {"target_id": target, "action": "block" if blocked else "unblock", "status": "RULE_VERIFIED",
                    "verification": "flow_stats"}

        def send(command):
            def reply(query):
                sample = "hybrid_success" if command["required_profile"] == "HYBRID" else "start_classic"
                response = cases[sample]["response"].copy()
                response["request_id"] = query["request_id"]
                response["state"] = dict(response["state"], policy_id=query["policy_id"],
                                         policy_version=query["policy_version"])
                if args.mode == "reset-example":
                    response["state"]["last_acked_seq"] = 41 + query["policy_version"]
                return response
            return apply_profile(command, reply)
    else:
        if not IDENTIFIER.fullmatch(args.run_id) or args.run_id in (".", ".."):
            parser.error("run_id non valido")
        try:
            from controller.sdn_client import set_classic_block as block
        except ModuleNotFoundError:
            parser.error("Aggiungi il worktree SDN a PYTHONPATH")
        lines, target, run_id = sys.stdin, args.target, args.run_id
        client, server, send = args.client, args.server, apply_profile
        minimum, battery, network = args.minimum, args.battery, args.network
        if not 0 <= battery <= 100:
            parser.error("La batteria deve essere compresa fra 0 e 100")
    for result in process_events(lines, run_id, target, client, server, block, send,
                                 minimum=minimum, battery=battery, network=network):
        print(json.dumps(dict(result, mode=args.mode)), flush=True)


if __name__ == "__main__":
    main()
