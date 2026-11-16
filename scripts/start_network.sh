#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# Verifica la disponibilità del comando Mininet.
if ! command -v mn >/dev/null 2>&1; then
    echo "Errore: comando mn non trovato." >&2
    exit 1
fi

# Controlla che un servizio risponda sulla porta del controller.
if ! python3 -c '
import socket
import sys

try:
    with socket.create_connection(("127.0.0.1", 6653), timeout=2):
        pass
except OSError:
    sys.exit(1)
'; then
    echo "Errore: controller non raggiungibile su 127.0.0.1:6653." >&2
    echo "Avvia prima: bash scripts/start_controller.sh" >&2
    exit 1
fi

sudo -v

# Verifica che Open vSwitch sia raggiungibile.
if ! sudo ovs-vsctl show >/dev/null; then
    echo "Errore: Open vSwitch non è disponibile." >&2
    exit 1
fi

# Evita di sovrapporre la prova a uno switch già presente.
if sudo ovs-vsctl br-exists s1; then
    echo "Errore: esiste già lo switch s1." >&2
    echo "Controlla se una prova è ancora attiva, anche con Manuel." >&2
    exit 1
fi

exec sudo mn \
    --custom "$PROJECT_ROOT/topology/qsno_topology.py" \
    --topo qsno \
    --switch ovsk \
    --controller remote,ip=127.0.0.1,port=6653