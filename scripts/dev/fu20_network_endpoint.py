#!/usr/bin/env python3
"""Controlled reachable endpoint for the FU-20 Linux network-isolation proof.

A real TCP + UDP echo server. The unrestricted control and the
launcher-restricted parser both target it, so a denial is only meaningful
if the control connects.

Used by the ``linux-network-isolation`` CI job.
"""
from __future__ import annotations

import argparse
import socketserver
import threading

_LOG_LOCK = threading.Lock()


def log(msg: str) -> None:
    with _LOG_LOCK:
        print(msg, flush=True)


class TCPHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        peer = self.request.getpeername()
        data = self.request.recv(64)
        log(f"TCP_ACCEPT from={peer[0]}:{peer[1]} data={data!r}")
        self.request.sendall(b"TCP_ECHO:" + data)


class UDPHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data, sock = self.request
        peer = self.client_address
        log(f"UDP_RECV from={peer[0]}:{peer[1]} data={data!r}")
        sock.sendto(b"UDP_ECHO:" + data, self.client_address)


class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class UDPServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    ap = argparse.ArgumentParser()
    # Binding all interfaces is deliberate: the endpoint must be
    # reachable from a sibling container on the proof network.
    ap.add_argument("--host", default="0.0.0.0")  # noqa: S104
    ap.add_argument("--tcp-port", type=int, default=18099)
    ap.add_argument("--udp-port", type=int, default=18098)
    args = ap.parse_args()

    # Binding all interfaces is deliberate: the endpoint must be
    # reachable from a sibling container on the proof network.
    tcp = TCPServer((args.host, args.tcp_port), TCPHandler)
    udp = UDPServer((args.host, args.udp_port), UDPHandler)
    log(f"SERVER_READY tcp={args.tcp_port} udp={args.udp_port}")
    threading.Thread(target=udp.serve_forever, daemon=True).start()
    tcp.serve_forever()


if __name__ == "__main__":
    main()
