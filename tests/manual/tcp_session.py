"""Servizio echo e client persistente per le prove manuali SDN."""

import argparse
import socket
import threading
import time


def handle_client(conn):
    with conn:
        while True:
            data = conn.recv(4096)
            if not data:
                return
            conn.sendall(data)


def run_server():
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("10.0.0.1", 4443))
        server.listen()
        print("Server pronto sulla porta 4443", flush=True)

        while True:
            conn, address = server.accept()
            print(f"Connessione da {address}", flush=True)
            threading.Thread(
                target=handle_client, args=(conn,), daemon=True
            ).start()


def run_client(label):
    try:
        with socket.create_connection(("10.0.0.1", 4443), timeout=3) as conn:
            print(
                f"{label}: connesso, porta locale {conn.getsockname()[1]}",
                flush=True,
            )
            for sequence in range(120):
                message = f"{label}:{sequence}\n".encode()
                conn.sendall(message)

                response = b""
                while len(response) < len(message):
                    chunk = conn.recv(len(message) - len(response))
                    if not chunk:
                        raise ConnectionError("Server disconnesso")
                    response += chunk

                if response != message:
                    raise ValueError("Risposta inattesa")

                print(f"{label}: ACK {sequence}", flush=True)
                time.sleep(1)
    except (OSError, ValueError) as error:
        print(f"{label}: STOP {type(error).__name__}: {error}", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["server", "client"])
    parser.add_argument("--label", default="client")
    args = parser.parse_args()

    if args.role == "server":
        run_server()
    else:
        run_client(args.label)