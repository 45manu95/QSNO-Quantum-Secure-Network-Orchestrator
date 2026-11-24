"""Ripete la misura evento → regola verificata per il drone, sulla topologia già avviata."""

import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

from controller.sdn_client import CLIENTS, get_switch_flows, set_classic_block


def write_record(output, record):
    output.write(json.dumps(record, ensure_ascii=False) + "\n")
    output.flush()


def collect(output, batch, network, repeats):
    times = []
    attempted = 0
    target = "drone"
    root = Path(__file__).resolve().parents[1]
    for sample in range(1, repeats + 1):
        # La lettura preliminare è fuori dall'intervallo misurato. Una regola
        # preesistente può appartenere a una prova altrui: lasciarla attiva.
        if any(f["cookie"] == CLIENTS[target]["cookie"] for f in get_switch_flows()):
            raise RuntimeError("Regola 0x1002 già presente prima della prova; verifica chi la sta usando")
        run = "{}-{:02d}".format(batch, sample)
        stamp = datetime.now(timezone.utc).isoformat()
        event = dict(event_id="E{}".format(sample), target_id=target, severity="high",
                     source="lab", timestamp=stamp)
        command = [sys.executable, "-B", "-m", "orchestrator.risk_events", "listen", run, target,
                   "--client", "CLASSIC", "HYBRID", "--server", "CLASSIC", "HYBRID",
                   "--network", network]
        record = dict(sample=sample, run_id=run, timestamp_utc=stamp, network_profile=network)
        attempted += 1
        try:
            proc = subprocess.run(command, input=json.dumps(event) + "\n", cwd=root,
                                  capture_output=True, text=True, timeout=40, check=True)
            result = json.loads(proc.stdout)
            if (result.get("run_id") != run or result.get("event_id") != event["event_id"]
                    or result.get("sdn_action") != "block" or result.get("mode") != "listen"):
                raise ValueError("Risposta del lettore inattesa")
            record.update(result)
            value = result.get("event_to_sdn_verified_ms")
            if result.get("sdn") == "RULE_VERIFIED" and type(value) in (int, float) and value >= 0:
                times.append(value)
            elif result.get("sdn") == "RULE_VERIFIED":
                raise ValueError("Regola verificata senza un tempo valido")
        except (ValueError, subprocess.SubprocessError, OSError) as error:
            record["measurement_error"] = str(getattr(error, "stderr", "") or error).strip()
        finally:
            try:
                write_record(output, record)
            finally:
                try:
                    set_classic_block(target, blocked=False)
                except (ValueError, RuntimeError, OSError) as error:
                    write_record(output, dict(run_id=run, cleanup_error=str(error)))
                    raise RuntimeError("Ripristino del drone non verificato: {}".format(error)) from error
    summary = dict(tentativi=attempted, sdn_verificati=len(times),
                   senza_misura_sdn=attempted - len(times))
    if times:
        summary["evento_a_regola_ms"] = {
            "min": round(min(times), 3), "mediana": round(median(times), 3),
            "media": round(mean(times), 3), "max": round(max(times), 3)}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", required=True, choices=("nominal", "degraded"),
                        help="Profilo già attivo in Mininet")
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("Il numero di ripetizioni deve essere positivo")
    directory = Path.home() / "qsno-misure"
    directory.mkdir(exist_ok=True)
    batch = "drone_high_blocco-classic_{}_{}".format(
        args.network, datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    path = directory / (batch + ".jsonl")
    try:
        with (directory / ".drone.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with path.open("x", encoding="utf-8") as output:
                print("File:", path, flush=True)
                summary = collect(output, batch, args.network, args.repeats)
        print(json.dumps(summary, ensure_ascii=False))
        return int(bool(summary["senza_misura_sdn"]))
    except (OSError, ValueError, RuntimeError) as error:
        print("Serie interrotta:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
