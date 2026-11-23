"""Riceve allarmi di rischio alto, uno per riga JSON, per una prova e un target."""

import argparse
import json
import sys
from datetime import datetime

from .helper_result import EXAMPLES, GROUPS
from .helper_status import IDENTIFIER, apply_profile, unique_fields
from .high_risk import handle_alarm
from .policy import AdaptivePolicy


def process_events(lines, run_id, target, client, server, block, send=apply_profile):
    policy = AdaptivePolicy()
    seen = {}
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
            if event["target_id"] != target or event["severity"] != "high":
                raise ValueError("Atteso allarme alto per il target della prova")
            stamp = event["timestamp"]
            when = datetime.fromisoformat(stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp)
            if when.utcoffset() is None:
                raise ValueError("Il timestamp deve includere il fuso orario")
        except (ValueError, RecursionError) as error:
            yield {"event_status": "REJECTED", "detail": str(error)}
            continue
        if event_id in seen:
            previous, version = seen[event_id]
            status = "DUPLICATE" if previous == event else "EVENT_ID_CONFLICT"
            yield {"event_id": event_id, "event_status": status, "original_policy_version": version}
            continue
        version = len(seen) + 1
        seen[event_id] = (event, version)
        decision = policy.decide(target, "high", minimum_profile="CLASSIC", battery_pct=100,
                                 network="nominal", client_profiles=client, server_profiles=server)
        result = handle_alarm(decision, run_id, event_id, version, block, send)
        yield {"event_id": event_id, "event_status": "PROCESSED", **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("example", help="Consegna due volte E17 con SDN e helper simulati")
    live = modes.add_parser("listen", help="Legge stdin e applica gli allarmi sulla VM")
    live.add_argument("run_id", help="Nuova prova, dedicata a questo processo e all'helper")
    live.add_argument("target", choices=("iot", "drone"))
    live.add_argument("--client", nargs="+", required=True, choices=GROUPS)
    live.add_argument("--server", nargs="+", required=True, choices=GROUPS)
    args = parser.parse_args()
    if args.mode == "example":
        with EXAMPLES.open(encoding="utf-8") as source:
            case = next(s for s in json.load(source)["scenarios"] if s["name"] == "hybrid_success")
        req = case["request"]
        target, run_id = req["target_id"], req["run_id"]
        client = server = list(GROUPS)
        line = json.dumps({"event_id": "E17", "target_id": target, "severity": "high",
                           "source": "ids-simulato", "timestamp": "2026-11-23T10:00:00Z"})
        lines = (line, line)

        def block(target, blocked):
            return {"target_id": target, "action": "block", "status": "RULE_VERIFIED",
                    "verification": "flow_stats"}

        def send(command):
            def reply(query):
                response = case["response"].copy()
                response["request_id"] = query["request_id"]
                response["state"] = dict(response["state"], policy_id=query["policy_id"],
                                         policy_version=query["policy_version"])
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
    for result in process_events(lines, run_id, target, client, server, block, send):
        print(json.dumps(dict(result, mode=args.mode)), flush=True)


if __name__ == "__main__":
    main()
