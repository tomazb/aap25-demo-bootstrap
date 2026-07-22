#!/usr/bin/env bash
# Offline end-to-end tests of the parity pipeline using fixtures. No AAP,
# no network. Each scenario restricts the run to job_templates via
# parity_only_types and asserts exit code + report content.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
reportdir=".tmp/parity-reports"
rm -rf "$reportdir"; mkdir -p "$reportdir"

run() {  # run <fixture_subdir> <fail_mode> [extra -e...]
  ansible-playbook verify_parity.yml \
    -e "parity_fixture_dir=tests/fixtures/parity/$1" \
    -e "parity_fail_on=$2" \
    -e "verify_report_dir=$reportdir" \
    -e '{"parity_only_types": ["job_templates"]}' "${@:3}" >/dev/null 2>&1
}
latest() { ls -t "$reportdir"/parity-*.md | head -1; }
fail() { echo "PARITY OFFLINE FAIL: $1" >&2; exit 1; }

# 1. clean fixtures pass (two orgs share the JT name "Deploy" -> both present)
run pass missing || fail "clean should pass"
grep -q 'RESULT: PASS' "$(latest)" || fail "clean report not PASS"

# 2. missing target object fails in missing mode; the org-qualified key proves
#    the same-name-different-org templates stayed distinct (only Org B is gone)
run missing missing && fail "missing object should fail in missing mode"
grep -q 'RESULT: FAIL' "$(latest)" || fail "missing report not FAIL"
grep -q 'MISSING on target: `Org B / Deploy`' "$(latest)" \
  || fail "org-qualified key not distinct (expected only Org B / Deploy missing)"
grep -q 'Org A / Deploy' "$(latest)" \
  && fail "Org A / Deploy must not be missing (name-only collision)"

# 3. missing target object is report-only in none mode
run missing none || fail "missing object should be tolerated in none mode"
grep -q 'RESULT: PASS' "$(latest)" || fail "none-mode missing not PASS"

# 4. field mismatch is report-only in missing mode
run drift missing || fail "drift should be tolerated in missing mode"
grep -q 'RESULT: PASS' "$(latest)" || fail "missing-mode drift not PASS"
grep -q 'MISMATCH' "$(latest)" || fail "mismatch not reported"

# 5. field mismatch fails in drift mode
run drift drift && fail "drift should fail in drift mode"
grep -q 'RESULT: FAIL' "$(latest)" || fail "drift-mode report not FAIL"

# 6. field mismatch tolerated in none mode
run drift none || fail "drift should be tolerated in none mode"
grep -q 'RESULT: PASS' "$(latest)" || fail "none-mode drift not PASS"

# 7. duplicate normalized key fails in every mode
for mode in missing drift none; do
  run dup "$mode" && fail "duplicate key should fail in $mode mode"
  grep -q 'RESULT: FAIL' "$(latest)" || fail "dup report not FAIL ($mode)"
  grep -qi 'duplicate normalized key' "$(latest)" || fail "dup not reported"
done

# 8. all fixtures missing cannot pass, even in none mode
run empty none && fail "all-fixtures-missing should fail"
grep -q 'RESULT: FAIL' "$(latest)" || fail "empty report not FAIL"
grep -qi 'missing source fixture' "$(latest)" || fail "missing fixture not reported"

# 9. an unknown fail mode is rejected
if run pass bogus; then fail "unknown parity_fail_on should be rejected"; fi

echo "PARITY OFFLINE E2E OK"
