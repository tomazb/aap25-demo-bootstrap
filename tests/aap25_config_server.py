#!/usr/bin/env python3
"""Minimal local Platform Gateway controller-config endpoint for offline tests."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

VERSION = os.environ.get("AAP_CONFIG_VERSION", "4.6.29")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if urlparse(self.path).path != "/api/controller/v2/config/":
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail":"not found"}')
            return

        body = json.dumps({"version": VERSION}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: aap25_config_server.py PORT_FILE")

    server = HTTPServer(("127.0.0.1", 0), Handler)
    with open(sys.argv[1], "w", encoding="utf-8") as stream:
        stream.write(str(server.server_address[1]))
    server.serve_forever()


if __name__ == "__main__":
    main()
