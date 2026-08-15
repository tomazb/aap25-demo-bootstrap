#!/usr/bin/env bash
# Offline syntax check. Stubs every ansible.platform/ansible.controller module
# referenced by the playbooks so `ansible-playbook --syntax-check` resolves
# them without contacting Galaxy or Automation Hub. Deterministic; no network.
set -euo pipefail
cd "$(dirname "$0")/.."
CP=.tmp/collections/ansible_collections
rm -rf "$CP"

stub_module() {  # stub_module <collection_dir> <module_name>
  local dir="$1/plugins/modules"
  mkdir -p "$dir"
  cat > "$dir/$2.py" <<'EOF'
DOCUMENTATION = '''
module: stub
short_description: stub
description: [stub]
options: {}
author: [stub]
'''
EOF
}

# Discover referenced modules from the playbooks and task files.
mapfile -t REFS < <(grep -rhoE 'ansible\.(platform|controller)\.[a-z_]+' \
  ./*.yml tasks/*.yml | sort -u)
[ "${#REFS[@]}" -gt 0 ] || { echo "no certified module references found" >&2; exit 1; }

PLATFORM_DIR="$CP/ansible/platform"
CONTROLLER_DIR="$CP/ansible/controller"
mkdir -p "$PLATFORM_DIR/meta" "$CONTROLLER_DIR/meta"
printf '{"collection_info": {"namespace": "ansible", "name": "platform", "version": "2.5.20250702"}}\n' > "$PLATFORM_DIR/MANIFEST.json"
printf '{"collection_info": {"namespace": "ansible", "name": "controller", "version": "4.6.99"}}\n' > "$CONTROLLER_DIR/MANIFEST.json"
printf 'requires_ansible: ">=2.15"\n' > "$PLATFORM_DIR/meta/runtime.yml"

controller_modules=()
for ref in "${REFS[@]}"; do
  coll="${ref%.*}"; name="${ref##*.}"
  # ansible.controller.controller is the action-group name, not a module.
  [ "$ref" = "ansible.controller.controller" ] && continue
  case "$coll" in
    ansible.platform) stub_module "$PLATFORM_DIR" "$name" ;;
    ansible.controller) stub_module "$CONTROLLER_DIR" "$name"; controller_modules+=("$name") ;;
    *) echo "unexpected collection: $coll" >&2; exit 1 ;;
  esac
done

# Declare the controller action group used by module_defaults.
{
  printf 'requires_ansible: ">=2.15"\n'
  printf 'action_groups:\n'
  printf '  controller:\n'
  for m in "${controller_modules[@]}"; do printf '    - %s\n' "$m"; done
} > "$CONTROLLER_DIR/meta/runtime.yml"

PLAYBOOKS=("$@")
[ "${#PLAYBOOKS[@]}" -gt 0 ] || PLAYBOOKS=(bootstrap.yml teardown.yml badpractice.yml verify_smoke.yml verify_parity.yml verify_functional.yml verify_rbac.yml)
for pb in "${PLAYBOOKS[@]}"; do
  ANSIBLE_COLLECTIONS_PATH=.tmp/collections ansible-playbook --syntax-check "$pb" >/dev/null
done
echo "SYNTAX OK: ${PLAYBOOKS[*]}"
