#!/usr/bin/env bash
# Offline test: with functional_checks empty the playbook must succeed
# without any network access and write a report.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf .tmp/functional-reports && mkdir -p .tmp/functional-reports
AAP_HOSTNAME=https://unreachable.invalid AAP_USERNAME=x AAP_PASSWORD=x \
ANSIBLE_COLLECTIONS_PATH=.tmp/collections \
ansible-playbook verify_functional.yml -e verify_report_dir=.tmp/functional-reports
report=$(ls .tmp/functional-reports/functional-*.md)
grep -q 'RESULT: PASS' "$report"
grep -q 'No functional checks configured' "$report"
echo "FUNCTIONAL OFFLINE OK"
