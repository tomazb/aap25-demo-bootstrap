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
`extra_vars` values or secrets, and are validated against the type list in
`verify_functional.yml`.

## Restricted-user RBAC verification

`verify_rbac.yml` + `tasks/rbac_user.yml` authenticate **as** each configured
`rbac_users` entry and confirm other organizations' content is absent from list
results — the RBAC proof the admin-authenticated smoke gate deliberately does
not make. The password comes only from `RBAC_DEMO_PASSWORD` (env) or a
Vault-provided `demo_user_password`, is marked `no_log`, and is never printed.
Empty `rbac_users` => `RESULT: NOT_RUN`. AD-backed login and group mapping stay
a manual checklist in the report (enterprise SSO is not automated without
confirmed support/credentials). Covered offline by `tests/rbac_offline.sh`
(correct-org pass, wrong-org cross-visibility fail, NOT_RUN).

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
