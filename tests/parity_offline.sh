#!/usr/bin/env bash
# Offline end-to-end test of the parity pipeline using fixtures.
# Expects: run fails (P Lost missing, P Drift branch mismatch), report
# says FAIL, and the second report-only run passes.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf .tmp/parity-reports && mkdir -p .tmp/parity-reports
if ansible-playbook verify_parity.yml \
    -e parity_fixture_dir=tests/fixtures/parity \
    -e verify_report_dir=.tmp/parity-reports; then
  echo "ERROR: expected parity failure" >&2; exit 1
fi
report=$(ls .tmp/parity-reports/parity-*.md)
grep -q 'RESULT: FAIL' "$report"
grep -q 'P Lost' "$report"
grep -q 'P Drift' "$report"
ansible-playbook verify_parity.yml \
  -e parity_fixture_dir=tests/fixtures/parity \
  -e verify_report_dir=.tmp/parity-reports \
  -e parity_fail_on=none
echo "PARITY OFFLINE E2E OK"
