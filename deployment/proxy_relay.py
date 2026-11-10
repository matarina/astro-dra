"""Forward Docker gateway port 9876 to the host's loopback proxy.

No request contents or credentials are logged. Empty TCP probes do not open
upstream connections; real transport failures retain direction and byte counts.
"""
import argparse
import json
import select
import socket
import socketserver


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        # Health probes connect and close without sending proxy protocol data.
        self.request.settimeout(10)
        try:
            first = self.request.recv(65536)
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            return
        if not first:
            return

        stage = "upstream_connect"
        direction = "client_to_upstream"
        client_bytes = upstream_bytes = 0
        try:
            with socket.create_connection(self.server.upstream, timeout=10) as upstream:
                self.request.settimeout(30)
                upstream.settimeout(30)
                stage = "transfer"
                upstream.sendall(first)
                client_bytes += len(first)
                peers = {self.request: upstream, upstream: self.request}
                reading = list(peers)
                while reading:
                    ready, _, _ = select.select(
                        reading, [], [], getattr(self.server, "idle_timeout", 120)
                    )
                    if not ready:
                        print(json.dumps({
                            "event": "proxy_relay_idle_close",
                            "severity": "info",
                            "reason_code": "idle_deadline",
                            "client_bytes_forwarded": client_bytes,
                            "upstream_bytes_forwarded": upstream_bytes,
                        }), flush=True)
                        return
                    for source in ready:
                        direction = (
                            "client_to_upstream" if source is self.request
                            else "upstream_to_client"
                        )
                        data = source.recv(65536)
                        destination = peers[source]
                        if data:
                            destination.sendall(data)
                            if source is self.request:
                                client_bytes += len(data)
                            else:
                                upstream_bytes += len(data)
                        else:
                            reading.remove(source)
                            try:
                                destination.shutdown(socket.SHUT_WR)
                            except OSError:
                                pass
        except OSError as exc:
            print(json.dumps({
                "event": "proxy_relay_transport_error",
                "severity": "warning" if isinstance(
                    exc, (ConnectionResetError, BrokenPipeError)
                ) else "error",
                "reason_code": "upstream_connect_failed" if stage == "upstream_connect" else "transport_interrupted",
                "stage": stage,
                "direction": direction,
                "error_type": type(exc).__name__,
                "client_bytes_forwarded": client_bytes,
                "upstream_bytes_forwarded": upstream_bytes,
            }), flush=True)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="host.docker.internal")
    parser.add_argument("--port", type=int, default=9876)
    args = parser.parse_args()
    address = socket.gethostbyname(args.listen_host)
    if address in {"0.0.0.0", "127.0.0.1"}:
        parser.error("listen-host must resolve to the Docker gateway address")
    with Server((address, args.port), Relay) as server:
        server.upstream = ("127.0.0.1", args.port)
        print(f"Proxy relay listening on {address}:{args.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
