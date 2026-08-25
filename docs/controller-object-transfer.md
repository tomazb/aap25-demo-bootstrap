# AAP 2.5 Automation Controller object transfer

> **Draft-only validation status:** Real AAP 2.5 source export and disposable-
> target import validation remain outstanding. Offline contract and harness
> coverage pass; do not treat this procedure as operationally cleared until
> both live validations succeed on disposable or independently recoverable
> AAP 2.5 systems.

This procedure uses `ansible.controller.export` and
`ansible.controller.import` to capture and recreate the Automation Controller
object types supported by the installed AAP 2.5 collection.

It is a supplemental configuration-transfer and parity artifact. It does not
replace the supported AAP 2.5 installation-type migration, which transfers the
component databases and matching encryption secrets and then performs
post-restore reconciliation.

## Boundaries

- AAP 2.5 only: the source and target controller API must report `4.6.x`.
- Use `ansible.controller >=4.6.20,<4.7.0` from an AAP 2.5 private automation
  hub or an otherwise approved source.
- `AAP_HOSTNAME` is the Platform Gateway root URL, not a direct controller URL
  and not a URL with `/api/controller/` appended.
- HTTPS and certificate validation are required outside a disposable lab.
- Export is read-only. Import mutates the target and does not support check
  mode; use a disposable or independently recoverable AAP 2.5 target.
- Do not expect credential secret values, complete job/event/audit history,
  Hub artifacts, Platform Gateway database state, instance groups, or custom
  execution-environment images in this artifact.

## Install and verify the AAP 2.5 collections

```bash
ansible-galaxy collection install -r requirements.yml
ansible-galaxy collection list | grep -E 'ansible\.(controller|platform)'
ansible-doc ansible.controller.export
ansible-doc ansible.controller.import
```

The resolved `ansible.controller` version must be in the range
`>=4.6.20,<4.7.0`.

## Export from the AAP 2.5 source

Use a dedicated protected directory. Enter the password without putting it in
shell history:

```bash
export AAP_HOSTNAME='https://source-aap.example.com'
export AAP_USERNAME='temporary-export-admin'
export AAP_VALIDATE_CERTS='true'
export EXPORT_DIR="$HOME/aap25-controller-export"

read -rsp 'Source AAP password: ' AAP_PASSWORD
printf '\n'
export AAP_PASSWORD

umask 077
ansible-playbook export.yml
unset AAP_PASSWORD
```

A successful run reports `EXPORT_COMPLETE` and creates one pair such as:

```text
controller-assets-4.6.29-20260817T120000Z.yml
controller-assets-4.6.29-20260817T120000Z.yml.sha256
```

The directory is mode `0700`; both files are mode `0600`. Verify the evidence
without printing the exported payload:

```bash
EXPORT_FILE=$(find "$EXPORT_DIR" -maxdepth 1 -type f \
  -name 'controller-assets-*.yml' -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)

test -n "$EXPORT_FILE"
stat -c '%a %U:%G %n' "$EXPORT_DIR" "$EXPORT_FILE" "$EXPORT_FILE.sha256"
(
  cd "$(dirname "$EXPORT_FILE")"
  sha256sum --check "$(basename "$EXPORT_FILE").sha256"
)
```

Expected modes are `700`, `600`, and `600`; checksum verification must report
`OK`.

## Transfer the artifact

Transfer the YAML and its `.sha256` sidecar together through the approved secure
channel. Preserve restrictive permissions. Re-run `sha256sum --check` after
transfer and before import.

## Import into an AAP 2.5 target

Confirm that the target is disposable or has a separately validated recovery
point. Use target credentials and the target Platform Gateway URL:

```bash
export AAP_HOSTNAME='https://target-aap.example.com'
export AAP_USERNAME='temporary-import-admin'
export AAP_VALIDATE_CERTS='true'
export IMPORT_FILE='/secure/path/controller-assets-4.6.29-20260817T120000Z.yml'

read -rsp 'Target AAP password: ' AAP_PASSWORD
printf '\n'
export AAP_PASSWORD

ansible-playbook import.yml -e import_confirm=true
```

The playbook requires the sidecar at `${IMPORT_FILE}.sha256` by default. Set
`IMPORT_CHECKSUM_FILE` only when the sidecar has a different approved path.
A successful run reports `IMPORT_COMPLETE`, the target controller version,
artifact checksum, resource-type count, object count, and the module's observed
`changed` value. Keep `AAP_PASSWORD` set through the negative checks below, then
unset it.

## Mandatory negative checks before a live import

Run these only against the disposable target and verify that its object counts
do not change. Keep target credentials exported for the whole section so each
command reaches its intended gate (do not `unset AAP_PASSWORD` until the checks
finish):

```bash
# Missing explicit confirmation: must fail on import_confirm before mutation.
ansible-playbook import.yml

# Import has no safe check-mode preview: must fail before import.
ansible-playbook import.yml --check -e import_confirm=true

# Checksum mismatch: copy the sidecar, alter only the copied digest, and point
# IMPORT_CHECKSUM_FILE at that copy. The run must fail before YAML parsing or
# target mutation.
cp "${IMPORT_FILE}.sha256" /tmp/bad.sha256
# Edit /tmp/bad.sha256 so the digest no longer matches IMPORT_FILE.
ansible-playbook import.yml -e import_confirm=true \
  -e IMPORT_CHECKSUM_FILE=/tmp/bad.sha256
```

Also validate failure for a missing payload, malformed YAML root, wrapped
Ansible result (`assets`, `export`, `changed`, or `failed` at the root), and a
non-`4.6.x` target. Prefer the offline harness in
`tests/export_import_offline.sh`, which already exercises those gates with
local stubs. Do not weaken the gates to make a negative test pass.

```bash
unset AAP_PASSWORD
```

## Post-import verification

1. Re-export the disposable target and compare normalized natural-key sets by
   resource type with the source artifact.
2. Check organizations, teams, users, RBAC assignments, inventories and
   hierarchy, projects, credentials and credential types, job templates,
   workflow nodes, schedules, notifications, and execution-environment
   definitions represented by the artifact.
3. Run the import a second time. Record the observed `changed` result, but judge
   idempotence by semantic parity and absence of duplicate natural keys rather
   than assuming a particular boolean result.
4. Validate external dependencies separately: project SCM reachability and CA
   trust, CyberArk credential input-source associations and lookup behavior,
   identity-provider mappings, execution images, and any instance-group or
   mesh configuration.
5. Do not launch automation against real managed hosts unless that execution
   has separate explicit authorization.

## Handling the artifact

Treat the YAML as sensitive configuration even though encrypted credential
secret values are not expected to be present. Do not commit it, attach it to a
pull request, paste it into validator output, or store it in an unprotected
workspace. Reports may include the SHA-256 digest, versions, counts, paths with
customer hostnames redacted, and key names for a defect; they must not include
passwords, tokens, private keys, credential inputs, or CyberArk secret data.
