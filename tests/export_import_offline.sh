#!/usr/bin/env bash
# Execute export.yml -> artifact/checksum -> import.yml without a real AAP.
# Uses deterministic local controller stubs and a local AAP 2.5 config endpoint.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

TMP=$(mktemp -d)
PIDS=()
cleanup() {
  local pid
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  rm -rf "$TMP"
}
trap cleanup EXIT

start_config_server() {
  local version=$1
  local port_file=$2
  local i

  AAP_CONFIG_VERSION="$version" \
    python3 tests/aap25_config_server.py "$port_file" &
  PIDS+=("$!")

  for i in $(seq 1 100); do
    [[ -s "$port_file" ]] && return 0
    sleep 0.05
  done
  echo "config server for $version did not publish a port" >&2
  return 1
}

expect_failure() {
  local label=$1
  shift
  if "$@" >"$TMP/$label.log" 2>&1; then
    echo "$label unexpectedly succeeded" >&2
    cat "$TMP/$label.log" >&2
    return 1
  fi
}

export ANSIBLE_COLLECTIONS_PATH="$PWD/tests/stubs/collections"
export ANSIBLE_LOCAL_TEMP="$TMP/ansible-local"
export ANSIBLE_REMOTE_TEMP="$TMP/ansible-remote"
mkdir -p "$ANSIBLE_LOCAL_TEMP" "$ANSIBLE_REMOTE_TEMP"

PORT_FILE="$TMP/aap25.port"
start_config_server "4.6.29" "$PORT_FILE"
AAP25_PORT=$(cat "$PORT_FILE")

export AAP_HOSTNAME="http://127.0.0.1:$AAP25_PORT"
export AAP_USERNAME="offline-admin"
export AAP_PASSWORD="offline-password"
export AAP_VALIDATE_CERTS="false"
export EXPORT_DIR="$TMP/export"
export STUB_EXPECT_CONTROLLER_HOST="$AAP_HOSTNAME"
export STUB_EXPORT_MARKER="$TMP/export-marker.json"

ansible-playbook export.yml \
  -e export_allow_insecure=true >"$TMP/export.log" 2>&1
grep -q "EXPORT_COMPLETE" "$TMP/export.log"

mapfile -t EXPORT_FILES < <(
  find "$EXPORT_DIR" -maxdepth 1 -type f \
    -name 'controller-assets-*.yml' -print
)
[[ "${#EXPORT_FILES[@]}" -eq 1 ]] || {
  echo "expected one export YAML, found ${#EXPORT_FILES[@]}" >&2
  exit 1
}
EXPORT_FILE=${EXPORT_FILES[0]}
CHECKSUM_FILE="$EXPORT_FILE.sha256"

[[ -f "$CHECKSUM_FILE" ]]
[[ "$(stat -c '%a' "$EXPORT_DIR")" == "700" ]]
[[ "$(stat -c '%a' "$EXPORT_FILE")" == "600" ]]
[[ "$(stat -c '%a' "$CHECKSUM_FILE")" == "600" ]]
(
  cd "$(dirname "$EXPORT_FILE")"
  sha256sum --check "$(basename "$CHECKSUM_FILE")" >/dev/null
)

python3 - "$EXPORT_FILE" "$STUB_EXPORT_MARKER" <<'PY'
import json
import sys

import yaml

export_file, marker_file = sys.argv[1:]
with open(export_file, encoding="utf-8") as stream:
    assets = yaml.safe_load(stream)
with open(marker_file, encoding="utf-8") as stream:
    marker = json.load(stream)

expected = {
    "organizations": [
        {
            "name": "Demo Linux",
            "description": "offline object-transfer fixture",
        }
    ],
    "inventories": [
        {
            "name": "Demo Linux Inventory",
            "organization": {
                "name": "Demo Linux",
                "type": "organization",
            },
        }
    ],
    "job_templates": [
        {
            "name": "Demo 01 - Linux hello",
            "organization": {
                "name": "Demo Linux",
                "type": "organization",
            },
        }
    ],
}
assert assets == expected
assert marker["all"] is True
assert marker["prefix"] == "/api/controller/"
assert marker["controller_host"].startswith("http://127.0.0.1:")
assert not ({"assets", "export", "changed", "failed"} & set(assets))
assert all(isinstance(value, list) for value in assets.values())
assert sum(len(value) for value in assets.values()) == 3
PY

export IMPORT_FILE="$EXPORT_FILE"
unset IMPORT_CHECKSUM_FILE || true
export STUB_IMPORT_CAPTURE="$TMP/import-capture.json"
rm -f "$STUB_IMPORT_CAPTURE"

ansible-playbook import.yml \
  -e import_allow_insecure=true \
  -e import_confirm=true >"$TMP/import.log" 2>&1
grep -q "IMPORT_COMPLETE" "$TMP/import.log"

python3 - "$EXPORT_FILE" "$STUB_IMPORT_CAPTURE" <<'PY'
import json
import sys

import yaml

with open(sys.argv[1], encoding="utf-8") as stream:
    exported = yaml.safe_load(stream)
with open(sys.argv[2], encoding="utf-8") as stream:
    imported = json.load(stream)
assert imported == exported
PY

# No explicit confirmation: fail before the import module can write its marker.
rm -f "$STUB_IMPORT_CAPTURE"
expect_failure no-confirmation \
  ansible-playbook import.yml -e import_allow_insecure=true
[[ ! -e "$STUB_IMPORT_CAPTURE" ]]

# Check mode is not a safe import preview and must be rejected before mutation.
rm -f "$STUB_IMPORT_CAPTURE"
expect_failure check-mode \
  ansible-playbook import.yml --check \
    -e import_allow_insecure=true -e import_confirm=true
[[ ! -e "$STUB_IMPORT_CAPTURE" ]]

# A checksum mismatch must fail before parsing or target mutation.
BAD_CHECKSUM="$TMP/bad.sha256"
printf '%064d  %s\n' 0 "$(basename "$EXPORT_FILE")" >"$BAD_CHECKSUM"
export IMPORT_CHECKSUM_FILE="$BAD_CHECKSUM"
rm -f "$STUB_IMPORT_CAPTURE"
expect_failure checksum-mismatch \
  ansible-playbook import.yml \
    -e import_allow_insecure=true -e import_confirm=true
[[ ! -e "$STUB_IMPORT_CAPTURE" ]]
unset IMPORT_CHECKSUM_FILE

# A wrapped Ansible module result must not be accepted as a canonical artifact.
WRAPPED_FILE="$TMP/wrapped.yml"
python3 - "$EXPORT_FILE" "$WRAPPED_FILE" <<'PY'
import sys

import yaml

with open(sys.argv[1], encoding="utf-8") as stream:
    assets = yaml.safe_load(stream)
with open(sys.argv[2], "w", encoding="utf-8") as stream:
    yaml.safe_dump({"assets": assets, "changed": False}, stream)
PY
(
  cd "$TMP"
  sha256sum "$(basename "$WRAPPED_FILE")" >"$(basename "$WRAPPED_FILE").sha256"
)
export IMPORT_FILE="$WRAPPED_FILE"
rm -f "$STUB_IMPORT_CAPTURE"
expect_failure wrapped-result \
  ansible-playbook import.yml \
    -e import_allow_insecure=true -e import_confirm=true
[[ ! -e "$STUB_IMPORT_CAPTURE" ]]

# A non-list resource section must be rejected before target mutation.
MALFORMED_FILE="$TMP/malformed.yml"
printf '%s\n' 'organizations: not-a-list' >"$MALFORMED_FILE"
(
  cd "$TMP"
  sha256sum "$(basename "$MALFORMED_FILE")" >"$(basename "$MALFORMED_FILE").sha256"
)
export IMPORT_FILE="$MALFORMED_FILE"
rm -f "$STUB_IMPORT_CAPTURE"
expect_failure malformed-resource \
  ansible-playbook import.yml \
    -e import_allow_insecure=true -e import_confirm=true
[[ ! -e "$STUB_IMPORT_CAPTURE" ]]

# A controller outside the AAP 2.5 4.6.x family must fail before export/import.
NON25_PORT_FILE="$TMP/non25.port"
start_config_server "4.7.0" "$NON25_PORT_FILE"
NON25_PORT=$(cat "$NON25_PORT_FILE")
export AAP_HOSTNAME="http://127.0.0.1:$NON25_PORT"
export STUB_EXPECT_CONTROLLER_HOST="$AAP_HOSTNAME"
export EXPORT_DIR="$TMP/non25-export"
rm -f "$STUB_EXPORT_MARKER"
expect_failure non25-export \
  ansible-playbook export.yml -e export_allow_insecure=true
[[ ! -e "$STUB_EXPORT_MARKER" ]]
[[ ! -d "$EXPORT_DIR" ]]

export IMPORT_FILE="$EXPORT_FILE"
unset IMPORT_CHECKSUM_FILE || true
rm -f "$STUB_IMPORT_CAPTURE"
expect_failure non25-import \
  ansible-playbook import.yml \
    -e import_allow_insecure=true -e import_confirm=true
[[ ! -e "$STUB_IMPORT_CAPTURE" ]]

echo "EXPORT/IMPORT OFFLINE OK"
