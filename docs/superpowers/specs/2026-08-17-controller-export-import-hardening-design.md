# AAP 2.5 Controller Object Transfer Hardening Design

## Purpose

Harden `export.yml` and `import.yml` as a supplemental Automation Controller
configuration-transfer workflow for AAP 2.5. The workflow captures and imports
only object types supported by the installed `ansible.controller` 4.6.x
exporter. It is not a replacement for the supported RPM-to-OpenShift database,
secret-key, and component reconciliation migration procedure.

## Problems in the current implementation

- `ansible.controller.export` returns the portable mapping in
  `export_output.assets`, but `export.yml` serializes the complete registered
  module result.
- `import.yml` reads `imported_assets.export`, which is not the documented
  import contract, and reports `import_output.status`, which the module does not
  return.
- The version probe uses `/api/v2/config/` instead of the AAP 2.5 Platform
  Gateway controller route `/api/controller/v2/config/`.
- Export/import do not set the gateway API prefix required by the exporter on
  affected AAP 2.5 collection builds.
- Missing files and API failures can be softened, allowing an apparent success
  without an import.
- The output filename is calculated more than once, permissions are too broad,
  and no integrity sidecar is produced.
- Import has no deliberate operator confirmation or artifact integrity gate.

## Selected design

### 1. Canonical artifact contract

The YAML export file contains exactly `export_output.assets`: a non-empty
mapping whose values are resource lists. It does not contain Ansible result
metadata such as `changed`, `failed`, or a second `assets` wrapper. Import loads
that mapping and passes it directly as `assets: "{{ imported_assets }}"`.

### 2. AAP 2.5 and Platform Gateway binding

Both playbooks accept the Platform Gateway root URL in `AAP_HOSTNAME`, probe
`/api/controller/v2/config/`, and fail unless the returned controller version
is in the `4.6.x` family used by AAP 2.5. The controller export/import tasks set
`CONTROLLER_OPTIONAL_API_URLPATTERN_PREFIX=/api/controller/` explicitly.

The repository remains bounded to `ansible.controller >=4.6.20,<4.7.0`. The
4.6.20 floor is selected because the AAP 2.5 async stream contains the Platform
Gateway export-prefix correction in that update line; no AAP 2.6 collection is
introduced.

### 3. Export flow

1. Validate credentials and secure transport.
2. Probe and validate the AAP 2.5 controller version.
3. Calculate one UTC timestamp and one output path.
4. Create the output directory with mode `0700`.
5. Export all resource types supported by the installed exporter.
6. Validate the returned asset mapping and list-valued resource sections.
7. Write the YAML file with mode `0600`, `diff: false`, and protected logging.
8. Calculate SHA-256 and write a same-name `.sha256` sidecar with mode `0600`.
9. Report only paths, version, counts, and digest; never print the payload.

### 4. Import flow

1. Require an explicit `IMPORT_FILE` or `-e import_file=...` value.
2. Require `-e import_confirm=true`; check mode is rejected because the import
   module does not support a safe preview.
3. Validate secure transport and both regular files: payload and checksum.
4. Calculate and compare SHA-256 before parsing the YAML.
5. Reject empty, wrapped, or non-list-valued resource documents.
6. Probe the target and require controller `4.6.x`.
7. Pass the canonical mapping directly to `ansible.controller.import` with the
   gateway prefix set.
8. Report `changed`, target version, source path, digest, and resource counts.

### 5. Security and operability

Username/password authentication remains supported to match the repository's
existing `AAP_*` contract. Files and task output are protected by default;
`export_no_log=false` or `import_no_log=false` is a lab-only troubleshooting
choice. The existing HTTPS and certificate-validation escape hatches remain
explicitly lab-only.

### 6. Verification

A new offline pytest contract suite first reproduces the current defects and
then enforces the canonical payload, gateway route/prefix, AAP 2.5 version
boundary, checksum and confirmation gates, permissions, and collection floor.
The existing syntax-check and ansible-lint CI scopes are extended to include
both playbooks. Live acceptance remains a separate validator-agent exercise on
real AAP 2.5 source and disposable target systems.

## Non-goals and limitations

- No AAP 2.6 code, APIs, collections, or migration guidance.
- No attempt to preserve job history, job events, audit history, Hub content,
  gateway database state, encrypted credential secret values, instance groups,
  or custom execution-environment images.
- No claim that importing controller objects is equivalent to the supported
  full-platform migration.
- No import into a production target during automated validation.
