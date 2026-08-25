# AAP 2.5 Controller Object Transfer Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `export.yml` and `import.yml` a fail-closed, mutually compatible AAP 2.5 Automation Controller object-transfer pair with offline regression coverage.

**Architecture:** Persist only the `ansible.controller.export` module's `assets` mapping, protect it with restrictive permissions and a SHA-256 sidecar, and feed that exact mapping to `ansible.controller.import`. Bind both operations explicitly to the AAP 2.5 Platform Gateway controller API and reject unsafe, malformed, unconfirmed, or version-incompatible operations before mutation.

**Tech Stack:** Ansible Core 2.16.14, `ansible.controller` 4.6.x, YAML, pytest, ansible-lint, GitHub Actions.

## Global Constraints

- AAP 2.5 only; do not add AAP 2.6 APIs, collections, or documentation.
- `ansible.platform >=2.5.20250702,<2.6.0` remains unchanged.
- `ansible.controller` must remain in the 4.6 family and use floor `4.6.20`.
- Platform Gateway root URL comes from `AAP_HOSTNAME`.
- HTTPS and certificate validation remain required unless the existing explicit lab-only override is used.
- Object export/import remains supplemental to the supported database-and-secrets migration.
- Never commit or print credentials or exported payloads.

---

### Task 1: Add a failing object-transfer contract suite

**Files:**
- Create: `tests/test_export_import_contract.py`

**Interfaces:**
- Consumes: `export.yml`, `import.yml`, and `requirements.yml` as YAML/text.
- Produces: pytest gates for payload shape, gateway routing, safety, permissions, checksum, and collection floor.

- [ ] **Step 1: Write tests that require `export_output.assets` to be serialized and `imported_assets` to be passed directly to import.**
- [ ] **Step 2: Add tests for `/api/controller/v2/config/`, the `4.6.x` version gate, and `CONTROLLER_OPTIONAL_API_URLPATTERN_PREFIX=/api/controller/`.**
- [ ] **Step 3: Add tests for explicit import confirmation, regular-file checks, SHA-256 matching, private modes, and removal of soft-failure controls.**
- [ ] **Step 4: Add a test requiring `ansible.controller >=4.6.20,<4.7.0`.**
- [ ] **Step 5: Run `python3 -m pytest tests/test_export_import_contract.py -q`; expect failures against the current playbooks for every defect class.**

### Task 2: Harden export.yml

**Files:**
- Modify: `export.yml`

**Interfaces:**
- Consumes: `AAP_HOSTNAME`, `AAP_USERNAME`, `AAP_PASSWORD`, `AAP_VALIDATE_CERTS`, optional `EXPORT_DIR`.
- Produces: one canonical YAML asset mapping and `<file>.sha256` sidecar.

- [ ] **Step 1: Replace the soft `/api/v2/config/` probe with a status-checked `/api/controller/v2/config/` probe and assert controller version `4.6.x`.**
- [ ] **Step 2: Calculate one UTC timestamp and derive stable output and checksum paths.**
- [ ] **Step 3: Create the export directory with mode `0700`.**
- [ ] **Step 4: Set the controller API prefix on `ansible.controller.export`, validate `export_output.assets`, and count list-valued objects.**
- [ ] **Step 5: Write only `export_output.assets` with mode `0600`, `diff: false`, and protected logging.**
- [ ] **Step 6: Calculate SHA-256, write a mode-`0600` sidecar, and report only non-payload evidence.**

### Task 3: Harden import.yml

**Files:**
- Modify: `import.yml`

**Interfaces:**
- Consumes: explicit `IMPORT_FILE` or `import_file`, optional checksum override, `import_confirm=true`, and the target `AAP_*` credentials.
- Produces: one guarded `ansible.controller.import` invocation using the canonical mapping.

- [ ] **Step 1: Require an explicit import file, confirmation, secure transport, and non-check-mode execution.**
- [ ] **Step 2: Require regular payload and checksum files, calculate SHA-256, parse the sidecar, and fail on mismatch.**
- [ ] **Step 3: Load YAML and reject empty documents, Ansible-result wrappers, and non-list resource sections.**
- [ ] **Step 4: Probe `/api/controller/v2/config/` and assert the target controller is `4.6.x`.**
- [ ] **Step 5: Pass `imported_assets` directly to `ansible.controller.import` with the gateway prefix set.**
- [ ] **Step 6: Report `changed`, target version, source path, digest, and resource/object counts without printing payload data.**

### Task 4: Pin compatible collection behavior and extend CI

**Files:**
- Modify: `requirements.yml`
- Modify: `tests/syntax_check.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: the repository's existing offline stub-collection and lint workflow.
- Produces: persistent regression coverage for both playbooks.

- [ ] **Step 1: Raise the controller floor to `>=4.6.20,<4.7.0` and document why.**
- [ ] **Step 2: Include `export.yml` and `import.yml` in the default offline syntax-check list.**
- [ ] **Step 3: Include both playbooks in the ansible-lint CI command.**
- [ ] **Step 4: Document the canonical asset contract and live-validation boundary in `AGENTS.md`.**

### Task 5: Verify and publish

**Files:**
- Verify all modified files.

**Interfaces:**
- Consumes: complete branch diff.
- Produces: a draft PR ready for live AAP 2.5 validation.

- [ ] **Step 1: Run the focused pytest suite and confirm all tests pass.**
- [ ] **Step 2: Parse all modified YAML files with PyYAML.**
- [ ] **Step 3: Run the repository's full offline pytest, shell syntax, Ansible syntax, and ansible-lint gates.**
- [ ] **Step 4: Inspect the final diff for secrets, AAP 2.6 references, accidental payload logging, and unrelated changes.**
- [ ] **Step 5: Open a draft PR and wait for exact-head GitHub Actions results.**
- [ ] **Step 6: Prepare a validator-agent prompt that tests export on real AAP 2.5 RPM, imports only into a disposable AAP 2.5 target, checks parity/idempotence/failure gates, and returns reproducible evidence without secrets.**
