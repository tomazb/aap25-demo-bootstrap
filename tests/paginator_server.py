#!/usr/bin/env python3
"""Local pagination test server (stdlib only, no network).

Serves deterministic scenarios for tasks/paginated_get.yml so the pagination
behaviour can be integration-tested fully offline. Writes the bound port to
the file given as argv[1] then serves forever.

Scenarios (all under http://127.0.0.1:<port>):
  /twopage/           two pages, next is an ABSOLUTE url, last page next=null
  /relnext/           two pages, next is a RELATIVE path, last page next=null
  /err401/            HTTP 401
  /err500/            HTTP 500
  /badjson/           HTTP 200 with a non-JSON body
  /cap/               endless pages (each next points to the next page)
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


def _page(host, path, page, last_page, next_absolute):
    results = [{"name": "%s-row-%d" % (path.strip("/"), page)}]
    if page >= last_page:
        nxt = None
    elif next_absolute:
        nxt = "http://%s%s?page=%d" % (host, path, page + 1)
    else:
        nxt = "%s?page=%d" % (path, page + 1)
    return {"count": last_page, "next": nxt, "previous": None, "results": results}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, raw=False):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if raw:
            self.wfile.write(body.encode())
        else:
            self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        host = self.headers.get("Host", "127.0.0.1")
        if path == "/twopage/":
            self._send(200, _page(host, path, page, 2, True))
        elif path == "/relnext/":
            self._send(200, _page(host, path, page, 2, False))
        elif path == "/err401/":
            self._send(401, {"detail": "auth failed"})
        elif path == "/err500/":
            self._send(500, {"detail": "boom"})
        elif path == "/badjson/":
            self._send(200, "this is not json", raw=True)
        elif path == "/cap/":
            # Never terminates on its own; used to test page-cap truncation.
            self._send(200, _page(host, path, page, 10 ** 9, False))
        else:
            self._send(404, {"detail": "not found"})


def main():
    port_file = sys.argv[1]
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    with open(port_file, "w") as fh:
        fh.write(str(httpd.server_address[1]))
    httpd.serve_forever()


if __name__ == "__main__":
    main()
