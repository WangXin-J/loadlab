from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_port(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


@pytest.fixture(scope="session")
def ws_server(tmp_path_factory):
    port = _free_port()
    stats = tmp_path_factory.mktemp("stats") / "server-stats.jsonl"
    proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "target" / "push_server.py"),
            "--port", str(port),
            "--mode", "naive",
            "--interval", "0.1",
            "--stats", str(stats),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_port(port):
            pytest.fail("推送服务启动超时")
        yield f"ws://127.0.0.1:{port}", stats
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
