"""Real loopback tests: empty probes, half-closes and actual transport failure."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import socket
import socketserver
import struct
import threading
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("deployment_proxy_relay", ROOT / "deployment/proxy_relay.py")
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


@contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def forwarding(upstream):
    class Observed(relay.Relay):
        def finish(self):
            try:
                super().finish()
            finally:
                self.server.finished.set()

    server = relay.Server(("127.0.0.1", 0), Observed)
    server.upstream = upstream
    server.finished = threading.Event()
    return server


def read_all(client):
    output = bytearray()
    while True:
        data = client.recv(65536)
        if not data:
            return bytes(output)
        output.extend(data)


def test_empty_probe_never_opens_upstream_or_emits_error(monkeypatch, capsys):
    called = []
    def unexpected(*a, **k):
        called.append(True)
        raise ConnectionRefusedError()
    monkeypatch.setattr(relay, "socket", SimpleNamespace(create_connection=unexpected, SHUT_WR=socket.SHUT_WR))
    with running(forwarding(("127.0.0.1", 1))) as server:
        with socket.create_connection(server.server_address, timeout=2) as client:
            client.shutdown(socket.SHUT_WR)
            assert read_all(client) == b""
        assert server.finished.wait(2)
    assert called == []
    assert capsys.readouterr().out == ""


def test_bulk_bidirectional_forwarding_preserves_half_close_and_bytes(capsys):
    payload = bytes(range(256)) * 1024
    class Echo(socketserver.BaseRequestHandler):
        def handle(self):
            received = read_all(self.request)
            self.request.sendall(b"reply:" + received)
            self.request.shutdown(socket.SHUT_WR)
    with running(socketserver.ThreadingTCPServer(("127.0.0.1", 0), Echo)) as upstream:
        with running(forwarding(upstream.server_address)) as server:
            with socket.create_connection(server.server_address, timeout=3) as client:
                client.sendall(payload)
                client.shutdown(socket.SHUT_WR)
                assert read_all(client) == b"reply:" + payload
            assert server.finished.wait(2)
    assert capsys.readouterr().out == ""


def test_real_upstream_connect_failure_is_not_suppressed(monkeypatch, capsys):
    def refused(*a, **k):
        raise ConnectionRefusedError("synthetic-private-marker")
    monkeypatch.setattr(relay, "socket", SimpleNamespace(create_connection=refused, SHUT_WR=socket.SHUT_WR))
    with running(forwarding(("127.0.0.1", 1))) as server:
        with socket.create_connection(server.server_address, timeout=2) as client:
            client.sendall(b"CONNECT synthetic-private-marker")
            assert read_all(client) == b""
        assert server.finished.wait(2)
    output = capsys.readouterr().out
    record = json.loads(output)
    assert record["stage"] == "upstream_connect"
    assert record["error_type"] == "ConnectionRefusedError"
    assert record["severity"] == "error"
    assert "synthetic-private-marker" not in output


def test_reset_after_transmission_retains_transport_diagnostic(capsys):
    class Reset(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(65536)
            self.request.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            # Close here so socketserver cannot turn the reset into a graceful FIN.
            self.request.close()
    with running(socketserver.ThreadingTCPServer(("127.0.0.1", 0), Reset)) as upstream:
        with running(forwarding(upstream.server_address)) as server:
            with socket.create_connection(server.server_address, timeout=2) as client:
                client.sendall(b"CONNECT synthetic-private-marker")
                try:
                    read_all(client)
                except ConnectionResetError:
                    pass
            assert server.finished.wait(2)
    output = capsys.readouterr().out
    record = json.loads(output)
    assert record["stage"] == "transfer"
    assert record["client_bytes_forwarded"] > 0
    assert record["error_type"] in {"ConnectionResetError", "BrokenPipeError"}
    assert record["severity"] == "warning"
    assert "synthetic-private-marker" not in output


def test_idle_tunnel_close_is_distinct_from_transport_failure(capsys):
    release = threading.Event()
    class KeepAlive(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(65536)
            self.request.sendall(b"ok")
            release.wait(2)

    with running(socketserver.ThreadingTCPServer(("127.0.0.1", 0), KeepAlive)) as upstream:
        with running(forwarding(upstream.server_address)) as server:
            server.idle_timeout = 0.05
            try:
                with socket.create_connection(server.server_address, timeout=2) as client:
                    client.sendall(b"request")
                    assert read_all(client) == b"ok"
                assert server.finished.wait(2)
            finally:
                release.set()
    output = capsys.readouterr().out
    record = json.loads(output)
    assert record["event"] == "proxy_relay_idle_close"
    assert record["reason_code"] == "idle_deadline"
    assert record["client_bytes_forwarded"] == len(b"request")
    assert record["upstream_bytes_forwarded"] == len(b"ok")
    assert "proxy_relay_transport_error" not in output
