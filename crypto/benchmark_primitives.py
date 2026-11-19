#!/usr/bin/env python3
"""Run the QSNO liboqs baseline and retain raw output, failures and run means.

Uses only the Python 3.8+ standard library. Summary quantiles describe the
distribution of per-run mean times, not individual cryptographic operations.
"""

import argparse
import csv
import json
import math
import platform
import random
import re
import shutil
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_COMMIT = "5a1a854b0dc9f2141bdc771c555ee60c37950183"
ALGORITHMS = (
    ("ML-KEM-768", "kem", ("keygen", "encaps", "decaps")),
    ("ML-DSA-44", "sig", ("keypair", "sign", "verify")),
    ("Falcon-512", "sig", ("keypair", "sign", "verify")),
)
FIELDS = (
    "algorithm", "repeat", "execution_order", "operation", "iterations",
    "total_s", "mean_us", "within_run_stddev_us", "cpu_cycles_mean",
    "within_run_cpu_cycles_stddev", "last_signature_bytes",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_cache(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith(("#", "//")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.split(":", 1)[0]] = value
    return values


def capture(command, cwd):
    return subprocess.check_output(
        command, cwd=str(cwd), text=True, stderr=subprocess.STDOUT, timeout=15
    ).strip()


def run_logged(command, path, cwd, timeout):
    with path.open("w", encoding="utf-8") as log:
        try:
            result = subprocess.run(
                [str(arg) for arg in command], cwd=str(cwd),
                stdout=log, stderr=subprocess.STDOUT, timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Tempo massimo superato. Leggi: {}".format(path)) from error
    if result.returncode != 0:
        raise RuntimeError(
            "Comando terminato con codice {}. Leggi: {}".format(result.returncode, path)
        )
    return path.read_text(encoding="utf-8", errors="replace")


def number(value):
    parsed = float(value.strip())
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError("Valore numerico non valido: {}".format(value))
    return parsed


def optional_number(value):
    value = value.strip()
    if value.lower() in ("", "na", "n/a"):
        return None
    return number(value)


def parse_output(text, algorithm, expected_operations):
    if not any(
        line.split("|", 1)[0].strip() == algorithm
        for line in text.splitlines() if "|" in line
    ):
        raise ValueError("Il risultato non contiene l'algoritmo {}".format(algorithm))
    rows = []
    seen = set()
    last_signature = re.search(r"Actual signature length returned \((\d+)\)", text)
    for line in text.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 7 or parts[0] not in expected_operations:
            continue
        operation = parts[0]
        if operation in seen:
            raise ValueError("Operazione duplicata: {}".format(operation))
        seen.add(operation)
        row = {
            "algorithm": algorithm,
            "operation": operation,
            "iterations": int(parts[1]),
            "total_s": number(parts[2]),
            "mean_us": number(parts[3]),
            "within_run_stddev_us": number(parts[4]),
            "cpu_cycles_mean": optional_number(parts[5]),
            "within_run_cpu_cycles_stddev": optional_number(parts[6]),
            "last_signature_bytes": int(last_signature.group(1)) if last_signature else None,
        }
        if row["iterations"] <= 0 or row["mean_us"] <= 0 or row["total_s"] <= 0:
            raise ValueError("Misura vuota per {} {}".format(algorithm, operation))
        rows.append(row)
    if seen != set(expected_operations):
        raise ValueError("Operazioni mancanti per {}: {}".format(
            algorithm, sorted(set(expected_operations) - seen)))
    return rows


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows, repetitions):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["algorithm"], row["operation"])].append(row["mean_us"])
    summary = []
    for algorithm, _, operations in ALGORITHMS:
        for operation in operations:
            times = groups[(algorithm, operation)]
            if len(times) != repetitions:
                raise ValueError("Numero di misure inatteso per {} {}".format(algorithm, operation))
            q1, _, q3 = statistics.quantiles(times, n=4, method="inclusive")
            summary.append({
                "algorithm": algorithm, "operation": operation,
                "runs": len(times), "median_of_run_means_us": statistics.median(times),
                "q1_of_run_means_us": q1, "q3_of_run_means_us": q3,
                "min_run_mean_us": min(times), "max_run_mean_us": max(times),
            })
    return summary


def main():
    parser = argparse.ArgumentParser(description="Prove ripetute liboqs per QSNO")
    parser.add_argument("--source", type=Path, default=Path.home() / "qsno-crypto/src/liboqs-0.16.0")
    parser.add_argument("--output", type=Path, help="Nuova cartella per i risultati; deve essere assente")
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--duration", type=int, default=1, help="Secondi per ogni operazione")
    parser.add_argument("--seed", type=int, default=20261118)
    args = parser.parse_args()
    if args.repetitions < 2 or args.duration < 1:
        parser.error("Servono almeno 2 ripetizioni e una durata di almeno 1 secondo")
    source = args.source.expanduser().resolve()
    cache_path = source / "build/CMakeCache.txt"
    if not cache_path.is_file():
        parser.error("Non trovo la compilazione liboqs: {}".format(cache_path))
    cache = read_cache(cache_path)
    expected = {
        "CMAKE_BUILD_TYPE": "Release", "OQS_USE_OPENSSL": "OFF",
        "OQS_LIBJADE_BUILD": "OFF", "BUILD_SHARED_LIBS": "ON",
        "OQS_DIST_BUILD": "ON",
    }
    for key, value in expected.items():
        if cache.get(key) != value:
            parser.error("Configurazione diversa: {}={}, atteso {}. Non modifico nulla.".format(
                key, cache.get(key, "assente"), value))
    required_algorithms = {"KEM_ml_kem_768", "SIG_ml_dsa_44", "SIG_falcon_512"}
    if set(cache.get("OQS_MINIMAL_BUILD", "").split(";")) != required_algorithms:
        parser.error("La selezione OQS_MINIMAL_BUILD non corrisponde ai tre algoritmi previsti")
    commit = capture(["git", "rev-parse", "HEAD"], source)
    if commit != EXPECTED_COMMIT:
        parser.error("Il codice liboqs non corrisponde alla release fissata dal progetto: {}".format(commit))
    for name in ("test_kem", "test_sig", "speed_kem", "speed_sig"):
        if not (source / "build/tests" / name).is_file():
            parser.error("Programma di prova mancante: {}".format(name))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = (args.output or Path.home() / "qsno-crypto/results/liboqs-0.16.0" / ("series-" + stamp)).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    (output / "checks").mkdir()
    shutil.copyfile(cache_path, output / "CMakeCache.txt")
    schedule = [(algorithm, kind, operations, repeat)
                for repeat in range(1, args.repetitions + 1)
                for algorithm, kind, operations in ALGORITHMS]
    random.Random(args.seed).shuffle(schedule)
    metadata = {
        "started_utc": utc_now(), "status": "running", "source": str(source),
        "git_commit": commit,
        "tracked_changes": capture(["git", "status", "--porcelain", "--untracked-files=no"], source),
        "platform": platform.platform(), "machine": platform.machine(),
        "python": platform.python_version(), "repetitions": args.repetitions,
        "duration_per_operation_s": args.duration, "seed": args.seed,
        "configuration": {key: cache.get(key) for key in (*expected, "OQS_MINIMAL_BUILD", "OQS_OPT_TARGET")},
        "schedule": [{"algorithm": a, "repeat": r} for a, _, _, r in schedule],
        "summary_definition": "Quantiles across per-run mean times; not per-operation latency quantiles.",
        "signature_length_note": "last_signature_bytes is the last sampled signature, not an average.",
        "correctness_checks": {},
    }

    def save_metadata():
        (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    save_metadata()
    print("Risultati: {}".format(output), flush=True)
    try:
        for algorithm, kind, _ in ALGORITHMS:
            log = output / "checks" / (algorithm + ".txt")
            text = run_logged([source / "build/tests" / ("test_" + kind), algorithm], log, source, 60)
            success = "shared secrets are equal" if kind == "kem" else "verification passes as expected"
            if success not in text:
                raise RuntimeError("Esito della prova non riconosciuto. Leggi: {}".format(log))
            metadata["correctness_checks"][algorithm] = "passed"
            save_metadata()
            print("Prova di funzionamento {}: OK".format(algorithm), flush=True)
        rows = []
        for order, (algorithm, kind, operations, repeat) in enumerate(schedule, 1):
            log = output / "raw" / ("{}-{:02d}.txt".format(algorithm, repeat))
            print("[{}/{}] {} - ripetizione {}".format(order, len(schedule), algorithm, repeat), flush=True)
            text = run_logged([
                source / "build/tests" / ("speed_" + kind), "-d", args.duration, "-i", algorithm,
            ], log, source, max(60, args.duration * 6 + 15))
            parsed = parse_output(text, algorithm, operations)
            for row in parsed:
                row.update(repeat=repeat, execution_order=order)
            rows.extend(parsed)
        summary = summarize(rows, args.repetitions)
        write_csv(output / "measurements.csv", FIELDS, rows)
        write_csv(output / "summary.csv", tuple(summary[0]), summary)
        lines = [
            "QSNO - Tempi in microsecondi (us)",
            "Mediana delle medie delle singole esecuzioni; Q1 e Q3 delimitano il 50% centrale.",
            "", "Algoritmo | Operazione | Prove | Mediana us | Q1 us | Q3 us",
        ]
        for row in summary:
            lines.append("{algorithm} | {operation} | {runs} | {median_of_run_means_us:.3f} | {q1_of_run_means_us:.3f} | {q3_of_run_means_us:.3f}".format(**row))
        report = "\n".join(lines) + "\n"
        (output / "summary.txt").write_text(report, encoding="utf-8")
        metadata.update(status="complete", ended_utc=utc_now(), raw_files=len(schedule), measurement_rows=len(rows))
        save_metadata()
        print("\n" + report, flush=True)
        print("COMPLETATO: {} file grezzi, {} misure, {} righe nel riepilogo.".format(len(schedule), len(rows), len(summary)))
        return 0
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt) as error:
        metadata.update(status="failed" if not isinstance(error, KeyboardInterrupt) else "interrupted", ended_utc=utc_now(), error=str(error))
        save_metadata()
        print("PROVA INTERROTTA: {}\nConservo i file gia prodotti in {}".format(error, output), file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("ERRORE: {}".format(error), file=sys.stderr)
        sys.exit(1)
