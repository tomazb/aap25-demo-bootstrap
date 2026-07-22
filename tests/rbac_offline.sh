#!/usr/bin/env bash
# Offline tests for verify_rbac.yml (positive + negative visibility, paginated)
# against the mock AAP. No real AAP, no network. rbac_allow_insecure=true is
# used only to reach the local HTTP mock.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

reportdir=".tmp/rbac-reports"
runlog=".tmp/rbac-run.log"
rm -rf "$reportdir"; mkdir -p "$reportdir"
SENT_SECRET="TEST_SECRET_DO_NOT_PRINT"

SERVER_PID=""
stop_server() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; SERVER_PID=""; }
trap 'stop_server; :' EXIT
fail() { echo "RBAC OFFLINE FAIL: $1" >&2; exit 1; }
latest() { ls -t "$reportdir"/rbac-*.md | head -1; }

start_server() {  # inherits RBAC_SCENARIO from caller
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

ALICE='{"username":"demo-alice","organization":"Demo Linux","expected_job_templates":["Demo 01 - Linux hello","Demo 02 - Linux inventory report"],"forbidden_organizations":["Demo Network","Demo Platform"]}'

# run_rbac ; sets RC and REPORT. Caller may prepend RBAC_SCENARIO / extra -e.
run_rbac() {
  set +e
  AAP_HOSTNAME="$BASE" RBAC_DEMO_PASSWORD="$SENT_SECRET" \
  ansible-playbook verify_rbac.yml -e rbac_allow_insecure=true \
    -e "verify_report_dir=$reportdir" \
    -e "{\"rbac_users\":[$ALICE]}" "$@" >"$runlog" 2>&1
  RC=$?
  set -e
  REPORT="$(latest)"
}

# 1. expected own-org templates visible -> PASS
start_server; run_rbac; stop_server
[ "$RC" -eq 0 ] || fail "1: expected-visible should pass"
grep -q 'RESULT: PASS' "$REPORT" || fail "1: not PASS"

# 2. one expected template missing -> FAIL
RBAC_SCENARIO=missing_expected start_server; run_rbac; stop_server
[ "$RC" -ne 0 ] || fail "2: missing expected should fail"
grep -q 'expected template not visible' "$REPORT" || fail "2: missing not reported"

# 3. a forbidden organization visible -> FAIL
RBAC_SCENARIO=forbidden start_server; run_rbac; stop_server
[ "$RC" -ne 0 ] || fail "3: forbidden-org visible should fail"
grep -q 'forbidden-organization content' "$REPORT" || fail "3: forbidden not reported"

# 4. empty visible result with expected templates -> FAIL
RBAC_SCENARIO=empty start_server; run_rbac; stop_server
[ "$RC" -ne 0 ] || fail "4: empty visibility with expected should fail"
grep -q 'expected template not visible' "$REPORT" || fail "4: empty not reported"

# 5. multiple pages all inspected -> PASS (both expected across 2 pages)
RBAC_SCENARIO=twopage start_server; run_rbac; stop_server
[ "$RC" -eq 0 ] || fail "5: two-page all-expected should pass"
grep -q 'RESULT: PASS' "$REPORT" || fail "5: not PASS"

# 6. foreign content only on page 2 -> FAIL
RBAC_SCENARIO=foreign_page2 start_server; run_rbac; stop_server
[ "$RC" -ne 0 ] || fail "6: foreign on page 2 should fail"
grep -q 'forbidden-organization content' "$REPORT" || fail "6: page-2 foreign not caught"

# 7. expected template only on page 2 -> PASS
RBAC_SCENARIO=expected_page2 start_server; run_rbac; stop_server
[ "$RC" -eq 0 ] || fail "7: expected on page 2 should pass"
grep -q 'RESULT: PASS' "$REPORT" || fail "7: not PASS"

# 8. pagination HTTP error -> FAIL and report written
RBAC_SCENARIO=http_error start_server; run_rbac; stop_server
[ "$RC" -ne 0 ] || fail "8: pagination HTTP error should fail"
grep -q 'listing failed' "$REPORT" || fail "8: error not reported"

# 9. missing next / malformed shape -> FAIL
RBAC_SCENARIO=no_next start_server; run_rbac; stop_server
[ "$RC" -ne 0 ] || fail "9: missing next should fail"
grep -q 'listing failed' "$REPORT" || fail "9: malformed shape not reported"

# 10. page-limit truncation -> FAIL
RBAC_SCENARIO=truncate start_server; run_rbac -e rbac_max_pages=2; stop_server
[ "$RC" -ne 0 ] || fail "10: truncation should fail"
grep -q 'truncated' "$REPORT" || fail "10: truncation not reported"

# 11. empty configuration without override -> NOT_RUN and non-zero
start_server
set +e
AAP_HOSTNAME="$BASE" RBAC_DEMO_PASSWORD="$SENT_SECRET" \
ansible-playbook verify_rbac.yml -e rbac_allow_insecure=true \
  -e "verify_report_dir=$reportdir" >"$runlog" 2>&1
rc_empty=$?
set -e
stop_server
[ "$rc_empty" -ne 0 ] || fail "11: empty without override should exit non-zero"
grep -q 'RESULT: NOT_RUN' "$(latest)" || fail "11: not NOT_RUN"
grep -q 'RESULT: PASS' "$(latest)" && fail "11: empty must not be PASS"

# 12. empty configuration with rbac_allow_empty=true -> NOT_RUN and zero
start_server
set +e
AAP_HOSTNAME="$BASE" RBAC_DEMO_PASSWORD="$SENT_SECRET" \
ansible-playbook verify_rbac.yml -e rbac_allow_insecure=true \
  -e rbac_allow_empty=true -e "verify_report_dir=$reportdir" >"$runlog" 2>&1
rc_empty2=$?
set -e
stop_server
[ "$rc_empty2" -eq 0 ] || fail "12: empty with override should exit zero"
grep -q 'RESULT: NOT_RUN' "$(latest)" || fail "12: not NOT_RUN"

# 13. no empty path makes a network request: unreachable host, no server up.
set +e
AAP_HOSTNAME=https://unreachable.invalid RBAC_DEMO_PASSWORD="$SENT_SECRET" \
ansible-playbook verify_rbac.yml -e rbac_allow_insecure=true \
  -e rbac_allow_empty=true -e "verify_report_dir=$reportdir" >"$runlog" 2>&1
rc_noreq=$?
set -e
[ "$rc_noreq" -eq 0 ] || fail "13: empty path must not need the network"
grep -q 'RESULT: NOT_RUN' "$(latest)" || fail "13: not NOT_RUN"

# 14. UNSAFE marker present when rbac_allow_insecure=true
start_server; run_rbac; stop_server
grep -q 'UNSAFE: rbac_allow_insecure=true' "$REPORT" \
  || fail "14: insecure override not stamped UNSAFE"

# 15. password sentinel must not appear in reports or captured output
if grep -R -e "$SENT_SECRET" "$reportdir" "$runlog" >/dev/null 2>&1; then
  fail "15: password sentinel leaked into a report or captured output"
fi

echo "RBAC OFFLINE OK"
