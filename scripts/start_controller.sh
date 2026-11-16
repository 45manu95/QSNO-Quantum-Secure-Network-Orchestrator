#!/usr/bin/env bash
set -euo pipefail

RYU_MANAGER="$HOME/venvs/qsno-ryu/bin/ryu-manager"

if [[ ! -x "$RYU_MANAGER" ]]; then
    echo "Ryu non trovato: $RYU_MANAGER" >&2
    exit 1
fi

exec "$RYU_MANAGER" \
    --ofp-listen-host 127.0.0.1 \
    --ofp-tcp-listen-port 6653 \
    --wsapi-host 127.0.0.1 \
    --wsapi-port 8080 \
    ryu.app.simple_switch_13 \
    ryu.app.ofctl_rest