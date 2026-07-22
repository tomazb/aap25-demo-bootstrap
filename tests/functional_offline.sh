#!/usr/bin/env bash
# Offline test for verify_functional.yml NOT_RUN semantics. No network:
# functional_checks is empty so nothing is launched.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
reportdir=".tmp/functional-reports"
rm -rf "$reportdir"; mkdir -p "$reportdir"
fail() { echo "FUNCTIONAL OFFLINE FAIL: $1" >&2; exit 1; }
latest() { ls -t "$reportdir"/functional-*.md | head -1; }

# 1. empty checks without override -> NOT_RUN and non-zero exit
AAP_HOSTNAME=https://unreachable.invalid AAP_USERNAME=x AAP_PASSWORD=x \
ANSIBLE_COLLECTIONS_PATH=.tmp/collections \
ansible-playbook verify_functional.yml -e "verify_report_dir=$reportdir" \
  >/dev/null 2>&1
[ $? -ne 0 ] || fail "empty default should exit non-zero"
grep -q 'RESULT: NOT_RUN' "$(latest)" || fail "default empty not NOT_RUN"
grep -q 'RESULT: PASS' "$(latest)" && fail "empty run must not report PASS"

# 2. empty checks with explicit override -> NOT_RUN and zero exit
AAP_HOSTNAME=https://unreachable.invalid AAP_USERNAME=x AAP_PASSWORD=x \
ANSIBLE_COLLECTIONS_PATH=.tmp/collections \
ansible-playbook verify_functional.yml -e "verify_report_dir=$reportdir" \
  -e functional_allow_empty=true >/dev/null 2>&1
[ $? -eq 0 ] || fail "empty with override should exit zero"
grep -q 'RESULT: NOT_RUN' "$(latest)" || fail "override empty not NOT_RUN"

echo "FUNCTIONAL OFFLINE OK"
