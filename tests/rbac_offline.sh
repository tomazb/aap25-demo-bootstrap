#!/usr/bin/env bash
# Offline test for verify_rbac.yml against the mock AAP (per-user RBAC scoping).
# No real AAP, no network. Uses rbac_allow_insecure=true for the local HTTP mock.
set -uo pipefail
cd "$(dirname "$0")/.."
reportdir=".tmp/rbac-reports"
rm -rf "$reportdir"; mkdir -p "$reportdir"
fail() { echo "RBAC OFFLINE FAIL: $1" >&2; exit 1; }
latest() { ls -t "$reportdir"/rbac-*.md | head -1; }

SERVER_PID=""; BASE=""
start_server() {
  local portfile; portfile="$(mktemp)"
  SMOKE_SCENARIO=happy python3 tests/mock_aap_server.py "$portfile" &
  SERVER_PID=$!
  local port=""
  for _ in $(seq 1 50); do
    [ -s "$portfile" ] && { port="$(cat "$portfile")"; break; }; sleep 0.1
  done
  rm -f "$portfile"; [ -n "$port" ] || fail "mock did not start"
  BASE="http://127.0.0.1:${port}"
}
stop_server() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; SERVER_PID=""; }

# 1. correct org claim -> user sees only own-org content -> PASS
start_server
AAP_HOSTNAME="$BASE" RBAC_DEMO_PASSWORD=Demo-Pass-No-Overlap \
ansible-playbook verify_rbac.yml -e rbac_allow_insecure=true \
  -e "verify_report_dir=$reportdir" \
  -e '{"rbac_users":[{"username":"demo-alice","organization":"Demo Linux"}]}' \
  >/dev/null 2>&1
rc=$?; stop_server
[ "$rc" -eq 0 ] || fail "correct-org user should pass"
grep -q 'RESULT: PASS' "$(latest)" || fail "expected PASS report"

# 2. wrong org claim -> the user's real content is foreign -> FAIL
start_server
AAP_HOSTNAME="$BASE" RBAC_DEMO_PASSWORD=Demo-Pass-No-Overlap \
ansible-playbook verify_rbac.yml -e rbac_allow_insecure=true \
  -e "verify_report_dir=$reportdir" \
  -e '{"rbac_users":[{"username":"demo-alice","organization":"Demo Network"}]}' \
  >/dev/null 2>&1
rc=$?; stop_server
[ "$rc" -ne 0 ] || fail "cross-org visibility should fail"
grep -q 'can see content from other organizations' "$(latest)" \
  || fail "cross-org visibility not reported"

# 3. no users configured -> NOT_RUN
start_server
AAP_HOSTNAME="$BASE" RBAC_DEMO_PASSWORD=x \
ansible-playbook verify_rbac.yml -e rbac_allow_insecure=true \
  -e "verify_report_dir=$reportdir" >/dev/null 2>&1
stop_server
grep -q 'RESULT: NOT_RUN' "$(latest)" || fail "empty rbac_users should be NOT_RUN"

echo "RBAC OFFLINE OK"
