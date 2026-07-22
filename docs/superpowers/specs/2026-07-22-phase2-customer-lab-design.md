# Phase 2 — customer-shaped migration lab (design)

Date: 2026-07-22
Status: implemented (opt-in; default CI unchanged and safe)
Scope: **AAP 2.5 RPM (with gateway) -> AAP 2.5 on OpenShift** only. No AAP 2.6.

Phase 2 adds opt-in scenarios that reflect the customer environment (private
GitHub, custom execution environments, CyberArk credentials, ServiceNow,
AD-group RBAC, disposable SSH canary) while keeping the default bootstrap and
CI safe: nothing new runs unless explicitly configured, and only an
`ssh_canary_job` with `-e allow_real_managed_host_checks=true` contacts a real
host.

## Customer-shaped functional checks

Added as opt-in `functional_checks` types (see
`config/verify.customer.example.yml`, placeholders only), dispatched from
`tasks/functional_check_customer.yml`:

| type | proves | notes |
|---|---|---|
| `private_scm_project_update` | DNS/routing/internal CA/Git auth/SCM credential decrypt | reuses project_update |
| `execution_environment_job` | registry pull + runtime deps; asserts the job's EE | reads back the job's EE name |
| `external_credential_job` | CyberArk lookup + use | success is the proof; no secret is read/reported |
| `workflow_launch` | migrated workflow runs | expected success or controlled failure |
| `inventory_source_update` | source plugin config + credential | sync and wait |
| `servicenow_notification_test` | ITSM integration | requires `sandbox: true`; never production by default |
| `ssh_canary_job` | OpenShift EE reaches tier-2 over TCP/22 | OFF unless `allow_real_managed_host_checks=true`; canary host only |

All record into `functional_passed`/`functional_failures`, never print
`extra_vars` values or secrets.

### Pre-flight type validation

`tasks/functional_validate.yml` runs before any API request or module call,
driven by `functional_field_specs` in `verify_functional.yml`. Common rules:
`functional_checks` is a list, each entry a mapping with a supported `type`, a
non-empty string `name`, and a positive-integer `timeout` when present.
Required fields per type: `job_template`/`private_scm_project_update`/
`external_credential_job`/`workflow_launch` need `organization`;
`execution_environment_job` needs `organization` + `execution_environment`;
`ssh_canary_job` needs `organization` + `limit`; `inventory_source_update`
needs `inventory` + `organization`; `notification_test`/
`servicenow_notification_test` need `organization`. Typed rules:
`workflow_launch.expected_status` (when set) must be `successful` or `failed`;
`servicenow_notification_test.sandbox` must be `true`. Validation errors name
only the type/field — never `extra_vars` or secrets.

### SSH canary safety gates

`ssh_canary_job` is the only check that contacts a real host. It is disabled by
default (`allow_real_managed_host_checks: false`, `ssh_canary_allowlist: []`).
Before `job_launch`, ALL of these must hold, or the job is not launched and a
sanitized failure is recorded:

1. `allow_real_managed_host_checks` is true.
2. `ssh_canary_allowlist` is a non-empty list.
3. `check.organization` is a non-empty string.
4. `check.limit` is defined, a string, non-empty after trim.
5. `check.limit` is not a broad target (`all`, `*`, `@all`).
6. `check.limit` contains none of the pattern characters `*` `,` `:` `&` `!`.
7. `check.limit` (trimmed) is exactly present in `ssh_canary_allowlist`.

The exact-allowlist match is the primary control; the broad-pattern rejections
are defense in depth. Enabling the flag alone is insufficient — the limit must
also be allowlisted. Only disposable lab canary hosts belong in the allowlist;
production hosts, groups, broad patterns, and whole inventories must never
appear.

## Restricted-user RBAC verification

`verify_rbac.yml` + `tasks/rbac_user.yml` authenticate **as** each configured
`rbac_users` entry and verify both directions. The password comes only from
`RBAC_DEMO_PASSWORD` (env) or a Vault-provided `demo_user_password`, is marked
`no_log`, and is never printed or placed in config.

- **Pagination:** all visible job templates are retrieved via the hardened
  `tasks/paginated_get.yml` (origin pinning, HTTPS/cert behavior, `no_log`
  password), following every page. A pagination error or truncation is a
  failure and partial rows are never evaluated as complete.
- **Positive:** each `expected_job_templates` entry must be visible exactly once
  and belong to the user's `organization`. Missing => FAIL, duplicate => FAIL.
  A user who sees zero templates cannot pass when expected templates are set.
- **Negative:** any visible template from a `forbidden_organizations` entry =>
  FAIL. Only explicitly configured organizations are treated as forbidden.
- **Config validation:** non-empty username/organization, a non-empty
  duplicate-free `expected_job_templates`, a duplicate-free
  `forbidden_organizations`, and the organization must not be forbidden.
- **Empty behavior:** `rbac_allow_empty` mirrors `functional_allow_empty` —
  empty `rbac_users` writes `RESULT: NOT_RUN` and exits non-zero by default;
  `-e rbac_allow_empty=true` exits 0 but still reports `NOT_RUN` (never PASS).
  The empty path makes no network call.

AD-backed login and group mapping stay a manual checklist in the report
(enterprise SSO is not automated without confirmed support/credentials).
Covered offline by `tests/rbac_offline.sh` (15 scenarios: positive/negative,
multi-page incl. foreign/expected on page 2, HTTP error, missing-next,
truncation, empty NOT_RUN with/without override, no-network empty path, UNSAFE
marker, password-sentinel scan).

## Offline customer-functional coverage

`tests/customer_functional_offline.sh` exercises every customer check against
local stub `ansible.controller` modules (deterministic ids/status + a sanitized
invocation marker) and the local mock AAP: success, module failure, pre-flight
validation, EE match/mismatch and readback error, workflow expected/controlled/
unexpected/invalid status, notification 0/1/2 matches and result, and every
SSH-canary safety gate (proving `job_launch` is not called on a guard failure).
A final sentinel scan fails if `TEST_SECRET_DO_NOT_PRINT`,
`TEST_TOKEN_DO_NOT_PRINT`, or `TEST_EXTRA_VAR_DO_NOT_PRINT` appears in any
report, marker, or captured output. No external network, no Galaxy.

## What the offline tests do NOT prove

The offline suite uses mocks and stubs. It does **not** prove: on-premises
GitHub connectivity; CyberArk integration; that a custom EE image can be pulled
by OpenShift; the tier-2 firewall/SSH path; ServiceNow integration; or AD login
and group mappings. Those require the live acceptance run below. No live AAP
result is claimed from offline tests. AAP 2.6 is out of scope.

## Expanded parity (design; disabled until real fixtures exist)

Migration-critical object types and relationships to add incrementally, each
only after its AAP 2.5 API shape is confirmed against a real response and
covered by fixtures. **Not enabled** in `config/verify.yml`; they must not be
guessed:

- groups; group -> host associations; inventory sources and their credentials
- custom credential types; project credentials/update flags
- job-template inventory/credentials/EE; job type, become, forks, limit,
  verbosity, tags, ask-on-launch flags; survey specs; notification associations
- workflow nodes/edges/approvals/node prompts
- schedule rrule + parent association
- organization/team memberships; platform role assignments
- gateway authenticator definitions and maps

Rules when adding: never compare credential secrets; redact sensitive fields;
canonicalize structured values (sort unordered lists, normalize variable
dicts) before comparing; preserve order where it matters; add fixture coverage
for every field. Gateway RBAC/authenticator checks stay disabled until backed
by real AAP 2.5 response fixtures.

## Two migration-rehearsal lanes

**Lane A — migration fidelity**

1. Seed the AAP 2.5 RPM source; add optional customer-shaped content.
2. Capture source smoke + functional reports.
3. Migrate to AAP 2.5 on OpenShift with the approved process.
4. Run parity (source -> target) and functional + RBAC on the target.
5. Record manual remediation.

**Lane B — clean rebuild**

1. Create a fresh AAP 2.5 OpenShift target.
2. Rebuild selected configuration declaratively.
3. Populate credentials through approved external-secret workflows.
4. Run the same verification suite.
5. Compare effort, downtime, RBAC quality, obsolete content, repeatability, and
   rollback complexity.

The code does not choose the strategy; it produces comparable evidence for both.

## Live acceptance (still outstanding)

Offline tests pass. A real acceptance run must still cover: source & target
gateway auth; multi-page API content; duplicate names across orgs; private
GitHub sync; custom EE pull + launch; CyberArk-backed credential use; a real
disposable SSH canary; workflow launch; inventory-source update; schedule
verification; ServiceNow sandbox; restricted-user visibility; and manual AD
group-mapping, instance/container-group, mesh, and private automation hub
reviews. Offline tests passed; live AAP 2.5 RPM-to-OpenShift acceptance remains
outstanding.
