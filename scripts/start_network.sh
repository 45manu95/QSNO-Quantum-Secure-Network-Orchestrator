#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

exec sudo mn \
    --custom "$PROJECT_ROOT/topology/qsno_topology.py" \
    --topo qsno \
    --switch ovsk \
    --controller remote,ip=127.0.0.1,port=6653