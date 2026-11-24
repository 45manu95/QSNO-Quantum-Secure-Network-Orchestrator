"""Misura dieci nuove connessioni TLS dal drone usando la sonda QSNO."""

import argparse
import json
import math
import re
import shlex
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROFILES = {
    "classic": ("4433", "X25519"),
    "hybrid": ("4434", "X25519MLKEM768"),
}


UDP_SECONDS = 14


def probe_once(command, request_id):
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=20)
        data = json.loads(proc.stdout)
        if not isinstance(data, dict) or data.get("request_id") != request_id:
            raise ValueError("Risposta della sonda non riconosciuta")
        if proc.returncode and data.get("ok") is True:
            data.update(ok=False, error_code="inconsistent_result")
        return data
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {"request_id": request_id, "ok": False, "error_code": "probe_error",
                "error_detail": str(error)}


def loaded_probe(command, request_id, mbps, log, udp_port):
    """Un flusso UDP per tentativo; conserva il rapporto restituito dal ricevitore."""
    sender_args = ["iperf", "-u", "-c", "10.0.0.1", "-B", "10.0.0.3", "-p", str(udp_port),
                   "-b", "{}M".format(mbps), "-t", str(UDP_SECONDS), "-f", "m"]
    with log.open("x", encoding="utf-8") as output:
        start = time.monotonic()
        sender = subprocess.Popen(sender_args, stdout=output, stderr=subprocess.STDOUT)
        try:
            time.sleep(2)
            if sender.poll() is not None:
                raise RuntimeError("Generatore UDP terminato prima della sonda: " + str(log))
            data = probe_once(command, request_id)
            overlap = sender.poll() is None and time.monotonic() - start < UDP_SECONDS
            try:
                sender.wait(timeout=UDP_SECONDS + 5)
            except subprocess.TimeoutExpired:
                sender.kill()
                sender.wait()
        finally:
            if sender.poll() is None:
                sender.kill()
                sender.wait()
    wall_seconds = time.monotonic() - start
    report = log.read_text(encoding="utf-8", errors="replace").partition("Server Report:")[2]
    interval = re.search(r"([\d.]+)\s*-\s*([\d.]+)\s+sec", report)
    rx_seconds = float(interval[2]) - float(interval[1]) if interval else None
    # Il report arriva prima che il client termini. 0,15 s coprono
    # l'arrotondamento dei tempi stampati da iperf al decimo di secondo.
    plausible = rx_seconds is not None and 0 < rx_seconds <= wall_seconds + 0.15
    data["udp_sender_process_seconds"] = round(wall_seconds, 3)
    data["udp_report_seconds"] = rx_seconds
    rate = re.search(r"([\d.]+)\s+Mbits/sec", report)
    loss = re.search(r"(\d+)\s*/\s*(\d+)\s*\(", report)
    data["udp_report_log"] = log.name
    data["udp_receiver_mbps"] = float(rate.group(1)) if rate else None
    data["udp_lost_datagrams"] = int(loss.group(1)) if loss else None
    data["udp_total_datagrams"] = int(loss.group(2)) if loss else None
    data["udp_window_verified"] = bool(plausible and overlap and sender.returncode == 0 and rate
                                       and data["udp_receiver_mbps"] > 0)
    return data


def measure(network, probe, crypto, output_root, profile="hybrid", udp_mbps=0,
            samples=10, udp_port=5501, trial_id=None):
    port, expected_group = PROFILES[profile]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = output_root / ("drone_tls_{}_{}_udp{}M_{}".format(profile, network, udp_mbps, stamp))
    directory.mkdir(parents=True, exist_ok=False)
    results = directory / "misure.jsonl"
    print("File:", results, flush=True)
    times = []
    rates = []
    successes = 0
    attempted = 0
    errors = Counter()
    with results.open("x", encoding="utf-8") as stream:
        for sample in range(1, samples + 1):
            request_id = "{}-{:02d}".format(stamp, sample)
            command = [
                sys.executable, "-B", str(probe), "probe", "--profile", profile,
                "--host", "10.0.0.1", "--port", port, "--server-name", "qsno-server",
                "--openssl", str(crypto / "openssl-3.5.9/bin/openssl"),
                "--ca", str(crypto / "tls-lab/ca.crt"), "--log-dir", str(directory / "probe"),
                "--request-id", request_id, "--timeout", "10",
            ]
            attempted += 1
            if udp_mbps:
                log = directory / "iperf-{:02d}.log".format(sample)
                data = loaded_probe(command, request_id, udp_mbps, log, udp_port)
                if data["udp_window_verified"]:
                    rates.append(data["udp_receiver_mbps"])
            else:
                data = probe_once(command, request_id)
            if data.get("ok") is True:
                ms = data.get("probe_elapsed_ms")
                if (data.get("tls_version") == "TLSv1.3"
                        and str(data.get("group_observed")).casefold() == expected_group.casefold()
                        and data.get("certificate_verified") is True
                        and data.get("application_response_ok") is True
                        and type(ms) in (int, float) and math.isfinite(ms) and ms >= 0):
                    successes += 1
                    if not udp_mbps or data["udp_window_verified"]:
                        times.append(ms)
                else:
                    data.update(ok=False, error_code="inconsistent_result")
            if data.get("ok") is not True:
                errors[data.get("error_code") or "unknown"] += 1
            data.update(sample=sample, network_profile=network, profile_requested=profile,
                        udp_offered_mbps=udp_mbps)
            if trial_id is not None:
                data["trial_id"] = trial_id
            stream.write(json.dumps(data) + "\n")
            stream.flush()
            print("{:2d}/{}  {}".format(sample, samples, data.get("error_code") or
                                         "{} ms".format(data.get("probe_elapsed_ms"))), flush=True)
            if udp_mbps and not data["udp_window_verified"]:
                print("Serie interrotta: carico non confermato. Log:", log, file=sys.stderr)
                break
    summary = {"rete": network, "profilo_tls": profile, "tentativi": attempted,
               "riusciti": successes, "errori": dict(errors), "udp_offerto_mbps": udp_mbps,
               "tempi_validi": len(times)}
    if trial_id is not None:
        summary["trial_id"] = trial_id
    if rates:
        summary["udp_ricevuto_mbps_mediana"] = statistics.median(rates)
    if times:
        summary["probe_elapsed_ms"] = {
            "min": min(times), "mediana": round(statistics.median(times), 3),
            "media": round(statistics.mean(times), 3), "max": max(times)}
    print(json.dumps(summary))
    return int(len(times) != samples)


def isolated_series(server, drone, mbps, samples=10):
    """Dal prompt py di Mininet: ricevitore dedicato a ciascuna sonda."""
    if mbps not in (5, 9) or samples < 1:
        raise ValueError("Carico o numero di prove non valido")
    port = 5511
    def listeners():
        out, err, code = server.pexec(["ss", "-H", "-lun", "sport = :5511"])
        if code:
            raise RuntimeError("Verifica porta UDP fallita: " + (err or out).strip())
        return out.strip()
    times, rates = [], []
    existing = listeners()
    if existing:
        raise RuntimeError("Porta UDP 5511 occupata su h_server: " + existing)
    for sample in range(1, samples + 1):
        receiver = server.popen(["iperf", "-s", "-u", "-B", "10.0.0.1", "-p", str(port)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(30):
                if receiver.poll() is not None:
                    raise RuntimeError("Avvio ricevitore UDP fallito")
                if "10.0.0.1:5511" in listeners():
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Ricevitore UDP non pronto")
            trial_id = uuid4().hex
            cmd = ["timeout", "-k", "3s", "50s", "runuser", "-u", "mininet", "--",
                   "python3", "-B", str(Path(__file__).resolve()),
                   "--network", "nominal", "--profile", "hybrid", "--udp-mbps", str(mbps),
                   "--samples", "1", "--udp-port", str(port), "--trial-id", trial_id]
            # La shell persistente appartiene già al cgroup CPU del drone.
            output = drone.cmd(shlex.join(cmd)) or ""
            print("Prova {}/{}\n{}".format(sample, samples, output.rstrip()), flush=True)
            try:
                result = json.loads(output.strip().splitlines()[-1])
            except (IndexError, ValueError) as error:
                raise RuntimeError("Riepilogo della sonda assente: " +
                                   (output.strip() or "nessun output")) from error
            expected = {"trial_id": trial_id, "udp_offerto_mbps": mbps,
                        "rete": "nominal", "profilo_tls": "hybrid", "tentativi": 1}
            if not isinstance(result, dict) or any(result.get(k) != v for k, v in expected.items()):
                raise RuntimeError("Risposta non corrispondente alla prova richiesta, esclusa dal riepilogo")
            if "udp_ricevuto_mbps_mediana" not in result:
                raise RuntimeError("Intervallo o rapporto UDP non valido; controllare il log indicato")
            rates.append(result["udp_ricevuto_mbps_mediana"])
            if result["tempi_validi"]:
                times.append(result["probe_elapsed_ms"]["mediana"])
        finally:
            if receiver.poll() is None:
                receiver.terminate()
                try:
                    receiver.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    receiver.kill()
                    receiver.wait()
    print(json.dumps({"udp_offerto_mbps": mbps, "tentativi": samples, "riusciti": len(times),
                      "udp_ricevuto_mbps_mediana": round(statistics.median(rates), 3),
                      "probe_elapsed_ms_mediana": statistics.median(times) if times else None}))


def main():
    crypto = Path("/home/mininet/qsno-crypto")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", required=True, choices=("degraded", "nominal"))
    parser.add_argument("--profile", choices=PROFILES, default="hybrid")
    parser.add_argument("--udp-mbps", type=int, choices=(0, 5, 9), default=0)
    parser.add_argument("--udp-port", type=int, default=5501)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--trial-id", help="Identificatore della chiamata da Mininet")
    parser.add_argument("--probe", type=Path, default=crypto / "qsno_tls.py")
    args = parser.parse_args()
    if args.samples < 1 or not 1 <= args.udp_port <= 65535:
        parser.error("Numero di prove o porta UDP non validi")
    if not args.probe.is_file():
        parser.error("Sonda assente in {}. Specificare il percorso con --probe.".format(args.probe))
    try:
        return measure(args.network, args.probe, crypto, Path.home() / "qsno-misure",
                       args.profile, args.udp_mbps, args.samples, args.udp_port, args.trial_id)
    except (OSError, RuntimeError) as error:
        parser.exit(1, "Serie interrotta: {}\n".format(error))


if __name__ == "__main__":
    sys.exit(main())
