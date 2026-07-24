#!/usr/bin/env bash
# Offline behavioural tests for the customer-shaped functional checks. Uses
# local stub ansible.controller modules (deterministic ids/status + sanitized
# invocation marker) and the local mock AAP server. No AAP, no Galaxy, no real
# GitHub/CyberArk/ServiceNow/registry/SSH, no external network.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

workdir=".tmp/cf"
rm -rf "$workdir"; mkdir -p "$workdir"
reportdir="$workdir/reports"; mkdir -p "$reportdir"
# Per-run marker/runlog (never overwritten) so the final sentinel scan sees
# EVERY scenario's markers and captured output, not just the last one.
run_number=0
marker="$workdir/markers-0.log"
runlog="$workdir/run-0.log"
: > "$marker"

# Sentinels that must never surface in reports, markers, or captured output.
SENT_SECRET="TEST_SECRET_DO_NOT_PRINT"
SENT_TOKEN="TEST_TOKEN_DO_NOT_PRINT"
SENT_XVAR="TEST_EXTRA_VAR_DO_NOT_PRINT"

SERVER_PID=""
stop_server() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; SERVER_PID=""; }
trap 'stop_server; :' EXIT
fail() { echo "CUSTOMER FUNCTIONAL FAIL: $1" >&2; exit 1; }

start_server() {  # inherits CUSTOMER_* env from caller
  local portfile; portfile="$(mktemp)"
  SMOKE_SCENARIO=happy python3 tests/mock_aap_server.py "$portfile" &
  SERVER_PID=$!
  local port=""
  for _ in $(seq 1 50); do
    [ -s "$portfile" ] && { port="$(cat "$portfile")"; break; }; sleep 0.1
  done
  rm -f "$portfile"; [ -n "$port" ] || fail "mock server did not start"
  BASE="http://127.0.0.1:${port}"
}

latest() { ls -t "$reportdir"/functional-*.md | head -1; }

# run_fn <checks-json-extra-args...>  ; sets RC and REPORT, appends to runlog.
# Caller must have called start_server and may export STUB_* / allow flag envs.
run_fn() {
  run_number=$((run_number + 1))
  marker="$workdir/markers-${run_number}.log"
  runlog="$workdir/run-${run_number}.log"
  : > "$marker"
  set +e
  STUB_MARKER="$marker" \
  AAP_HOSTNAME="$BASE" AAP_USERNAME=admin AAP_PASSWORD="$SENT_SECRET" \
  ANSIBLE_COLLECTIONS_PATH=tests/stubs/collections \
  ansible-playbook verify_functional.yml \
    -e functional_allow_insecure=true \
    -e "verify_report_dir=$reportdir" \
    "$@" >"$runlog" 2>&1
  RC=$?
  set -e
  REPORT="$(latest)"
}

launched() { grep -q "$1" "$marker"; }        # module name present in marker
not_launched() { ! grep -q "$1" "$marker"; }

# ============================ A. private_scm_project_update ================
CUSTOMER_SNOW_ORG="Demo Platform" start_server
run_fn -e '{"functional_checks":[{"type":"private_scm_project_update","name":"P","organization":"Demo Linux","extra_vars":{"m":"'"$SENT_XVAR"'"}}]}'
[ "$RC" -eq 0 ] || fail "A: private_scm success should pass"
grep -q 'RESULT: PASS' "$REPORT" || fail "A: not PASS"
launched project_update || fail "A: project_update not launched"
stop_server

start_server
STUB_FAIL_NAMES=P run_fn -e '{"functional_checks":[{"type":"private_scm_project_update","name":"P","organization":"Demo Linux"}]}'
[ "$RC" -ne 0 ] || fail "A: module failure should fail"
grep -q 'private_scm_project_update P failed' "$REPORT" || fail "A: failure not aggregated"
stop_server

start_server
run_fn -e '{"functional_checks":[{"type":"private_scm_project_update","name":"P"}]}'
[ "$RC" -ne 0 ] || fail "A: missing organization should preflight-fail"
not_launched project_update || fail "A: module ran despite invalid config"
stop_server

# ============================ B. execution_environment_job ================
CUSTOMER_EE="custom-ee" start_server
run_fn -e '{"functional_checks":[{"type":"execution_environment_job","name":"EEJob","organization":"Demo Linux","execution_environment":"custom-ee","extra_vars":{"m":"'"$SENT_XVAR"'"}}]}'
[ "$RC" -eq 0 ] || fail "B: matching EE should pass"
grep -q 'execution_environment_job EEJob (job 777)' "$REPORT" || fail "B: job id/name not in report"
stop_server

CUSTOMER_EE="other-ee" start_server
run_fn -e '{"functional_checks":[{"type":"execution_environment_job","name":"EEJob","organization":"Demo Linux","execution_environment":"custom-ee"}]}'
[ "$RC" -ne 0 ] || fail "B: EE mismatch should fail"
grep -q 'RESULT: FAIL' "$REPORT" || fail "B: mismatch not FAIL"
stop_server

start_server
run_fn -e '{"functional_checks":[{"type":"execution_environment_job","name":"EEJob","organization":"Demo Linux"}]}'
[ "$RC" -ne 0 ] || fail "B: missing execution_environment should preflight-fail"
not_launched job_launch || fail "B: job ran despite missing EE field"
stop_server

CUSTOMER_JOB_READ_FAIL=1 start_server
run_fn -e '{"functional_checks":[{"type":"execution_environment_job","name":"EEJob","organization":"Demo Linux","execution_environment":"custom-ee"}]}'
[ "$RC" -ne 0 ] || fail "B: job readback error should fail"
stop_server

# ============================ C. external_credential_job ==================
start_server
run_fn -e '{"functional_checks":[{"type":"external_credential_job","name":"XC","organization":"Demo Linux","extra_vars":{"tok":"'"$SENT_TOKEN"'"}}]}'
[ "$RC" -eq 0 ] || fail "C: external cred success should pass"
grep -q 'external_credential_job XC (job 777)' "$REPORT" || fail "C: job id not in report"
stop_server

start_server
STUB_FAIL_NAMES=XC run_fn -e '{"functional_checks":[{"type":"external_credential_job","name":"XC","organization":"Demo Linux"}]}'
[ "$RC" -ne 0 ] || fail "C: module failure should fail"
stop_server

# ============================ D. workflow_launch =========================
start_server
STUB_STATUS=successful run_fn -e '{"functional_checks":[{"type":"workflow_launch","name":"WF","organization":"Demo Platform","expected_status":"successful"}]}'
[ "$RC" -eq 0 ] || fail "D: expected successful should pass"
stop_server

start_server
STUB_STATUS=failed run_fn -e '{"functional_checks":[{"type":"workflow_launch","name":"WF","organization":"Demo Platform","expected_status":"failed"}]}'
[ "$RC" -eq 0 ] || fail "D: expected controlled failure should pass"
stop_server

start_server
STUB_STATUS=successful run_fn -e '{"functional_checks":[{"type":"workflow_launch","name":"WF","organization":"Demo Platform","expected_status":"failed"}]}'
[ "$RC" -ne 0 ] || fail "D: unexpected status should fail"
stop_server

start_server
run_fn -e '{"functional_checks":[{"type":"workflow_launch","name":"WF","organization":"Demo Platform","expected_status":"bogus"}]}'
[ "$RC" -ne 0 ] || fail "D: invalid expected_status should preflight-fail"
not_launched workflow_launch || fail "D: workflow ran despite invalid expected_status"
stop_server

# ============================ E. inventory_source_update =================
start_server
run_fn -e '{"functional_checks":[{"type":"inventory_source_update","name":"IS","inventory":"Demo Linux Inventory","organization":"Demo Linux"}]}'
[ "$RC" -eq 0 ] || fail "E: inventory source success should pass"
launched inventory_source_update || fail "E: module not launched"
stop_server

start_server
STUB_FAIL_NAMES=IS run_fn -e '{"functional_checks":[{"type":"inventory_source_update","name":"IS","inventory":"Demo Linux Inventory","organization":"Demo Linux"}]}'
[ "$RC" -ne 0 ] || fail "E: module failure should fail"
stop_server

start_server
run_fn -e '{"functional_checks":[{"type":"inventory_source_update","name":"IS","organization":"Demo Linux"}]}'
[ "$RC" -ne 0 ] || fail "E: missing inventory should preflight-fail"
not_launched inventory_source_update || fail "E: module ran despite missing inventory"
stop_server

# ============================ F. servicenow_notification_test ============
start_server
run_fn -e '{"functional_checks":[{"type":"servicenow_notification_test","name":"SN","organization":"Demo Platform"}]}'
[ "$RC" -ne 0 ] || fail "F: missing sandbox should preflight-fail"
stop_server

start_server
run_fn -e '{"functional_checks":[{"type":"servicenow_notification_test","name":"SN","organization":"Demo Platform","sandbox":false}]}'
[ "$RC" -ne 0 ] || fail "F: sandbox=false should preflight-fail"
stop_server

CUSTOMER_SNOW_MATCHES=0 CUSTOMER_SNOW_ORG="Demo Platform" start_server
run_fn -e '{"functional_checks":[{"type":"servicenow_notification_test","name":"SN","organization":"Demo Platform","sandbox":true}]}'
[ "$RC" -ne 0 ] || fail "F: zero matches should fail"
stop_server

CUSTOMER_SNOW_MATCHES=2 CUSTOMER_SNOW_ORG="Demo Platform" start_server
run_fn -e '{"functional_checks":[{"type":"servicenow_notification_test","name":"SN","organization":"Demo Platform","sandbox":true}]}'
[ "$RC" -ne 0 ] || fail "F: multiple matches should fail"
stop_server

CUSTOMER_SNOW_MATCHES=1 CUSTOMER_SNOW_ORG="Demo Platform" CUSTOMER_SNOW_STATUS=successful start_server
run_fn -e '{"functional_checks":[{"type":"servicenow_notification_test","name":"SN","organization":"Demo Platform","sandbox":true}]}'
[ "$RC" -eq 0 ] || fail "F: one match + success should pass"
stop_server

CUSTOMER_SNOW_MATCHES=1 CUSTOMER_SNOW_ORG="Demo Platform" CUSTOMER_SNOW_STATUS=failed start_server
run_fn -e '{"functional_checks":[{"type":"servicenow_notification_test","name":"SN","organization":"Demo Platform","sandbox":true}]}'
[ "$RC" -ne 0 ] || fail "F: failed notification result should fail"
stop_server

# ============================ G. ssh_canary_job safety ===================
CANARY='{"type":"ssh_canary_job","name":"CAN","organization":"Demo Linux","limit":"canary-1","extra_vars":{"m":"'"$SENT_XVAR"'"}}'
AL='["canary-1"]'
# no authorization flag -> FAIL, no launch
start_server
run_fn -e "{\"functional_checks\":[$CANARY],\"ssh_canary_allowlist\":$AL}"
[ "$RC" -ne 0 ] || fail "G: no allow flag should fail"
not_launched job_launch || fail "G: canary launched without allow flag"
stop_server

# helper for allowed runs with a given limit; expect_fail=1 means guard fails
canary_case() {  # <limit> <allowlist-json> <expect_rc_nonzero> <label>
  local lim="$1" al="$2" expect="$3" label="$4"
  local chk='{"type":"ssh_canary_job","name":"CAN","organization":"Demo Linux","limit":'"$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$lim")"'}'
  start_server
  run_fn -e "{\"functional_checks\":[$chk],\"ssh_canary_allowlist\":$al}" \
         -e allow_real_managed_host_checks=true
  if [ "$expect" = "1" ]; then
    [ "$RC" -ne 0 ] || fail "G: $label should fail"
    not_launched job_launch || fail "G: $label launched despite guard"
  else
    [ "$RC" -eq 0 ] || fail "G: $label should pass"
    launched job_launch || fail "G: $label did not reach launch"
  fi
  stop_server
}
canary_case ""        '["canary-1"]' 1 "empty limit"
canary_case "all"     '["canary-1"]' 1 "all"
canary_case "*"       '["canary-1"]' 1 "star"
canary_case "@all"    '["canary-1"]' 1 "@all"
canary_case "web:&db" '["canary-1"]' 1 "pattern chars"
canary_case "other"   '["canary-1"]' 1 "non-allowlisted host"
canary_case "canary-1" '["canary-1"]' 0 "exact allowlisted canary"
# missing limit key entirely -> preflight fail, no launch
start_server
run_fn -e '{"functional_checks":[{"type":"ssh_canary_job","name":"CAN","organization":"Demo Linux"}],"ssh_canary_allowlist":["canary-1"]}' \
       -e allow_real_managed_host_checks=true
[ "$RC" -ne 0 ] || fail "G: missing limit should preflight-fail"
not_launched job_launch || fail "G: launched despite missing limit"
stop_server

# ============================ H. report/output safety ====================
# Scan ALL per-run markers, run logs, and reports across every scenario.
if grep -R -e "$SENT_SECRET" -e "$SENT_TOKEN" -e "$SENT_XVAR" "$workdir" >/dev/null 2>&1; then
  echo "sentinel leak locations:" >&2
  grep -RIl -e "$SENT_SECRET" -e "$SENT_TOKEN" -e "$SENT_XVAR" "$workdir" >&2 || true
  fail "H: a sentinel value leaked into a report/marker/output"
fi

echo "CUSTOMER FUNCTIONAL OFFLINE OK"
