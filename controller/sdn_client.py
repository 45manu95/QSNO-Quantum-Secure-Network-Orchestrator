"""Client per applicare blocchi SDN attraverso l'API locale di Ryu."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


API_URL = "http://127.0.0.1:8080"
SERVER_IP = "10.0.0.1"
CLASSIC_PORT = 4433

CLIENTS = {
    "iot": {"ip": "10.0.0.2", "cookie": 4097},
    "drone": {"ip": "10.0.0.3", "cookie": 4098},
}


def set_classic_block(target, blocked):
    """Invia la modifica a Ryu; non certifica l'effetto sul traffico."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["block", "unblock"])
    parser.add_argument("target", choices=CLIENTS)
    args = parser.parse_args()

    try:
        set_classic_block(args.target, blocked=args.action == "block")
    except (HTTPError, URLError, OSError, ValueError, RuntimeError) as error:
        print(f"ERRORE: richiesta SDN fallita: {error}", file=sys.stderr)
        return 1

    print(
        f"Ryu ha accettato: {args.action} {args.target}, "
        f"server {SERVER_IP}:{CLASSIC_PORT}."
    )
    print("L'effetto sul traffico deve essere verificato separatamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())