#!/usr/bin/env bash
# Syntax-check playbooks without Red Hat hub access: stub the certified
# collections just enough for module resolution.
set -euo pipefail
cd "$(dirname "$0")/.."
CP=.tmp/collections/ansible_collections
mkdir -p "$CP/ansible/platform/plugins/modules" "$CP/ansible/platform/meta"
printf 'requires_ansible: ">=2.15"\n' > "$CP/ansible/platform/meta/runtime.yml"
rm -f "$CP/ansible/platform/galaxy.yml"
printf '{"collection_info": {"namespace": "ansible", "name": "platform", "version": "2.5.20250702"}}\n' \
  > "$CP/ansible/platform/MANIFEST.json"
for m in organization team user role_user_assignment; do
  cat > "$CP/ansible/platform/plugins/modules/$m.py" <<'EOF'
DOCUMENTATION = '''
module: stub
short_description: stub
description: [stub]
options: {}
author: [stub]
'''
EOF
done
if [ ! -d "$CP/ansible/controller" ]; then
  if [ -d "$HOME/.ansible/collections/ansible_collections/ansible/controller" ]; then
    cp -r "$HOME/.ansible/collections/ansible_collections/ansible/controller" "$CP/ansible/controller"
  else
    ansible-galaxy collection install 'awx.awx:>=24.6.0,<24.7.0' -p .tmp/collections >/dev/null
    cp -r "$CP/awx/awx" "$CP/ansible/controller"
    printf '{"collection_info": {"namespace": "ansible", "name": "controller", "version": "4.6.99"}}\n' \
      > "$CP/ansible/controller/MANIFEST.json"
  fi
fi
PLAYBOOKS=("$@")
[ ${#PLAYBOOKS[@]} -gt 0 ] || PLAYBOOKS=(bootstrap.yml teardown.yml verify_smoke.yml verify_parity.yml verify_functional.yml)
for pb in "${PLAYBOOKS[@]}"; do
  ANSIBLE_COLLECTIONS_PATH=.tmp/collections ansible-playbook --syntax-check "$pb"
done
echo "SYNTAX OK: ${PLAYBOOKS[*]}"
