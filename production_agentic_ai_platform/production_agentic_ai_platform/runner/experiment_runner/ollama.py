"""Reach an Ollama server anywhere while the POC's code keeps calling http://127.0.0.1:11434.

Frozen harnesses call the local address.  When the server is elsewhere (the host's Ollama from inside Docker, a GPU box
on the network), the runner listens on 127.0.0.1:11434 for as long as it runs and relays every byte to it.
"""

from __future__ import annotations

import os
import socket
import threading
from urllib.parse import urlparse

LOCAL = ("127.0.0.1", 11434)


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while data := a.recv(1 << 16):
            b.sendall(data)
    except OSError:
        pass
    finally:
        try:
            b.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class Relay:
    def __init__(self, host: str, port: int, local: tuple[str, int] = LOCAL):
        self.target = (host, port)
        self.srv = socket.create_server(local)
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                continue
            try:
                u = socket.create_connection(self.target, timeout=15)
                u.settimeout(None)
            except OSError:
                c.close()  # the caller sees a refused request instead of waiting forever
                continue
            for a, b in ((c, u), (u, c)):
                threading.Thread(target=_pipe, args=(a, b), daemon=True).start()


_ENDPOINT: str | None = None


def connect(url: str | None, env_var: str = "OLLAMA_HOST") -> str:
    """Make http://127.0.0.1:11434 reach the chosen server (once per process). Returns a description of the endpoint."""
    global _ENDPOINT
    if _ENDPOINT:
        return _ENDPOINT
    url = url or os.environ.get(env_var) or "http://127.0.0.1:11434"
    u = urlparse(url if "://" in url else f"http://{url}")
    host, port = u.hostname or "127.0.0.1", u.port or 11434
    if host in ("127.0.0.1", "localhost", "::1") and port == 11434:
        _ENDPOINT = "http://127.0.0.1:11434 (local)"
        return _ENDPOINT
    try:
        Relay(host, port)
    except OSError:
        raise SystemExit(f"--ollama-host {host}:{port}: something already listens on 127.0.0.1:11434 here "
                         "(a local Ollama?). Stop it, or drop --ollama-host to use it.")
    _ENDPOINT = f"http://{host}:{port} (forwarded from 127.0.0.1:11434)"
    return _ENDPOINT
