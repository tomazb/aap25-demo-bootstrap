#!/usr/bin/env bash
# Offline regression test for verify_smoke.yml against a local mock AAP.
# No real AAP, no network. Uses smoke_allow_insecure=true so the local HTTP
# mock is reachable (the security gate is verified separately below).
set -uo pipefail
cd "$(dirname "$0")/.."
reportdir=".tmp/smoke-reports"
rm -rf "$reportdir"; mkdir -p "$reportdir"
fail() { echo "SMOKE OFFLINE FAIL: $1" >&2; exit 1; }

SERVER_PID=""
BASE=""
start_server() {  # start_server <scenario> ; sets SERVER_PID and BASE
  local portfile; portfile="$(mktemp)"
  SMOKE_SCENARIO="$1" python3 tests/mock_aap_server.py "$portfile" &
  SERVER_PID=$!
  local port=""
  for _ in $(seq 1 50); do
    [ -s "$portfile" ] && { port="$(cat "$portfile")"; break; }
    sleep 0.1
  done
  rm -f "$portfile"
  [ -n "$port" ] || fail "mock server did not start"
  BASE="http://127.0.0.1:${port}"
}
stop_server() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; SERVER_PID=""; }

run_smoke() {  # run_smoke <scenario> ; sets RC and REPORT
  start_server "$1"
  AAP_HOSTNAME="$BASE" AAP_USERNAME=admin AAP_PASSWORD=Adm1n-No-Overlap \
  ansible-playbook verify_smoke.yml \
    -e smoke_allow_insecure=true \
    -e "verify_report_dir=$reportdir" >/dev/null 2>&1
  RC=$?
  stop_server
  REPORT="$(ls -t "$reportdir"/smoke-*.md | head -1)"
}

# happy path passes
run_smoke happy
[ "$RC" -eq 0 ] || fail "happy scenario should pass (rc=$RC)"
grep -q 'RESULT: PASS' "$REPORT" || fail "happy report not PASS"

# missing project does not crash; report is written and FAILs
run_smoke missing_project
[ "$RC" -ne 0 ] || fail "missing_project should fail"
grep -q 'RESULT: FAIL' "$REPORT" || fail "missing_project report missing"
grep -q 'project missing in org' "$REPORT" || fail "missing project not reported"

# an API 500 does not prevent report generation
run_smoke api_500
[ "$RC" -ne 0 ] || fail "api_500 should fail"
grep -q 'RESULT: FAIL' "$REPORT" || fail "api_500 report not written"
grep -q 'team request failed' "$REPORT" || fail "api_500 not aggregated"

# duplicate same-named inventory in one org is rejected
run_smoke duplicate_inventory
[ "$RC" -ne 0 ] || fail "duplicate_inventory should fail"
grep -q 'duplicate inventory in org' "$REPORT" || fail "duplicate not reported"

# stale history (no runs for the CURRENT template id) must not pass
run_smoke stale_history
[ "$RC" -ne 0 ] || fail "stale_history should fail"
grep -q 'no successful run for the current template id' "$REPORT" \
  || fail "stale history not caught by current-id check"

# the security gate rejects HTTP without the insecure override
start_server happy
if AAP_HOSTNAME="$BASE" AAP_USERNAME=admin AAP_PASSWORD=x \
   ansible-playbook verify_smoke.yml -e "verify_report_dir=$reportdir" >/dev/null 2>&1; then
  stop_server; fail "HTTP endpoint must be rejected without smoke_allow_insecure"
fi
stop_server

echo "SMOKE OFFLINE OK"
