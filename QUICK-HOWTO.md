# Quick howto: deploy the AAP 2.5 demo bootstrap

A one-page, copy-pasteable path from an empty AAP 2.5 installation to a fully
seeded demo environment. For the reasoning behind each step, the full option
list, and the migration-verification playbooks, see [README.md](README.md).

## Before you start

- An Ansible Automation Platform 2.5 installation reachable over HTTPS, and a
  platform administrator credential you are willing to use temporarily.
- A Git repository the AAP controller can reach, holding a copy of this
  repository. The demo projects use it as their SCM source, so publish it
  before running the bootstrap.
- A control node with Python 3.10-3.12. Stock RHEL 8 `python3` is 3.6 and
  cannot run ansible-core 2.16; install a newer application stream
  (`sudo dnf install python3.12`, then `python3.12 -m pip install --user
  ansible-core`) or run the playbooks from an execution environment with
  `ansible-navigator`. See [README section 2a](README.md#2a-control-node-prerequisites-rhel-8).

## 1. Install the AAP-matched collections

```bash
ansible-galaxy collection install -r requirements.yml
ansible-galaxy collection list | grep -E 'ansible\.(platform|controller)'
```

Expect `ansible.platform 2.5.x` and `ansible.controller 4.6.x`. The platform
collection must be at least `2.5.20250702`; earlier 2.5 GA builds lack the
`object_ids` name-lookup parameter that the user role assignments depend on.
Do not substitute a 2.6/2.7 collection family against AAP 2.5.

## 2. Export bootstrap authentication

Use the platform gateway URL, not a controller URL.

```bash
export AAP_HOSTNAME='https://aap.example.com'
export AAP_USERNAME='admin'
export AAP_PASSWORD='REDACTED'
export AAP_VALIDATE_CERTS='true'
```

`bootstrap.yml` refuses a plain-HTTP endpoint or disabled certificate
validation before sending the admin credential. For a private CA, install the
CA trust on the control node rather than turning validation off. In a
throwaway lab only, `-e bootstrap_allow_insecure=true` overrides the check
(`-e teardown_allow_insecure=true` for the teardown playbook).

## 3. Provide the demo user password

```bash
cp config/secrets.example.yml config/secrets.yml
vi config/secrets.yml                    # set demo_user_password
ansible-vault encrypt config/secrets.yml
```

The same password applies to all six demo users. `config/secrets.yml` is
gitignored. Re-running the bootstrap does not rotate existing passwords.

To bootstrap without local users -- for example when the teams map to an
external identity provider -- skip this step entirely and add
`-e demo_create_users=false` to the run below. Team content roles are still
assigned.

## 4. Run the bootstrap

```bash
ansible-playbook bootstrap.yml \
  -e demo_scm_url='https://git.example.com/automation/aap25-demo-bootstrap.git' \
  -e demo_scm_branch='main' \
  -e @config/secrets.yml --ask-vault-pass
```

On a fresh instance, the task *Wait for gateway organizations to propagate to
the controller* can pause for up to 15 minutes. That is the periodic
gateway-to-controller resource sync, not a hang; the play continues as soon as
all three organizations are visible on the controller side.

The playbook is idempotent apart from job-history seeding. To reapply
configuration without generating new job records:

```bash
ansible-playbook bootstrap.yml \
  -e demo_scm_url='https://git.example.com/automation/aap25-demo-bootstrap.git' \
  -e @config/secrets.yml --ask-vault-pass \
  --skip-tags seed_history
```

## 5. Check the result

In the unified UI, confirm three `Demo *` organizations and teams, six
`demo-*` users, three inventories, three successfully synced projects, five
job templates, one workflow template, one enabled schedule, one notifier, one
machine credential, and a job list containing both successful runs and one
intentional failure. Then log in as `demo-alice` and confirm only Demo Linux
content is visible. The full checklist is
[README section 6](README.md#6-post-bootstrap-checks).

For a scriptable equivalent of those checks:

```bash
ansible-playbook verify_smoke.yml
```

This asserts the demo objects, project sync state, and job history, and exits
non-zero on failure. It authenticates as the admin user throughout, so it
proves availability and content but not RBAC.

## Removing the demo content

```bash
ansible-playbook teardown.yml
```

Removes every object the bootstrap created. Job history rows belonging to
deleted templates remain in the controller; that is controller behavior.

## Where to go next

- [README section 7](README.md#7-migration-verification-aap-25-rpm---aap-25-on-openshift)
  covers the three-layer migration verification (smoke, content parity,
  functional equivalence) and the operator runbook for an RPM-to-OpenShift
  migration.
- `config/demo.yml` defines every seeded object; edit it to change the demo
  content.
- [README security and lifecycle notes](README.md#security-and-lifecycle-notes)
  covers credential handling and the constraints on demo objects.
