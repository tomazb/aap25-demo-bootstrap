# AAP 2.5 demo bootstrap

This repository populates a fresh Ansible Automation Platform 2.5 installation with:

- three gateway-managed organizations and teams;
- six local demo users (two per organization) with team-scoped RBAC, so every user manages only their own organization's content;
- three controller inventories with synthetic hosts and groups;
- three SCM projects pointing back to this repository;
- five safe job templates, including a survey and a controlled failure;
- one workflow job template chaining two of the demo templates;
- one enabled weekly schedule, one webhook notification template pointing at
  a non-routable URL, one machine credential with a clearly-fake password,
  and one label — so every object type compared by `verify_parity.yml` is
  exercised by seeded content (execution environments excepted: a custom EE
  needs a pullable image, and the default EEs already exercise that type);
- seeded successful and failed job history.

No task contacts a real managed host. Every synthetic host uses `ansible_connection: local`, and the content is limited to `debug`, `assert`, `set_stats`, and an intentional `fail` task.

## 1. Publish this repository

Push the complete directory to a Git repository that the AAP controller can reach. The controller project uses this same repository as its SCM source.

## 2. Install AAP-matched certified collections

Use the collection versions provided by your AAP 2.5 private automation hub whenever possible.

```bash
ansible-galaxy collection install -r requirements.yml
ansible-galaxy collection list | grep -E 'ansible\.(platform|controller)'
```

Expected version families are `ansible.platform 2.5.x` and `ansible.controller 4.6.x`. Do not silently install 2.6/2.7 collection families against AAP 2.5.

`requirements.yml` requires `ansible.platform >= 2.5.20250702`: earlier 2.5 GA builds lack the `object_ids` name-lookup parameter on `role_user_assignment` that the user role assignments depend on. If your private automation hub only mirrors an older 2.5 build, sync a newer one before running the bootstrap.

## 2a. Control node prerequisites (RHEL 8)

ansible-core 2.16 — the AAP 2.5 tooling line — requires Python 3.10–3.12 on
the control node. Stock RHEL 8 `python3` is 3.6, which cannot run it. Either:

- install a newer application stream and use it for ansible-core and the
  collections: `sudo dnf install python3.12` then
  `python3.12 -m pip install --user ansible-core`, or
- run the playbooks from an AAP execution environment with
  `ansible-navigator`, which needs no Python on the host beyond the runner.

## 3. Export bootstrap authentication

Use the platform gateway URL. A temporary platform administrator credential is the simplest bootstrap method. Do not commit it.

```bash
export AAP_HOSTNAME='https://aap.example.com'
export AAP_USERNAME='admin'
export AAP_PASSWORD='REDACTED'
export AAP_VALIDATE_CERTS='true'
```

`bootstrap.yml` and `teardown.yml` refuse a plain-HTTP endpoint or disabled
certificate validation before sending the admin credential; for a throwaway
lab only, override with `-e bootstrap_allow_insecure=true` /
`-e teardown_allow_insecure=true`.

The playbook feeds these values to the `ansible.controller` modules through `module_defaults`, so `CONTROLLER_*` environment variables are not needed. Most `ansible.controller` 4.6.x builds only read `CONTROLLER_*` variables, not `AAP_*`, which is why the playbook passes the values explicitly instead of relying on the environment.

For a private CA, install the CA trust on the bootstrap host instead of setting certificate validation to false.

## 4. Provide the demo user password

User passwords are never stored in this repository. Create a Vault-encrypted secrets file (the unencrypted file is gitignored):

```bash
cp config/secrets.example.yml config/secrets.yml
vi config/secrets.yml                    # set demo_user_password
ansible-vault encrypt config/secrets.yml
```

The same password is applied to all six demo users. Re-running the bootstrap does not rotate existing passwords (`update_secrets: false`); change passwords in the UI, or delete the users and re-run.

To bootstrap without local users (for example when teams map to an external IdP), skip this section and pass `-e demo_create_users=false`. Team content roles are still assigned; only user creation and user role assignments are skipped.

## 5. Run the bootstrap

```bash
ansible-playbook bootstrap.yml \
  -e demo_scm_url='https://git.example.com/automation/aap25-demo-bootstrap.git' \
  -e demo_scm_branch='main' \
  -e @config/secrets.yml --ask-vault-pass
```

On a fresh instance the task `Wait for gateway organizations to propagate to the controller` can pause for up to 15 minutes: the controller learns about gateway-created organizations through a periodic resource sync with a 15-minute default interval. This is expected; the bootstrap continues as soon as all three organizations are visible on the controller side.

Run it a second time. Configuration tasks should be idempotent; the final history-seeding task intentionally creates additional job runs each time.

To reapply configuration without creating more history:

```bash
ansible-playbook bootstrap.yml \
  -e demo_scm_url='https://git.example.com/automation/aap25-demo-bootstrap.git' \
  -e @config/secrets.yml --ask-vault-pass \
  --skip-tags seed_history
```

The history task is tagged `seed_history`; omit that tag when you want configuration convergence without generating new job records.

## 6. Post-bootstrap checks

Verify in the unified UI:

1. Access Management -> Organizations: `Demo Linux`, `Demo Network`, `Demo Platform`.
2. Access Management -> Users: `demo-alice`, `demo-bob`, `demo-carol`, `demo-dave`, `demo-erin`, `demo-frank`.
3. Access Management -> Teams: three teams, each with one `Team Admin` and one `Team Member` user, and roles on their organization's content.
4. Automation Execution -> Infrastructure -> Inventories: three demo inventories.
5. Automation Execution -> Projects: three successful SCM project syncs.
6. Automation Execution -> Templates: five demo job templates.
7. Jobs: successful runs plus one intentional failed run.
8. Automation Execution -> Templates: the `Demo WF - Linux hello then report`
   workflow template.
9. Automation Execution -> Schedules: `Demo Weekly Hello`, enabled, with a
   populated next run.
10. Automation Execution -> Administration -> Notifiers: `Demo Webhook
    Notifier`.
11. Automation Execution -> Infrastructure -> Credentials: `Demo Platform
    Machine Credential`.
12. Log in as `demo-alice` (Demo Linux team admin): only the Demo Linux inventory, project, and templates are visible and manageable; the other two organizations' content is not.

## 7. Migration verification (AAP 2.5 RPM -> AAP 2.5 on OpenShift)

Three independent, pipeline-gateable playbooks help **verify** a migration
from **AAP 2.5 on RPM/RHEL (with the automation gateway)** to a fresh
**AAP 2.5 on OpenShift**. This repository does not perform the platform or
database migration — it seeds a lab and verifies a migration performed by
another process. Source-side access is always read-only. Each playbook writes
a Markdown report to `reports/` (gitignored) and exits non-zero on failure.

All verification playbooks require an HTTPS endpoint with certificate
validation before sending credentials (install private CA trust rather than
disabling validation). Operational errors — API/transport failures,
pagination truncation, duplicate normalized keys, missing/invalid fixtures —
always fail the run, in every mode.

### Layer 1 - target smoke gate

Run `bootstrap.yml` against the OCP target, then:

```bash
ansible-playbook verify_smoke.yml     # asserts demo objects, sync and history
ansible-playbook teardown.yml         # removes all demo content afterwards
```

This proves admin authentication, API availability, resource synchronization
to the controller, SCM project sync state, execution, and job history for the
**current** demo templates (history is queried by the resolved template id, so
stale runs of a deleted/recreated template cannot satisfy the gate).

It does **not** prove RBAC: every request authenticates as the admin user.
Restricted-user authorization must be verified separately. Job history rows
of deleted demo templates remain in the controller; that is controller
behavior, not an error.

### Layer 2 - content parity

```bash
export SOURCE_AAP_HOSTNAME='https://rpm-gateway.example.com'   # source gateway
export SOURCE_AAP_USERNAME='admin'
export SOURCE_AAP_PASSWORD='REDACTED'
# target uses AAP_HOSTNAME / AAP_USERNAME / AAP_PASSWORD
ansible-playbook verify_parity.yml
```

Compares organizations, users, teams (gateway routes), and credentials
(existence), projects, inventories, hosts, job templates, workflow job
templates, schedules, notification templates, execution environments and
labels (controller routes) between the AAP 2.5 source and the AAP 2.5 OCP
target. Object types, per-side key/field paths, and comparison scope are
configured in `config/verify.yml` (`parity_types`). Org-scoped resources use
organization-qualified keys so two objects with the same name in different
organizations stay distinct; a duplicate normalized key is an operational
error. Smart and constructed inventories are excluded from host comparison.
Credential **secrets** cannot be compared through any API; a migrated
`SECRET_KEY` is proven functionally by Layer 3 instead.

`parity_fail_on` controls the exit code (the report always lists everything):

- `missing` — fail when a source object is absent on the target; field
  mismatches are reported but do not fail.
- `drift` — fail on missing objects **or** field mismatches.
- `none` — tolerate all content differences (operational errors still fail).

Pagination is bounded by `parity_max_pages`; hitting the cap with more pages
pending is treated as truncation and fails the run.

### Layer 3 - functional equivalence

Curate `functional_checks` in `config/verify.yml` (job template launches,
project syncs, notification tests), then:

```bash
ansible-playbook verify_functional.yml
```

A launched job template that uses a migrated credential is the `SECRET_KEY`
decrypt proof: with a wrong key the credential exists but the job fails at
decryption. With no checks configured the playbook writes a `RESULT: NOT_RUN`
report and exits non-zero (NOT_RUN is not a PASS); pass
`-e functional_allow_empty=true` to exit 0 for a pre-curation pipeline. The
report ends with a manual checklist (SSO/LDAP login, settings, instance/
container groups, mesh topology) for what cannot be automated responsibly.

### Operator runbook

1. Seed the AAP 2.5 RPM source with `bootstrap.yml` (or use existing content).
2. Run `verify_smoke.yml` and curated `verify_functional.yml` against the
   source; preserve the reports.
3. Perform the migration using the approved migration process.
4. Run `verify_parity.yml` (source -> target) and `verify_functional.yml`
   against the target.
5. Complete the manual checklist items.
6. Preserve all reports as migration evidence.
7. Tear down only the disposable `Demo` objects (`teardown.yml`).

### Live acceptance status

Offline tests pass in CI (unit, syntax, pagination, parity, smoke, functional).
Live AAP 2.5 RPM-to-OpenShift acceptance remains outstanding; no live AAP
result is claimed here.

## Security and lifecycle notes

- Do not insert demo records directly into PostgreSQL.
- Do not copy project content into controller container filesystems.
- Keep demo objects prefixed with `Demo` so they can be identified and removed.
- Keep real secrets out of this repository. Add real credentials only through an approved secret-management workflow.
- Demo users are local gateway accounts intended for throwaway demo environments. Their shared password comes only from the Vault-encrypted `config/secrets.yml`, which is gitignored. For production-like demos, disable local users (`-e demo_create_users=false`) and map the teams to your external identity provider groups instead.
