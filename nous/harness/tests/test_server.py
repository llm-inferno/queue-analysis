import socket
import threading
import time
import pytest
from nous.harness.server import wait_for_port, AnalyzerServer


def test_wait_for_port_returns_when_socket_accepts():
    """wait_for_port should return promptly once something binds."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    def listen():
        sock.listen(1)
        conn, _ = sock.accept()
        conn.close()

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    try:
        wait_for_port("127.0.0.1", port, timeout=2.0)
    finally:
        sock.close()


def test_wait_for_port_times_out_when_no_listener():
    with pytest.raises(TimeoutError):
        wait_for_port("127.0.0.1", 65530, timeout=0.5)


def test_analyzer_server_context_manager_lifecycle(monkeypatch):
    """AnalyzerServer.__enter__ starts the process; __exit__ stops it.
    We monkeypatch the actual subprocess so this test does not require Go.
    """
    started, signals = [], []

    class FakeProc:
        def __init__(self): self.returncode = None
        def poll(self): return self.returncode
        def terminate(self): signals.append("term"); self.returncode = -15
        def kill(self): signals.append("kill"); self.returncode = -9
        def wait(self, timeout=None): return self.returncode

    def fake_popen(cmd, **kwargs):
        started.append(cmd)
        return FakeProc()

    monkeypatch.setattr("nous.harness.server.subprocess.Popen", fake_popen)
    monkeypatch.setattr("nous.harness.server.wait_for_port", lambda *a, **k: None)

    with AnalyzerServer(repo_dir="/tmp", port=8080) as url:
        assert url == "http://127.0.0.1:8080"
        assert started, "Popen should have been called"
    assert signals == ["term"], f"expected graceful SIGTERM only, got {signals}"
