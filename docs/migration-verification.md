# Migration verification (AAP 2.5 RPM → AAP 2.5 on OpenShift)

Four independent, pipeline-gateable playbooks help **verify** a migration from
**AAP 2.5 on RPM/RHEL (with the automation gateway)** to a fresh **AAP 2.5 on
OpenShift**. This repository does not perform the platform or database migration
— it seeds a lab and verifies a migration performed by another process.
Source-side access by the verification playbooks is always read-only; the
optional `bootstrap.yml` lab-seeding step described below is pre-verification
setup and writes disposable demo content. Each verification playbook writes a
Markdown report to `reports/` (gitignored) and exits non-zero on failure.

All verification playbooks require an HTTPS endpoint with certificate validation
before sending credentials (install private CA trust rather than disabling
validation). For a throwaway lab only, use the override corresponding to the
verification playbook: `-e smoke_allow_insecure=true`,
`-e functional_allow_insecure=true`, or `-e rbac_allow_insecure=true`. For
example:

```bash
ansible-playbook verify_smoke.yml -e smoke_allow_insecure=true
ansible-playbook verify_rbac.yml \
  -e @config/verify.rbac.example.yml -e rbac_allow_insecure=true
```

Each override bypasses that playbook's transport check and stamps an UNSAFE
marker on its report. `verify_parity.yml` has no insecure live-mode override;
both endpoints must use HTTPS with certificate validation. Never use an
insecure override against a customer or production endpoint. Operational errors
— API/transport failures, pagination truncation, duplicate normalized keys,
missing/invalid fixtures — always fail the run, in every mode.

Commands below use host-native `ansible-playbook`; for an execution environment,
substitute the `aap_run` wrapper from
[runtimes-and-prerequisites.md](runtimes-and-prerequisites.md).

## Layer 1 — target smoke gate

Run `bootstrap.yml` against the OCP target. If local users were enabled, run:

```bash
ansible-playbook verify_smoke.yml     # asserts demo objects, sync, users, and history
```

If bootstrap used `demo_create_users=false`, run this command instead (do not run
both smoke commands):

```bash
ansible-playbook verify_smoke.yml -e demo_create_users=false
```

After the selected smoke check passes, remove all demo content:

```bash
ansible-playbook teardown.yml
```

This proves admin authentication, API availability, resource synchronization to
the controller, SCM project sync state, execution, and job history for the
**current** demo templates (history is queried by the resolved template id, so
stale runs of a deleted/recreated template cannot satisfy the gate).

It does **not** prove RBAC: every request authenticates as the admin user.
Restricted-user authorization must be verified separately (Layer 4). Job-history
rows of deleted demo templates remain in the controller; that is controller
behavior, not an error.

## Layer 2 — content parity

```bash
export SOURCE_AAP_HOSTNAME='https://rpm-gateway.example.com'   # source gateway
export SOURCE_AAP_USERNAME='admin'
export SOURCE_AAP_PASSWORD='REDACTED'
# target uses AAP_HOSTNAME / AAP_USERNAME / AAP_PASSWORD
ansible-playbook verify_parity.yml
```

Compares organizations, users, teams (gateway routes), and credentials
(existence), projects, inventories, hosts, job templates, workflow job templates,
schedules, notification templates, execution environments and labels (controller
routes) between the AAP 2.5 source and the AAP 2.5 OCP target. Object types,
per-side key/field paths, and comparison scope are configured in
`config/verify.yml` (`parity_types`). Org-scoped resources use
organization-qualified keys so two objects with the same name in different
organizations stay distinct; a duplicate normalized key is an operational error.
Smart and constructed inventories are excluded from host comparison. Credential
**secrets** cannot be compared through any API; a migrated `SECRET_KEY` is proven
functionally by Layer 3 instead.

`parity_fail_on` controls the exit code (the report always lists everything):

- `missing` — fail when a source object is absent on the target; field mismatches
  are reported but do not fail.
- `drift` — fail on missing objects **or** field mismatches.
- `none` — tolerate all content differences (operational errors still fail).

Pagination is bounded by `parity_max_pages`; hitting the cap with more pages
pending is treated as truncation and fails the run.

## Layer 3 — functional equivalence

Curate `functional_checks` in `config/verify.yml` (job template launches, project
syncs, notification tests), then:

```bash
ansible-playbook verify_functional.yml
```

A launched job template that uses a migrated credential is the `SECRET_KEY`
decrypt proof: with a wrong key the credential exists but the job fails at
decryption. With no checks configured the playbook writes a `RESULT: NOT_RUN`
report and exits non-zero (NOT_RUN is not a PASS); pass
`-e functional_allow_empty=true` to exit 0 for a pre-curation pipeline. The report
ends with a manual checklist (SSO/LDAP login, settings, instance/container groups,
mesh topology) for what cannot be automated responsibly.

## Layer 4 — restricted-user RBAC

`verify_smoke.yml` authenticates as the admin user and therefore does **not**
prove team-scoped visibility. After bootstrap with local users, run:

```bash
export RBAC_DEMO_PASSWORD='…'
ansible-playbook verify_rbac.yml -e @config/verify.rbac.example.yml
```

See `config/verify.rbac.example.yml` for the seeded demo users (copy to a
gitignored overlay if you customize). For mixed customer-shaped functional + RBAC
overlays, use `config/verify.customer.example.yml` instead.

Each `rbac_users` entry must list `expected_job_templates` (positive: visible
exactly once in the user's organization) and `forbidden_organizations` (negative:
no templates from those orgs). Empty `rbac_users` writes `RESULT: NOT_RUN` and
exits non-zero unless `-e rbac_allow_empty=true`. Passwords never appear in
reports.

## Operator runbook

1. As pre-verification setup, seed the AAP 2.5 RPM source with `bootstrap.yml`
   (or use existing content). This is the only source-writing step; the
   verification playbooks only read source content.
2. Run `verify_smoke.yml` and curated `verify_functional.yml` against the source;
   preserve the reports.
3. Perform the migration using the approved migration process.
4. Run `verify_parity.yml` (source → target), `verify_functional.yml`, and
   `verify_rbac.yml` against the target (RBAC only when local demo users exist).
5. Complete the manual checklist items.
6. Preserve all reports as migration evidence.
7. Tear down only the disposable `Demo` objects (`teardown.yml`).

## Live acceptance status

Offline tests pass in CI. Live AAP 2.5 RPM-to-OpenShift acceptance remains
outstanding; no live AAP result is claimed here. See
[live-acceptance-prep.md](live-acceptance-prep.md) for what offline covers, what a
live run must still prove, and what this repository will never claim from mocks
alone.
