"""Client per applicare blocchi SDN attraverso l'API locale di Ryu."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
import time


API_URL = "http://127.0.0.1:8080"
SERVER_IP = "10.0.0.1"
CLASSIC_PORT = 4433

CLIENTS = {
    "iot": {"ip": "10.0.0.2", "cookie": 4097},
    "drone": {"ip": "10.0.0.3", "cookie": 4098},
}

def get_switch_flows(timeout=2):
    """Legge le regole; una risposta incompleta è un errore."""
    opener = build_opener(ProxyHandler({}))
    request = Request(API_URL + "/stats/flow/1", method="GET")

    with opener.open(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Lettura regole: HTTP {response.status}")
        data = json.load(response)

    if not isinstance(data, dict) or not isinstance(data.get("1"), list):
        raise RuntimeError("Risposta senza regole valide dello switch 1")

    flows = data["1"]
    if not all(isinstance(flow, dict) for flow in flows):
        raise RuntimeError("Formato delle regole non valido")

    return flows


def verify_classic_block(target, blocked, timeout=5):
    """Attende lo stato richiesto nelle statistiche dello switch."""
    client = CLIENTS[target]
    expected_match = {
        "dl_type": 2048,
        "nw_src": client["ip"],
        "nw_dst": SERVER_IP,
        "nw_proto": 6,
        "tp_dst": CLASSIC_PORT,
    }
    deadline = time.monotonic() + timeout

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Stato richiesto non osservato per {target}"
            )

        flows = get_switch_flows(timeout=min(2, remaining))
        owned = [
            flow for flow in flows
            if flow.get("cookie") == client["cookie"]
        ]

        if blocked:
            verified = (
                len(owned) == 1
                and owned[0].get("table_id") == 0
                and owned[0].get("priority") == 100
                and owned[0].get("match") == expected_match
                and owned[0].get("actions") == []
                and owned[0].get("idle_timeout") == 0
                and owned[0].get("hard_timeout") == 0
            )
        else:
            # Il cookie è riservato al blocco di questo client.
            verified = not owned

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Verifica scaduta per {target}"
            )

        if verified:
            return

        time.sleep(min(0.2, max(0, deadline - time.monotonic())))

def set_classic_block(target, blocked):
    """Invia la modifica e restituisce il risultato della verifica."""
    started = time.monotonic()

    if target not in CLIENTS:
        raise ValueError(f"Client sconosciuto: {target}")

    client = CLIENTS[target]
    payload = {
        "dpid": 1,
        "cookie": client["cookie"],
        "table_id": 0,
        "priority": 100,
        "match": {
            "eth_type": 2048,
            "ip_proto": 6,
            "ipv4_src": client["ip"],
            "ipv4_dst": SERVER_IP,
            "tcp_dst": CLASSIC_PORT,
        },
    }

    if blocked:
        endpoint = "/stats/flowentry/add"
        payload["actions"] = []
    else:
        endpoint = "/stats/flowentry/delete_strict"
        payload["cookie_mask"] = 0xFFFFFFFFFFFFFFFF

    request = Request(
        API_URL + endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # Non usare eventuali proxy configurati nell'ambiente.
    opener = build_opener(ProxyHandler({}))

    with opener.open(request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"Risposta HTTP inattesa: {response.status}")
        response.read()

    verify_classic_block(target, blocked)
    return {
        "target_id": target,
        "action": "block" if blocked else "unblock",
        "dpid": 1,
        "cookie": client["cookie"],
        "server_ip": SERVER_IP,
        "server_port": CLASSIC_PORT,
        "status": "RULE_VERIFIED",
        "verification": "flow_stats",
        "request_and_verification_ms": round(
            (time.monotonic() - started) * 1000, 3
        ),
        "traffic_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["block", "unblock"])
    parser.add_argument("target", choices=CLIENTS)
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Stampa il risultato in formato JSON",
    )
    args = parser.parse_args()
    started = time.monotonic()

    try:
        result = set_classic_block(
            args.target,
            blocked=args.action == "block",
        )
    except (HTTPError, URLError, OSError, ValueError, RuntimeError) as error:
        if args.json_output:
            result = {
                "target_id": args.target,
                "action": args.action,
                "status": "ERROR",
                "rule_state": "UNKNOWN",
                "error_type": type(error).__name__,
                "error": str(error),
                "elapsed_ms": round(
                    (time.monotonic() - started) * 1000, 3
                ),
                "traffic_verified": False,
            }
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(
                f"ERRORE: richiesta SDN fallita: {error}",
                file=sys.stderr,
            )
        return 1

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"Regola verificata sullo switch: "
            f"{result['action']} {result['target_id']}, "
            f"server {SERVER_IP}:{CLASSIC_PORT}."
        )
        print(
            "Tempo richiesta e verifica: "
            f"{result['request_and_verification_ms']} ms."
        )
        print("L'effetto sul traffico deve essere verificato separatamente.")

    return 0


if __name__ == "__main__":
    sys.exit(main())