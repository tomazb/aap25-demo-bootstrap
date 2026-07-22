# AAP 2.5 demo bootstrap

This repository populates a fresh Ansible Automation Platform 2.5 installation with:

- three gateway-managed organizations and teams;
- six local demo users (two per organization) with team-scoped RBAC, so every user manages only their own organization's content;
- three controller inventories with synthetic hosts and groups;
- three SCM projects pointing back to this repository;
- five safe job templates, including a survey and a controlled failure;
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

## 3. Export bootstrap authentication

Use the platform gateway URL. A temporary platform administrator credential is the simplest bootstrap method. Do not commit it.

```bash
export AAP_HOSTNAME='https://aap.example.com'
export AAP_USERNAME='admin'
export AAP_PASSWORD='REDACTED'
export AAP_VALIDATE_CERTS='true'
```

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
8. Log in as `demo-alice` (Demo Linux team admin): only the Demo Linux inventory, project, and templates are visible and manageable; the other two organizations' content is not.

## Security and lifecycle notes

- Do not insert demo records directly into PostgreSQL.
- Do not copy project content into controller container filesystems.
- Keep demo objects prefixed with `Demo` so they can be identified and removed.
- Keep real secrets out of this repository. Add real credentials only through an approved secret-management workflow.
- Demo users are local gateway accounts intended for throwaway demo environments. Their shared password comes only from the Vault-encrypted `config/secrets.yml`, which is gitignored. For production-like demos, disable local users (`-e demo_create_users=false`) and map the teams to your external identity provider groups instead.
