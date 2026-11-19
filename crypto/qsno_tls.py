#!/usr/bin/env python3
"""TLS endpoints and verified probes for the QSNO laboratory (Python 3.8+).

Every probe opens a fresh TLS connection. Its elapsed time includes process
startup, TCP, TLS, an HTTP request and shutdown; it is not pure handshake time.
"""

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROFILES = {
    "classic": {"group": "X25519", "port": 4433},
    "hybrid": {"group": "X25519MLKEM768", "port": 4434},
}
CIPHERSUITE = "TLS_AES_256_GCM_SHA384"
LAB = Path.home() / "qsno-crypto/tls-lab"
OPENSSL = Path.home() / "qsno-crypto/openssl-3.5.9/bin/openssl"


def text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def field(output, label):
    match = re.search(r"^" + re.escape(label) + r":\s*(.+)$", output, re.MULTILINE)
    return match.group(1).strip() if match else None


def observed_group(output):
    return field(output, "Negotiated TLS1.3 group") or (
        (field(output, "Peer Temp Key") or "").split(",", 1)[0].strip() or None
    )


def inspect_connection(stdout, stderr, returncode, expected_group):
    group = observed_group(stderr)
    version = field(stderr, "Protocol version")
    cipher = field(stderr, "Ciphersuite")
    certificate = field(stderr, "Verification") == "OK"
    first_line = stdout.splitlines()[0] if stdout.splitlines() else ""
    response_ok = bool(re.fullmatch(r"HTTP/1\.[01] 200(?: .*)?", first_line))
    result = {
        "group_observed": group, "tls_version": version, "ciphersuite": cipher,
        "signature_algorithm": field(stderr, "Signature type"),
        "verified_peername": field(stderr, "Verified peername"),
        "certificate_verified": certificate, "application_response_ok": response_ok,
    }
    lowered = stderr.lower()
    if returncode != 0:
        if "certificate verify failed" in lowered or "hostname mismatch" in lowered:
            error = "certificate_verify_failed"
        elif "connection refused" in lowered or "connect:errno=" in lowered or "bio_connect" in lowered:
            error = "connection_failed"
        else:
            error = "handshake_failed"
    elif not certificate:
        error = "verification_not_confirmed"
    elif version != "TLSv1.3":
        error = "unexpected_tls_version"
    elif not group or group.casefold() != expected_group.casefold():
        error = "unexpected_group"
    elif cipher != CIPHERSUITE:
        error = "unexpected_ciphersuite"
    elif not response_ok:
        error = "application_response_missing"
    else:
        error = None
    result.update(ok=error is None, error_code=error)
    return result


def require_file(path, description, executable=False):
    path = path.expanduser().resolve()
    if not path.is_file() or (executable and not os.access(str(path), os.X_OK)):
        raise ValueError("{} non disponibile: {}".format(description, path))
    return path


def target_address(host, port):
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "{}:{}".format(host, port)
    return "[{}]:{}".format(host, port) if address.version == 6 else "{}:{}".format(host, port)


def save_private(path, content):
    with path.open("x", encoding="utf-8") as stream:
        path.chmod(0o600)
        stream.write(content)


def serve(args):
    executable = require_file(args.openssl, "OpenSSL", executable=True)
    certificate = require_file(args.cert, "Certificato del server")
    key = require_file(args.key, "Chiave del server")
    profile = PROFILES[args.profile]
    port = args.port or profile["port"]
    command = [
        str(executable), "s_server", "-accept", target_address(args.bind, port),
        "-cert", str(certificate), "-key", str(key), "-tls1_3",
        "-groups", profile["group"], "-ciphersuites", CIPHERSUITE,
        "-num_tickets", "0", "-www",
    ]
    print("QSNO server: profilo={}, gruppo={}, indirizzo={}".format(
        args.profile, profile["group"], target_address(args.bind, port)), flush=True)
    # Replace this process so Ctrl+C and process supervision reach OpenSSL.
    os.execv(str(executable), command)


def probe(args):
    profile = PROFILES[args.profile]
    port = args.port or profile["port"]
    started = time.monotonic()
    result = {
        "schema_version": 1,
        "request_id": args.request_id or str(uuid.uuid4()),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "profile_requested": args.profile, "group_requested": profile["group"],
        "host": args.host, "port": port, "server_name": args.server_name,
        "ok": False, "group_observed": None, "certificate_verified": False,
        "application_response_ok": False, "openssl_returncode": None,
        "error_code": None, "error_detail": None,
        "elapsed_definition": "process_startup+TCP+TLS+HTTP_response+shutdown",
    }
    stdout, stderr = "", ""
    try:
        executable = require_file(args.openssl, "OpenSSL", executable=True)
        ca = require_file(args.ca, "Certificato della CA")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", args.server_name):
            raise ValueError("Nome del server non valido")
        command = [
            str(executable), "s_client", "-connect", target_address(args.host, port),
            "-servername", args.server_name, "-verify_hostname", args.server_name,
            "-verify_return_error", "-CAfile", str(ca), "-tls1_3",
            "-groups", profile["group"], "-ciphersuites", CIPHERSUITE,
            "-brief", "-ign_eof",
        ]
        request = "GET / HTTP/1.0\r\nHost: {}\r\n\r\n".format(args.server_name)
        completed = subprocess.run(
            command, input=request, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=args.timeout, check=False,
        )
        stdout, stderr = completed.stdout, completed.stderr
        result.update(openssl_returncode=completed.returncode)
        result.update(inspect_connection(stdout, stderr, completed.returncode, profile["group"]))
        if not result["ok"]:
            result["error_detail"] = stderr[-4000:] or "Esito TLS o risposta applicativa inattesi"
    except subprocess.TimeoutExpired as error:
        stdout, stderr = text(error.stdout), text(error.stderr)
        result.update(error_code="timeout", error_detail="Nessun esito completo entro {} secondi".format(args.timeout))
    except (OSError, ValueError) as error:
        result.update(error_code="configuration_error", error_detail=str(error))
    result["probe_elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    try:
        directory = args.log_dir.expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        basename = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex
        prefix = directory / basename
        result["log_prefix"] = str(prefix)
        save_private(directory / (basename + ".handshake.log"), stderr)
        save_private(directory / (basename + ".response.txt"), stdout)
        save_private(directory / (basename + ".json"), json.dumps(result, indent=2) + "\n")
    except OSError as error:
        result.update(ok=False, error_code="log_write_failed", error_detail=str(error))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def port_number(value):
    parsed = int(value)
    if not 1 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("La porta deve essere fra 1 e 65535")
    return parsed


def positive_timeout(value):
    parsed = float(value)
    if not 0 < parsed <= 300:
        raise argparse.ArgumentTypeError("Il timeout deve essere maggiore di 0 e al massimo 300 secondi")
    return parsed


def main():
    parser = argparse.ArgumentParser(description="Server TLS e verifica dei profili QSNO")
    commands = parser.add_subparsers(dest="command", required=True)
    server = commands.add_parser("serve", help="Avvia un servizio TLS con un solo profilo")
    client = commands.add_parser("probe", help="Verifica un profilo e restituisce un oggetto JSON")
    for command in (server, client):
        command.add_argument("--profile", choices=tuple(PROFILES), required=True)
        command.add_argument("--port", type=port_number)
        command.add_argument("--openssl", type=Path, default=OPENSSL)
    server.add_argument("--bind", default="127.0.0.1")
    server.add_argument("--cert", type=Path, default=LAB / "server.crt")
    server.add_argument("--key", type=Path, default=LAB / "server.key")
    client.add_argument("--host", default="127.0.0.1")
    client.add_argument("--server-name", default="qsno-server")
    client.add_argument("--ca", type=Path, default=LAB / "ca.crt")
    client.add_argument("--timeout", type=positive_timeout, default=10)
    client.add_argument("--request-id")
    client.add_argument("--log-dir", type=Path, default=Path.home() / "qsno-crypto/results/tls-probes")
    args = parser.parse_args()
    if args.command == "probe":
        return probe(args)
    try:
        serve(args)
    except (OSError, ValueError) as error:
        print("ERRORE: {}".format(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
