# AAP 2.5 RPM→OCP migration verification — design

Date: 2026-07-22
Status: approved for implementation (autonomous run; user pre-authorized full
brainstorm → spec → implement cycle; assumptions recorded below)

## Problem

The repo bootstraps a fresh AAP 2.5 with safe demo content. Migration projects
(RPM-based AAP → AAP 2.5 on OpenShift) need to *verify* the migration, which
the seeder alone does not do. Three verification layers were identified:

1. **Smoke gate** — is the OCP target healthy end-to-end (auth, RBAC, sync,
   SCM, execution)?
2. **Content parity** — did every object arrive from the RPM source?
3. **Functional equivalence** — does migrated content actually *run* on the
   target (including the credential-decrypt / `SECRET_KEY` proof)?

## Assumptions (autonomous decisions)

- **Source** may be AAP 2.4 or 2.5 on RPM: controller-centric API
  (`/api/v2`), no gateway. Users/teams/orgs are read from the controller on
  the source side. **Target** is always AAP 2.5 gateway
  (`/api/gateway/v1` for identity objects, `/api/controller/v2` for
  automation objects).
- Verification must be **read-only against the source**. Target gets only
  explicitly configured functional launches.
- Each layer is a **separately runnable playbook** that exits non-zero on
  failure, so all three are pipeline-gate-able.
- Reports are written to `reports/` (gitignored): one Markdown summary per
  run plus the raw diff as JSON.
- Secrets never appear in reports or task output (`no_log` on auth-bearing
  loops where Ansible would echo request parameters).
- **YAGNI cuts:** demo-prefix parametrization (demo names are already unique;
  parallel demo runs are not a migration use case); automated SSO/LDAP login
  testing (browser flows — manual checklist instead); settings/instance-group
  parity (too environment-specific — manual checklist instead).

## Approaches considered

- **A. Pure Ansible playbooks + a small filter plugin** for
  normalize/diff logic. No new toolchain; matches repo philosophy
  (ansible-core + `ansible.platform`/`ansible.controller`); diff logic in
  Python where Jinja would be unreadable; filter plugin unit-testable with
  pytest offline. **Chosen.**
- B. `infra.aap_configuration` `filetree_create` dumps on both sides + a diff
  script. Leverages supported config-as-code tooling, but pulls in a large
  collection dependency, its dump format shifts between versions, and it
  exports config-as-code semantics rather than verification semantics.
- C. Standalone Python CLI (`requests`). Most flexible, but introduces a
  second toolchain into an Ansible-only repo and duplicates auth handling the
  collections already solve.

## Architecture

Four new top-level playbooks (flat layout, matching `bootstrap.yml`), one
shared task file, one filter plugin, one config file:

```
teardown.yml              # Layer 1: remove everything bootstrap.yml created
verify_smoke.yml          # Layer 1: assert the bootstrap demo state exists & ran
verify_parity.yml         # Layer 2: source vs target object diff
verify_functional.yml     # Layer 3: run migrated content on the target
config/verify.yml         # parity object-type map + functional check list
tasks/paginated_get.yml   # shared: follow API pagination, accumulate results
filter_plugins/parity.py  # normalize_objects / parity_diff / parity_summary
tests/                    # pytest for the filter plugin + JSON fixtures
reports/                  # gitignored run output
```

### Auth model

- Target: existing `AAP_*` env vars (same as `bootstrap.yml`).
- Source (parity only): `SOURCE_AAP_HOSTNAME` / `SOURCE_AAP_USERNAME` /
  `SOURCE_AAP_PASSWORD` / `SOURCE_AAP_VALIDATE_CERTS` (defaults true).
- All API reads use `ansible.builtin.uri` with basic auth; collections are
  used only where objects are created/launched (functional layer), reusing
  the `module_defaults` bridge from `bootstrap.yml`.

### Layer 1 — smoke gate

- `teardown.yml`: deletes in strict reverse dependency order — job templates,
  projects, groups, hosts, inventories (controller) then users, teams,
  organizations (gateway) — driven by the same `config/demo.yml` lists the
  bootstrap consumes, so it removes exactly what bootstrap creates. Role
  assignments die with their objects. Job history rows for deleted templates
  remain (controller behavior) — documented, not fought.
- `verify_smoke.yml`: read-only asserts against the target —
  every demo org/team/user/inventory/project/template exists (user checks
  skipped when `demo_create_users` is false, mirroring the bootstrap), each project's
  last update succeeded, job history contains ≥1 successful run per seeded
  template and ≥1 failed run of the controlled-outcome template. Emits a
  pass/fail Markdown report; any failed assert fails the play at the end
  (collect-then-fail, so one run reports all problems).

### Layer 2 — content parity

- Object types compared (each toggleable in `config/verify.yml`):
  organizations, users, teams, credentials (name + credential_type name —
  existence only, secrets can't be compared), projects (name, scm_type,
  scm_url, scm_branch), inventories (name, org, kind), hosts (per-inventory
  name sets), job_templates (name, playbook, project name),
  workflow_job_templates (name), schedules (name, enabled, unified JT name),
  notification_templates (name, type), execution_environments (name, image),
  labels (name).
- Flow per type: paginated GET from source `/api/v2/<type>` and target
  (gateway or controller path per type) → `normalize_objects` filter maps
  raw API rows to `{key, fields}` records (handles source/target field-shape
  drift, e.g. identity objects coming from gateway vs controller) →
  `parity_diff` filter returns `{missing_on_target, extra_on_target,
  field_mismatches}` → accumulated into one report.
- `parity_fail_on: missing` (default) fails the play if any source object is
  missing on target; `extra` objects on target are report-only (the demo
  content itself would otherwise trip it); `none` makes the run report-only.
- Smart inventories and constructed inventories are excluded from host-count
  comparison (membership is computed, not migrated).

### Layer 3 — functional equivalence

- Driven by `functional_checks` in `config/verify.yml` — a curated,
  per-migration list (empty by default; the playbook warns and exits 0 with
  a "nothing configured" report so it is safe in pipelines before curation):
  - `job_template` checks: launch by name/org with optional `limit`,
    `extra_vars`, `job_type: check`; wait; assert success. A check whose JT
    uses a migrated credential is the **`SECRET_KEY` decrypt proof** — wrong
    key means the credential exists but the job fails at credential
    decryption.
  - `project_update` checks: trigger + wait a project sync; proves SCM
    credentials decrypt and the cluster reaches the SCM host.
  - `notification_test` checks: POST
    `/notification_templates/{id}/test/`, poll the resulting notification
    for `successful`.
- Schedules: asserts every enabled migrated schedule on target has
  `next_run` populated (scheduler alive) — parity of existence is Layer 2's
  job.
- Report ends with a static **manual checklist** section (SSO/LDAP login,
  settings review, instance groups/container groups, hop/execution node
  topology) — items that cannot be automated responsibly.

### Error handling

- API reads: `status_code: [200]`, explicit failure with the URL (creds
  never logged) on anything else; pagination loop bounded (`max_pages`,
  default 100, page_size 200) to avoid infinite loops on a broken `next`.
- All three verify playbooks collect failures into a list and fail once at
  the end with the full list — never die on the first finding.
- `teardown.yml` uses `state: absent` semantics (idempotent; absent objects
  are no-ops).

### Testing

- `filter_plugins/parity.py` is pure functions → pytest unit tests with JSON
  fixtures modeling real API shapes (source controller rows vs target
  gateway rows), including drift cases: missing object, extra object, field
  mismatch, pagination fragments, smart-inventory exclusion.
- Playbooks: `ansible-playbook --syntax-check` for all four (collection shim
  for `ansible.platform`/`ansible.controller` in CI-less local runs).
- Offline end-to-end: a fixture-mode variable (`parity_fixture_dir`) lets
  `verify_parity.yml` read the JSON fixtures instead of calling APIs, so the
  normalize→diff→report path runs completely offline; used as the
  self-test.
- Live-instance runs are documented as the real acceptance test (needs an
  AAP; not available in this environment — stated honestly in the PR).

## Out of scope

- Migrating content (this verifies; `infra.aap_configuration`/export-import
  migrates).
- Comparing credential secrets, settings values, LDAP/SSO configuration.
- EDA, automation hub content parity.
