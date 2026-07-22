#!/usr/bin/env bash
# Offline integration test for tasks/paginated_get.yml using a local
# stdlib HTTP server. No AAP instance, no network downloads.
set -euo pipefail
cd "$(dirname "$0")/.."
portfile="$(mktemp)"
python3 tests/paginator_server.py "$portfile" &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true; rm -f "$portfile"' EXIT

# Wait for the server to publish its bound port.
for _ in $(seq 1 50); do
  [ -s "$portfile" ] && break
  sleep 0.1
done
port="$(cat "$portfile")"
[ -n "$port" ] || { echo "server did not start" >&2; exit 1; }

ANSIBLE_FILTER_PLUGINS="$(pwd)/filter_plugins" \
ansible-playbook tests/pagination_probe.yml \
  -e "pg_base=http://127.0.0.1:${port}"
echo "PAGINATION OFFLINE OK"
