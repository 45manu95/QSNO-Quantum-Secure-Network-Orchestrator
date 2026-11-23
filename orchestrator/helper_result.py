"""Interpreta gli esiti simulati di set_profile per una singola chiamata QSNO."""

import argparse
import json
from pathlib import Path


GROUPS = {"CLASSIC": "X25519", "HYBRID": "X25519MLKEM768"}
EXAMPLES = Path(__file__).resolve().parents[1] / "contracts" / "qsno-helper-v1.examples.json"


def confirmed_active(state, profile):
    active = profile + "_ACTIVE"
    return (state.get("status") == active and state.get("observed_profile") == profile
            and state.get("observed_group") == GROUPS[profile]
            and state.get("certificate_ok") is True and state.get("application_ack") is True
            and isinstance(state.get("connection_id"), str) and bool(state["connection_id"])
            and type(state.get("last_acked_seq")) is int and state["last_acked_seq"] >= 0
            and isinstance(state.get("supported_profiles"), list)
            and profile in state["supported_profiles"])


def interpret_set_profile(request, response):
    """Restituisce l'esito della chiamata, senza modificare lo stato SDN o TLS."""
    if request["action"] != "set_profile" or request["required_profile"] not in GROUPS:
        raise ValueError("È richiesta una chiamata set_profile per CLASSIC o HYBRID")
    if not isinstance(response, dict):
        return {"outcome": "UNKNOWN"}
    if (type(response.get("schema_version")) is not int
            or response["schema_version"] != 1 or response.get("message_type") != "response"):
        return {"outcome": "UNKNOWN"}
    for key in ("request_id", "run_id", "target_id", "action"):
        if response.get(key) != request[key]:
            return {"outcome": "UNKNOWN"}

    state = response.get("state")
    if not isinstance(state, dict):
        return {"outcome": "UNKNOWN"}
    version = state.get("policy_version")
    if type(version) is not int:
        return {"outcome": "UNKNOWN"}

    error = response.get("error")
    if response.get("ok") is False and isinstance(error, dict):
        if error.get("code") == "stale_policy" and version >= request["policy_version"]:
            # Il comando è stato rifiutato. Questo esito non aggiorna lo stato corrente.
            return {"outcome": "REJECTED", "code": "stale_policy"}

    profile = request["required_profile"]
    if (version != request["policy_version"] or state.get("policy_id") != request["policy_id"]
            or state.get("desired_profile") != profile):
        return {"outcome": "UNKNOWN"}

    if response.get("ok") is False and isinstance(error, dict) and error.get("code") == "timeout":
        if (state.get("status") == "BLOCKED" and state.get("application_ack") is False
                and state.get("certificate_ok") is False
                and all(key in state and state[key] is None
                        for key in ("connection_id", "observed_group", "observed_profile"))):
            return {"outcome": "BLOCKED", "code": "timeout", "phase": error.get("phase")}
        return {"outcome": "UNKNOWN"}

    if (response.get("ok") is True and "error" in response and error is None
            and confirmed_active(state, profile)):
        return {"outcome": profile + "_ACTIVE", "connection_id": state["connection_id"]}
    return {"outcome": "UNKNOWN"}


def main():
    with EXAMPLES.open(encoding="utf-8") as source:
        scenarios = {s["name"]: s for s in json.load(source)["scenarios"]
                     if s["request"]["action"] == "set_profile" and "exchanges" not in s}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=sorted(scenarios))
    scenario = scenarios[parser.parse_args().scenario]
    result = interpret_set_profile(scenario["request"], scenario["response"])
    print(json.dumps(result))


if __name__ == "__main__":
    main()
