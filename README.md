# AAP 2.5 demo bootstrap

This repository populates a fresh Ansible Automation Platform 2.5 installation with:

- three gateway-managed organizations and teams;
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

## 3. Export bootstrap authentication

Use the platform gateway URL. A temporary platform administrator credential is the simplest bootstrap method. Do not commit it.

```bash
export AAP_HOSTNAME='https://aap.example.com'
export AAP_USERNAME='admin'
export AAP_PASSWORD='REDACTED'
export AAP_VALIDATE_CERTS='true'

export CONTROLLER_HOST="$AAP_HOSTNAME"
export CONTROLLER_USERNAME="$AAP_USERNAME"
export CONTROLLER_PASSWORD="$AAP_PASSWORD"
export CONTROLLER_VERIFY_SSL="$AAP_VALIDATE_CERTS"
```

For a private CA, install the CA trust on the bootstrap host instead of setting certificate validation to false.

## 4. Run the bootstrap

```bash
ansible-playbook bootstrap.yml \
  -e demo_scm_url='https://git.example.com/automation/aap25-demo-bootstrap.git' \
  -e demo_scm_branch='main'
```

Run it a second time. Configuration tasks should be idempotent; the final history-seeding task intentionally creates additional job runs each time.

To reapply configuration without creating more history:

```bash
ansible-playbook bootstrap.yml \
  -e demo_scm_url='https://git.example.com/automation/aap25-demo-bootstrap.git' \
  --skip-tags seed_history
```

The history task is tagged `seed_history`; omit that tag when you want configuration convergence without generating new job records.

## 5. Post-bootstrap checks

Verify in the unified UI:

1. Access Management -> Organizations: `Demo Linux`, `Demo Network`, `Demo Platform`.
2. Automation Execution -> Infrastructure -> Inventories: three demo inventories.
3. Automation Execution -> Projects: three successful SCM project syncs.
4. Automation Execution -> Templates: five demo job templates.
5. Jobs: successful runs plus one intentional failed run.

## Security and lifecycle notes

- Do not insert demo records directly into PostgreSQL.
- Do not copy project content into controller container filesystems.
- Keep demo objects prefixed with `Demo` so they can be identified and removed.
- Keep real secrets out of this repository. Add real credentials only through an approved secret-management workflow.
- Teams are created without local demo users. Map them to your external identity provider groups, or create temporary users from an Ansible Vault-encrypted input file.
