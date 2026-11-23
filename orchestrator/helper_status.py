"""Legge get_status dal socket dell'helper e riconcilia una richiesta set_profile."""

import argparse
import json
import math
import re
import socket
import time
import uuid
from pathlib import Path

from .helper_result import EXAMPLES, GROUPS, confirmed_active, interpret_set_profile


MAX_LINE = 16384
IDENTIFIER = re.compile(r"[A-Za-z0-9._-]{1,64}")
STATE_FIELDS = {"status", "policy_id", "policy_version", "desired_profile", "observed_profile",
                "observed_group", "certificate_ok", "application_ack", "connection_id",
                "last_acked_seq", "supported_profiles"}


def unique_fields(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Campo JSON duplicato")
        obj[key] = value
    return obj


def exchange_helper(request):
    if not hasattr(socket, "AF_UNIX"):
        raise OSError("Socket Unix non disponibile in questo interprete")
    run = request["run_id"]
    if not IDENTIFIER.fullmatch(run) or run in (".", "..") or request["target_id"] not in ("iot", "drone"):
        raise ValueError("Identificativo di prova o dispositivo non valido")
    path = Path("/run/qsno") / run / (request["target_id"] + ".sock")
    deadline = time.monotonic() + 2 + request.get("timeout_ms", 0) / 1000

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError("Scadenza richiesta helper")
        return seconds

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(remaining())
        channel.connect(str(path))
        channel.settimeout(remaining())
        channel.sendall(json.dumps(request).encode("utf-8") + b"\n")
        line = bytearray()
        while len(line) < MAX_LINE:
            channel.settimeout(remaining())
            part = channel.recv(min(4096, MAX_LINE - len(line)))
            if not part:
                break
            line.extend(part)
            if b"\n" in part:
                break
    if not line.endswith(b"\n") or line.count(b"\n") != 1:
        raise ValueError("Risposta helper incompleta o troppo lunga")
    return json.loads(line.decode("utf-8"), object_pairs_hook=unique_fields)


def read_status(request):
    if request["action"] != "get_status":
        raise ValueError("Attesa una richiesta get_status")
    return exchange_helper(request)


def reconcile_status(command, exchange=read_status):
    """Legge la situazione attuale senza ripetere la modifica di profilo."""
    query = {"schema_version": 1, "message_type": "request", "action": "get_status",
             "request_id": uuid.uuid4().hex, "run_id": command["run_id"],
             "target_id": command["target_id"]}
    try:
        response = exchange(query)
    except (OSError, ValueError, RecursionError) as error:
        return {"outcome": "UNKNOWN", "detail": str(error)}
    unknown = {"outcome": "UNKNOWN"}
    if not isinstance(response, dict) or set(response) != set(query) | {"ok", "state", "duration_ms", "error"}:
        return unknown
    if any(response[key] != query[key] for key in ("action", "request_id", "run_id", "target_id")):
        return unknown
    duration = response["duration_ms"]
    if (response["message_type"] != "response" or type(response["schema_version"]) is not int
            or response["schema_version"] != 1 or response["ok"] is not True or response["error"] is not None
            or type(duration) not in (int, float) or duration < 0
            or (type(duration) is float and not math.isfinite(duration))):
        return unknown
    state = response["state"]
    if not isinstance(state, dict) or set(state) != STATE_FIELDS:
        return unknown
    version = state["policy_version"]
    profile = command["required_profile"]
    if (type(version) is not int or version != command["policy_version"]
            or state["policy_id"] != command["policy_id"] or state["desired_profile"] != profile):
        return unknown
    supported = state["supported_profiles"]
    seq = state["last_acked_seq"]
    if (not isinstance(supported, list) or not all(isinstance(p, str) and p in GROUPS for p in supported)
            or len(supported) != len(set(supported)) or (seq is not None and (type(seq) is not int or seq < 0))):
        return unknown
    if confirmed_active(state, profile):
        return {"outcome": state["status"], "connection_id": state["connection_id"], "last_acked_seq": seq}
    if (state["status"] in ("TRANSITION", "BLOCKED") and state["certificate_ok"] is False
            and state["application_ack"] is False and all(state[k] is None for k in
            ("observed_profile", "observed_group", "connection_id"))):
        return {"outcome": state["status"]}
    return unknown


def apply_profile(command, exchange=exchange_helper):
    """Invia una modifica. In caso di esito incerto esegue una sola lettura."""
    try:
        response = exchange(command)
    except (OSError, ValueError, RecursionError):
        response = None
    if isinstance(response, dict):
        common = {"schema_version", "message_type", "request_id", "run_id", "target_id",
                  "action", "ok", "state", "duration_ms", "error"}
        state = response.get("state")
        duration = response.get("duration_ms")
        if (set(response) == common and isinstance(state, dict) and set(state) == STATE_FIELDS
                and type(duration) in (int, float) and duration >= 0
                and (type(duration) is int or math.isfinite(duration))):
            result = interpret_set_profile(command, response)
            if result["outcome"] != "UNKNOWN":
                return dict(result, source="set_profile")
    return dict(reconcile_status(command, exchange), source="get_status")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("example", help="Legge lo stato simulato dopo una risposta persa")
    modes.add_parser("recover-example", help="Invia set_profile e recupera la risposta persa in simulazione")
    live = modes.add_parser("read", help="Interroga il socket Unix sulla VM")
    apply = modes.add_parser("apply", help="Invia set_profile al socket Unix sulla VM")
    for mode in (live, apply):
        mode.add_argument("run_id")
        mode.add_argument("target_id", choices=("iot", "drone"))
        mode.add_argument("policy_id")
        mode.add_argument("policy_version", type=int)
        mode.add_argument("required_profile", choices=GROUPS)
    apply.add_argument("--reason", required=True)
    apply.add_argument("--timeout-ms", type=int, default=10000)
    args = parser.parse_args()
    if args.mode in ("example", "recover-example"):
        with EXAMPLES.open(encoding="utf-8") as source:
            case = next(s for s in json.load(source)["scenarios"] if s["name"] == "lost_response_retry")
        fresh = next(e for e in case["exchanges"] if e["step"] == "fresh_status")

        def replay(query):
            if query["action"] == "set_profile":
                raise ConnectionResetError("Risposta simulata persa")
            return dict(fresh["helper_response"], request_id=query["request_id"])

        if args.mode == "recover-example":
            result = apply_profile(case["request"], replay)
        else:
            result = reconcile_status(case["request"], replay)
    elif args.mode == "apply":
        if (not IDENTIFIER.fullmatch(args.policy_id) or not IDENTIFIER.fullmatch(args.run_id)
                or args.run_id in (".", "..") or args.policy_version <= 0
                or not 1 <= len(args.reason) <= 256 or not 100 <= args.timeout_ms <= 30000):
            parser.error("Identificativo, versione, motivo o timeout fuori dai limiti del contratto")
        command = vars(args).copy()
        del command["mode"]
        command.update(schema_version=1, message_type="request",
                       action="set_profile", request_id=uuid.uuid4().hex)
        result = apply_profile(command)
    else:
        result = reconcile_status(vars(args))
    print(json.dumps(result))
    if args.mode == "apply":
        return int(result["outcome"] != args.required_profile + "_ACTIVE")
    return int(result["outcome"] == "UNKNOWN")


if __name__ == "__main__":
    raise SystemExit(main())
