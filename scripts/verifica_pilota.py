"""Ricalcola le mediane del pilota del 23 novembre dai JSONL espliciti della VM."""
import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path


def tls_paths(profile, network, times, load=None):
    prefix = "drone_tls_{}_{}".format(profile, network)
    if load is not None:
        prefix += "_udp{}M".format(load)
    return [prefix + "_20261123T" + stamp + "Z/misure.jsonl" for stamp in times.split()]


# Per ogni riga: metrica, rete, profilo TLS, carico, mediana ms, mediana UDP, file.
SERIES = [
    ("sdn", "nominal", None, None, 6.535, None,
     ["drone_high_blocco-classic_nominal_20261123T155255640399Z.jsonl"]),
    ("sdn", "degraded", None, None, 6.331, None,
     ["drone_high_blocco-classic_degraded_20261123T155559628082Z.jsonl"]),
    ("tls", "nominal", "classic", None, 66.950, None, tls_paths("classic", "nominal", "161711048215")),
    ("tls", "degraded", "classic", None, 386.388, None, tls_paths("classic", "degraded", "162004622982")),
    ("tls", "nominal", "hybrid", None, 61.335, None, tls_paths("hybrid", "nominal", "160829069380")),
    ("tls", "degraded", "hybrid", None, 383.467, None, tls_paths("hybrid", "degraded", "160648464624")),
    ("tls", "nominal", "hybrid", 0, 58.338, None, tls_paths("hybrid", "nominal", "162741453459", 0)),
    ("tls", "nominal", "hybrid", 5, 60.293, 5.240, tls_paths("hybrid", "nominal",
     "164703173403 164717304688 164731440954 164745595338 164759746251 "
     "164813878493 164827999044 164842132596 164856291940 164910508454", 5)),
    ("tls", "nominal", "hybrid", 9, 1349.034, 8.435, tls_paths("hybrid", "nominal",
     "164938799077 164954126158 165009415941 165024913698 165040500330 "
     "165055819401 165111183141 165126241310 165141710555 165932879473", 9)),
]


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("misura numerica non valida")
    return value


def audit(root, series):
    metric, network, profile, load, expected, expected_rate, names = series
    times, rates, files, ids = [], [], [], set()
    for name in names:
        raw = (root / name).read_bytes()
        files.append({"file": name, "sha256": hashlib.sha256(raw).hexdigest()})
        lines = raw.decode("utf-8").splitlines()
        if len(lines) != (1 if len(names) > 1 else 10):
            raise ValueError(name + ": numerosità inattesa")
        for line in lines:
            row = json.loads(line)
            if metric == "sdn":
                key = row["run_id"]
                valid = (row["target_id"] == "drone" and row["sdn"] == "RULE_VERIFIED"
                         and row["sdn_action"] == "block" and row["severity"] == "high")
                value = row["event_to_sdn_verified_ms"]
            else:
                key = row["request_id"]
                group = "x25519" if profile == "classic" else "x25519mlkem768"
                valid = (row["profile_requested"] == profile and row["ok"] is True
                         and row["group_observed"].lower() == group and row["certificate_verified"] is True
                         and row["application_response_ok"] is True and row["tls_version"] == "TLSv1.3"
                         and row["host"] == "10.0.0.1" and row["port"] == (4433 if profile == "classic" else 4434)
                         and row.get("udp_offered_mbps") == load)
                value = row["probe_elapsed_ms"]
                if load:
                    if row["udp_window_verified"] is not True or number(row["udp_receiver_mbps"]) <= 0:
                        raise ValueError(name + ": carico non confermato")
                    rates.append(row["udp_receiver_mbps"])
            if not valid or row["network_profile"] != network or not key or key in ids:
                raise ValueError(name + ": scenario, esito o identificatore incoerente")
            if name.endswith("165932879473Z/misure.jsonl") and row.get("trial_id") != "recupero-drone-9m-01":
                raise ValueError(name + ": identificatore del recupero inatteso")
            ids.add(key)
            times.append(number(value))
    ms = statistics.median(times)
    rate = statistics.median(rates) if rates else None
    # I riepiloghi mostrati sulla VM erano arrotondati al millesimo.
    if len(times) != 10 or abs(ms - expected) > 0.000501:
        raise ValueError("mediana osservata {} ms su {} campioni, attesa {} ms su 10".format(ms, len(times), expected))
    if expected_rate is not None and abs(rate - expected_rate) > 0.000501:
        raise ValueError("banda mediana osservata {} Mbit/s, attesa {}".format(rate, expected_rate))
    return dict(metrica=metric, rete=network, profilo=profile, udp_mbps=load, campioni=len(times),
                mediana_ms=ms, mediana_udp_ricevuto_mbps=rate, sorgenti=files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    results, errors = [], []
    for series in SERIES:
        try:
            results.append(audit(args.directory, series))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append({"serie": series[:4], "errore": str(error)})
    print(json.dumps({"serie_verificate": len(results), "risultati": results, "errori": errors},
                     indent=2, ensure_ascii=False))
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
