"""Applica eventi di rischio e campioni di telemetria JSON per una prova e un target."""

import argparse
import json
import sys
import time
import math
from datetime import datetime

from .helper_result import EXAMPLES, GROUPS
from .helper_status import IDENTIFIER, apply_profile, unique_fields
from .high_risk import apply_decision
from .policy import AdaptivePolicy


def process_events(lines, run_id, target, client, server, block, send=apply_profile, *,
                   minimum="CLASSIC", battery=100, network="nominal", stability_seconds=10):
    if not math.isfinite(stability_seconds) or stability_seconds < 0:
        raise ValueError("La stabilizzazione richiede una durata finita e non negativa")
    policy = AdaptivePolicy()
    seen = {}
    version = 0
    previous_decision = None
    last_high = None
    last_telemetry = None
    pending_action = None
    pending_since_ns = 0
    for line in lines:
        # La riga è disponibile al lettore. Il timestamp del monitor ha un'altra origine.
        received_ns = time.monotonic_ns()
        try:
            event = json.loads(line, object_pairs_hook=unique_fields)
            fields = {"event_id", "target_id", "severity", "source", "timestamp"}
            telemetry = isinstance(event, dict) and event.get("severity") == "telemetry"
            expected = fields | {"battery_pct", "network"} if telemetry else fields
            if not isinstance(event, dict) or set(event) != expected:
                raise ValueError("Campi evento non validi")
            if not all(isinstance(event[key], str) for key in fields):
                raise ValueError("I campi evento devono essere stringhe")
            if telemetry and (type(event["battery_pct"]) not in (int, float)
                              or not 0 <= event["battery_pct"] <= 100
                              or event["network"] not in ("nominal", "degraded")):
                raise ValueError("Telemetria non valida")
            event_id = event["event_id"]
            if not IDENTIFIER.fullmatch(event_id) or not event["source"].strip():
                raise ValueError("ID evento o sorgente non validi")
            severity = event["severity"]
            if event["target_id"] != target or severity not in ("high", "low", "reset", "telemetry"):
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
        if severity in ("high", "reset"):
            pending_action = None
        if telemetry:
            if last_telemetry is not None and when <= last_telemetry:
                seen[event_id] = (event, version)
                yield {"event_id": event_id, "event_status": "REJECTED", "detail": "Campione obsoleto"}
                continue
            last_telemetry = when
        decision = policy.decide(target, "low" if telemetry else severity, minimum_profile=minimum,
                                 battery_pct=event.get("battery_pct", battery),
                                 network=event.get("network", network),
                                 client_profiles=client, server_profiles=server)
        decision_ms = (time.monotonic_ns() - received_ns) / 1_000_000
        info = {"run_id": run_id, "target_id": target, "event_id": event_id,
                "event_status": "PROCESSED", "severity": severity,
                "event_to_decision_ms": decision_ms, "event_to_sdn_verified_ms": None,
                "alarm_active": target in policy.active_alarms, "reason": decision["reason"]}
        required_action = (decision["decision"], decision["desired_profile"])
        if telemetry:
            info.update(battery_pct=event["battery_pct"], network=event["network"])
            # Prima del primo comando anche il profilo iniziale è solo un'intenzione.
            reference = previous_decision
            if reference is None:
                initial = policy.decide(target, "low", minimum_profile=minimum, battery_pct=battery,
                                        network=network, client_profiles=client, server_profiles=server)
                reference = (initial["decision"], initial["desired_profile"])
            if required_action != reference and stability_seconds and decision["decision"] != "BLOCK":
                if pending_action != required_action:
                    pending_action = required_action
                    pending_since_ns = received_ns
                age = (received_ns - pending_since_ns) / 1_000_000_000
                if age < stability_seconds:
                    seen[event_id] = (event, version)
                    yield dict(info, event_status="PENDING", policy_version=version,
                               desired_profile=decision["desired_profile"], stable_for_s=age,
                               sdn_action="keep", helper_requested=False)
                    continue
            pending_action = None
            battery, network = event["battery_pct"], event["network"]
        if severity != "high" and required_action == previous_decision:
            seen[event_id] = (event, version)
            yield dict(info, policy_version=version, desired_profile=decision["desired_profile"],
                       sdn_action="keep", helper_requested=False)
            continue
        version += 1
        seen[event_id] = (event, version)
        result = apply_decision(decision, run_id, event_id, version, block, send,
                                event_received_ns=received_ns)
        previous_decision = required_action if result["sdn"] == "RULE_VERIFIED" else None
        yield {**info, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("example", help="Consegna due volte E17 con SDN e helper simulati")
    modes.add_parser("reset-example", help="Prova high, low e reset con batteria simulata al 15 percento")
    modes.add_parser("telemetry-example", help="Drone 35–25 per cento, con switch e helper simulati")
    live = modes.add_parser("listen", help="Legge stdin e applica gli allarmi sulla VM")
    live.add_argument("run_id", help="Nuova prova, dedicata a questo processo e all'helper")
    live.add_argument("target", choices=("iot", "drone"))
    live.add_argument("--client", nargs="+", required=True, choices=GROUPS)
    live.add_argument("--server", nargs="+", required=True, choices=GROUPS)
    live.add_argument("--minimum", choices=GROUPS, default="CLASSIC")
    live.add_argument("--battery", type=float, default=100)
    live.add_argument("--network", choices=("nominal", "degraded"), default="nominal")
    live.add_argument("--stability-seconds", type=float, default=10)
    args = parser.parse_args()
    if args.mode in ("example", "reset-example", "telemetry-example"):
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
        if args.mode == "telemetry-example":
            target, battery = "drone", 35
            def telemetry_lines():
                base = dict(json.loads(line), target_id=target, severity="low")
                yield json.dumps(base)
                base.update(severity="telemetry", network="nominal", battery_pct=25, event_id="T1",
                            timestamp="2026-11-23T10:00:01Z")
                yield json.dumps(base)
                time.sleep(10)
                yield json.dumps(dict(base, event_id="T2", timestamp="2026-11-23T10:00:11Z"))
            lines = telemetry_lines()
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
                response["target_id"] = target
                response["request_id"] = query["request_id"]
                response["state"] = dict(response["state"], policy_id=query["policy_id"],
                                         policy_version=query["policy_version"])
                if args.mode == "telemetry-example":
                    response["state"]["connection_id"] = "demo-{}-v{}".format(target, query["policy_version"])
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
        if not math.isfinite(args.stability_seconds) or args.stability_seconds < 0:
            parser.error("La stabilizzazione richiede una durata finita e non negativa")
    for result in process_events(lines, run_id, target, client, server, block, send,
                                 minimum=minimum, battery=battery, network=network,
                                 stability_seconds=getattr(args, "stability_seconds", 10)):
        print(json.dumps(dict(result, mode=args.mode)), flush=True)


if __name__ == "__main__":
    main()
