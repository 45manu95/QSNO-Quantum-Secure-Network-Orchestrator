#!/usr/bin/env python3
"""Controlled TLS/SDN integration check using the existing QSNO network code.

Requires Linux, root, Mininet and an already running Ryu controller. It refuses
an existing s1 or connected datapaths, owns its network and child processes,
and never invokes the global Mininet cleanup command.
"""

import argparse
import importlib.util
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


NETWORK_COMMIT = "e8a2dd3fc7c5baa3e1c084a068064e592761f706"
NODES = {"h_server": "10.0.0.1", "h_iot": "10.0.0.2", "h_drone": "10.0.0.3"}


def command(arguments, cwd=None):
    return subprocess.run(arguments, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=15, check=False)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stop_owned(process):
    if process.poll() is not None:
        return
    # Mininet's mnexec -d makes this child a session/process-group leader.
    # Never signal a group shared with this runner or other shell processes.
    grouped = os.getpgid(process.pid) == process.pid
    if grouped:
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if grouped:
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=3)


def preflight(repo, base, output):
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("Esegui sulla VM Ubuntu usando sudo python3.")
    required = [repo / "topology/qsno_topology.py", repo / "controller/sdn_client.py",
                base / "qsno_tls.py", base / "openssl-3.5.9/bin/openssl",
                base / "tls-lab/ca.crt", base / "tls-lab/server.crt", base / "tls-lab/server.key"]
    for path in required:
        if not path.is_file():
            raise RuntimeError("File necessario assente: {}".format(path))
    if output.exists():
        raise RuntimeError("La cartella dei risultati esiste gia. Scegli un nome nuovo: {}".format(output))
    git = command(["git", "-c", "safe.directory=" + str(repo), "-C", str(repo), "rev-parse", "HEAD"])
    if git.returncode != 0 or git.stdout.strip() != NETWORK_COMMIT:
        raise RuntimeError("La copia della rete deve essere alla revisione {}. Dettagli: {}".format(
            NETWORK_COMMIT, git.stderr.strip() or git.stdout.strip()))
    dirty = command(["git", "-c", "safe.directory=" + str(repo), "-C", str(repo), "status", "--porcelain", "--untracked-files=no"])
    if dirty.returncode != 0 or dirty.stdout.strip():
        raise RuntimeError("La copia della rete contiene modifiche tracciate o non e leggibile; non la modifico.")
    ovs = command(["ovs-vsctl", "br-exists", "s1"])
    if ovs.returncode == 0:
        raise RuntimeError("Esiste gia s1: una rete potrebbe essere attiva. Coordinati con il collega; non la arresto.")
    if ovs.returncode != 2:
        raise RuntimeError("Open vSwitch non disponibile: {}".format(ovs.stderr.strip()))
    with socket.create_connection(("127.0.0.1", 6653), timeout=2):
        pass
    opener = build_opener(ProxyHandler({}))
    with opener.open("http://127.0.0.1:8080/stats/switches", timeout=2) as response:
        switches = json.load(response)
    if not isinstance(switches, list) or switches:
        raise RuntimeError("Ryu gestisce gia degli switch oppure restituisce uno stato inatteso. Non avvio un'altra rete.")
    return git.stdout.strip()


def run_check(args):
    repo = args.network_repo.expanduser().resolve()
    base = args.crypto_home.expanduser().resolve()
    output = args.output.expanduser().resolve()
    commit = preflight(repo, base, output)
    # Import Linux-only dependencies after the read-only preflight checks.
    from mininet.net import Mininet
    from mininet.node import RemoteController
    topology = load_module("qsno_topology_check", repo / "topology/qsno_topology.py")
    sdn = load_module("qsno_sdn_check", repo / "controller/sdn_client.py")
    output.mkdir(parents=True)
    output.chmod(0o755)
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(), "status": "running",
        "network_commit": commit, "network_profile": args.profile, "checks": [],
        "crypto_home": str(base), "cleanup_errors": [],
        "scope": "Fresh TLS connections and per-client SDN blocking; not persistent-stream migration.",
    }
    network, processes, blocked = None, [], False

    def save_report():
        path = output / "report.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o644)

    def record(name, passed, details):
        report["checks"].append({"name": name, "passed": passed, "details": details})
        save_report()
        print("{} {}".format("PASS" if passed else "FAIL", name), flush=True)
        if not passed:
            raise RuntimeError("Verifica non superata: {}. Vedi {}".format(name, output / "report.json"))

    def probe(name, node, profile, error=None, port=None, server_name=None, retry_connect=False):
        deadline = time.monotonic() + 10
        attempt = 0
        while True:
            attempt += 1
            argv = [sys.executable, str(base / "qsno_tls.py"), "probe", "--profile", profile,
                    "--host", NODES["h_server"], "--openssl", str(base / "openssl-3.5.9/bin/openssl"),
                    "--ca", str(base / "tls-lab/ca.crt"), "--log-dir", str(output / "probe-logs"),
                    "--request-id", name, "--timeout", "3" if error == "timeout" else "10"]
            if port is not None:
                argv += ["--port", str(port)]
            if server_name:
                argv += ["--server-name", server_name]
            # The existing client shell is already in its CPU cgroup. Running
            # through it preserves the quota and avoids mnexec -g rejecting
            # underscore-containing host names in some Mininet 2.3 builds.
            # Keep the foreground process in that shell's group for cleanup.
            bounded = ["timeout", "--foreground", "--kill-after=2s", "20s", *argv]
            stdout = node.cmd(" ".join(shlex.quote(str(arg)) for arg in bounded))
            stderr = ""
            (output / ("{}-{}.stdout.txt".format(name, attempt))).write_text(stdout, encoding="utf-8")
            (output / ("{}-{}.stderr.txt".format(name, attempt))).write_text(stderr, encoding="utf-8")
            try:
                details = json.loads(stdout)
            except ValueError as error_output:
                raise RuntimeError("Helper {} senza risultato JSON. Dettagli: {} {}".format(
                    name, stdout[-2000:], stderr[-2000:])) from error_output
            if stderr:
                details["helper_stderr"] = stderr
            if retry_connect and details.get("error_code") == "connection_failed" and time.monotonic() < deadline:
                time.sleep(0.1)
                continue
            passed = (details.get("openssl_returncode") == 0 and details.get("ok") is True) if error is None else (
                details.get("ok") is False and details.get("error_code") == error)
            record(name, passed, details)
            return

    save_report()
    try:
        network = Mininet(topo=topology.QsnoTopology(profile=args.profile), controller=None, build=False)
        network.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)
        network.build()
        network.start()
        for name, address in NODES.items():
            if network.get(name).IP() != address:
                raise RuntimeError("Indirizzo inatteso per {}".format(name))
        deadline = time.monotonic() + 10
        while True:
            try:
                sdn.get_switch_flows(timeout=2)
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Lo switch non compare nelle statistiche di Ryu entro 10 secondi")
                time.sleep(0.2)
        server = network.get("h_server")
        for profile in ("classic", "hybrid"):
            with (output / (profile + "-server.log")).open("w", encoding="utf-8") as log:
                process = server.popen([
                    sys.executable, str(base / "qsno_tls.py"), "serve", "--profile", profile,
                    "--bind", NODES["h_server"], "--openssl", str(base / "openssl-3.5.9/bin/openssl"),
                    "--cert", str(base / "tls-lab/server.crt"), "--key", str(base / "tls-lab/server.key"),
                ], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
                processes.append(process)
        iot, drone = network.get("h_iot"), network.get("h_drone")
        probe("iot_classic", iot, "classic", retry_connect=True)
        probe("iot_hybrid", iot, "hybrid", retry_connect=True)
        probe("drone_classic", drone, "classic")
        probe("drone_hybrid", drone, "hybrid")
        probe("incompatible_group", iot, "classic", port=4434, error="handshake_failed")
        probe("wrong_server_name", iot, "hybrid", server_name="nome-sbagliato", error="certificate_verify_failed")
        # Set before the API call: even a partially applied request must be
        # reversed during cleanup if later verification fails.
        blocked = True
        result = sdn.set_classic_block("iot", True)
        record("block_iot_rule", result.get("status") == "RULE_VERIFIED", result)
        probe("iot_classic_blocked", iot, "classic", error="timeout")
        probe("iot_hybrid_after_block", iot, "hybrid")
        probe("drone_classic_after_block", drone, "classic")
        result = sdn.set_classic_block("iot", False)
        record("unblock_iot_rule", result.get("status") == "RULE_VERIFIED", result)
        blocked = False
        probe("iot_classic_restored", iot, "classic")
        report["status"] = "complete"
    except BaseException as error:
        report.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed", error=str(error))
        print("ERRORE: {}".format(error), file=sys.stderr, flush=True)
    finally:
        for process in reversed(processes):
            try:
                stop_owned(process)
            except ProcessLookupError:
                pass
            except Exception as error:
                report["cleanup_errors"].append("processo {}: {}".format(process.pid, error))
        if blocked:
            try:
                sdn.set_classic_block("iot", False)
            except Exception as error:
                report["cleanup_errors"].append("rimozione blocco IoT: {}".format(error))
        if network is not None:
            try:
                network.stop()
            except Exception as error:
                report["cleanup_errors"].append("arresto della rete: {}".format(error))
        if report["cleanup_errors"]:
            report["status"] = "failed"
        report["ended_utc"] = datetime.now(timezone.utc).isoformat()
        save_report()
    passed = sum(check["passed"] for check in report["checks"])
    complete = report["status"] == "complete" and passed == 12
    print("{}: {}/12 controlli superati. Report: {}".format(
        "COMPLETATO" if complete else "NON COMPLETATO", passed, output / "report.json"), flush=True)
    return 0 if complete else 1


def main():
    parser = argparse.ArgumentParser(description="Prima verifica TLS e SDN nella rete QSNO")
    parser.add_argument("--network-repo", type=Path, required=True)
    parser.add_argument("--crypto-home", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("nominal", "degraded"), default="nominal")
    args = parser.parse_args()
    try:
        return run_check(args)
    except (Exception, KeyboardInterrupt) as error:
        print("AVVIO RIFIUTATO: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
