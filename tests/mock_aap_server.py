#!/usr/bin/env python3
"""Local mock AAP gateway+controller for verify_smoke.yml regression tests.

Loads config/demo.yml so it can answer authoritatively for every demo object,
then applies a scenario (env SMOKE_SCENARIO) to inject faults. Stdlib only.

argv[1] = port file. Scenarios:
  happy              everything present, synced, current-id history
  missing_project    first demo project returns no results
  api_500            teams endpoint returns HTTP 500
  duplicate_inventory  first inventory name returns two rows in the same org
  stale_history      job templates exist but NO successful history for the
                     current template id (only stale runs of an old id existed)
"""
import base64
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = yaml.safe_load(open(os.path.join(HERE, "..", "config", "demo.yml")))
SCENARIO = os.environ.get("SMOKE_SCENARIO", "happy")

ORGS = [o["name"] for o in DEMO["demo_organizations"]]
TEAMS = [t["name"] for t in DEMO["demo_teams"]]
USERS = [u["username"] for u in DEMO["demo_users"]]
INV = {i["name"]: i["organization"] for i in DEMO["demo_inventories"]}
PROJ = {p["name"]: p["organization"] for p in DEMO["demo_projects"]}
# Assign a stable current id to each job template.
JT = {j["name"]: {"org": j["organization"], "id": 100 + n}
      for n, j in enumerate(DEMO["demo_job_templates"])}
CONTROLLED = "Demo 05 - Controlled outcome"
FIRST_PROJECT = DEMO["demo_projects"][0]["name"]
FIRST_INV = DEMO["demo_inventories"][0]["name"]
# Restricted-user RBAC: map username -> org, and enumerate all JT rows so an
# unfiltered list can be scoped to the authenticated user's own organization.
USER_ORG = {u["username"]: u["organization"] for u in DEMO["demo_users"]}
JT_ROWS = [{"name": n, "id": v["id"],
            "summary_fields": {"organization": {"name": v["org"]}}}
           for n, v in JT.items()]


def _list(results):
    return {"count": len(results), "next": None, "previous": None,
            "results": results}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def _auth_user(self):
        hdr = self.headers.get("Authorization", "")
        if hdr.startswith("Basic "):
            try:
                return base64.b64decode(hdr[6:]).decode().split(":", 1)[0]
            except Exception:
                return None
        return None

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)
        path = p.path
        name = q.get("name", [None])[0]
        username = q.get("username", [None])[0]

        # Restricted-user RBAC: an unfiltered job-template list is scoped to the
        # authenticated user's own organization (admin/unknown sees all).
        if path == "/api/controller/v2/job_templates/" and name is None:
            who = self._auth_user()
            if who in USER_ORG:
                org = USER_ORG[who]
                rows = [r for r in JT_ROWS
                        if r["summary_fields"]["organization"]["name"] == org]
            else:
                rows = JT_ROWS
            return self._send(200, _list(rows))

        if path == "/api/gateway/v1/organizations/":
            return self._send(200, _list(
                [{"name": name}] if name in ORGS else []))
        if path == "/api/gateway/v1/teams/":
            if SCENARIO == "api_500":
                return self._send(500, {"detail": "boom"})
            return self._send(200, _list(
                [{"name": name}] if name in TEAMS else []))
        if path == "/api/gateway/v1/users/":
            return self._send(200, _list(
                [{"username": username}] if username in USERS else []))

        if path == "/api/controller/v2/inventories/":
            if SCENARIO == "duplicate_inventory" and name == FIRST_INV:
                row = {"name": name, "summary_fields":
                       {"organization": {"name": INV[name]}}}
                return self._send(200, _list([row, dict(row)]))
            if name in INV:
                return self._send(200, _list([{"name": name, "summary_fields":
                    {"organization": {"name": INV[name]}}}]))
            return self._send(200, _list([]))

        if path == "/api/controller/v2/projects/":
            if SCENARIO == "missing_project" and name == FIRST_PROJECT:
                return self._send(200, _list([]))
            if name in PROJ:
                return self._send(200, _list([{"name": name, "status": "successful",
                    "summary_fields": {"organization": {"name": PROJ[name]}}}]))
            return self._send(200, _list([]))

        if path == "/api/controller/v2/job_templates/":
            if name in JT:
                return self._send(200, _list([{"name": name, "id": JT[name]["id"],
                    "summary_fields": {"organization": {"name": JT[name]["org"]}}}]))
            return self._send(200, _list([]))

        if path == "/api/controller/v2/jobs/":
            status = q.get("status", [None])[0]
            try:
                jt_id = int(q.get("job_template", ["0"])[0])
            except (TypeError, ValueError):
                jt_id = 0
            if SCENARIO == "stale_history" and status == "successful":
                # No history for the current template id (only an old id had it).
                return self._send(200, _list([]))
            if status == "failed":
                # Only the controlled-outcome current id has a failed run.
                if jt_id == JT[CONTROLLED]["id"]:
                    return self._send(200, _list([{"id": 1, "status": "failed"}]))
                return self._send(200, _list([]))
            if status == "successful":
                current_ids = {template["id"] for template in JT.values()}
                if jt_id in current_ids:
                    return self._send(
                        200, _list([{"id": 1, "status": "successful"}]))
            return self._send(200, _list([]))

        return self._send(404, {"detail": "not found"})


def main():
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    with open(sys.argv[1], "w") as fh:
        fh.write(str(httpd.server_address[1]))
    httpd.serve_forever()


if __name__ == "__main__":
    main()
