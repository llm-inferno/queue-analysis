"""Lifecycle of the Go queue-analysis HTTP server."""

from __future__ import annotations
import socket
import subprocess
import time
from contextlib import AbstractContextManager
from pathlib import Path


def wait_for_port(host: str, port: int, timeout: float = 30.0) -> None:
    """Block until host:port accepts a TCP connection, or raise TimeoutError."""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError as e:
            last_err = e
            time.sleep(0.1)
    raise TimeoutError(f"port {host}:{port} did not open within {timeout}s; last error: {last_err}")


class AnalyzerServer(AbstractContextManager):
    """Spawn `go run main.go` in repo_dir, wait for :port, kill on exit."""

    def __init__(self, repo_dir: str | Path, port: int = 8080, ready_timeout: float = 60.0):
        self.repo_dir = str(repo_dir)
        self.port = port
        self.ready_timeout = ready_timeout
        self._proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> str:
        self._proc = subprocess.Popen(
            ["go", "run", "main.go"],
            cwd=self.repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_port("127.0.0.1", self.port, timeout=self.ready_timeout)
        except Exception:
            self._kill()
            raise
        return self.url

    def __exit__(self, exc_type, exc, tb) -> None:
        self._kill()

    def _kill(self) -> None:
        if self._proc is None or self._proc.poll() is not None:
            return
        # SIGTERM first so `go run` has a chance to clean up its compiled child;
        # escalate to SIGKILL if it doesn't exit promptly.
        self._proc.terminate()
        try:
            self._proc.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            pass
        self._proc.kill()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
