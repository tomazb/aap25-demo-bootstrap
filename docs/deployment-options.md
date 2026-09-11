# Deployment options and post-bootstrap checks

Variations on the [README quickstart](../README.md#quickstart): running without
local users, re-running without new job history, lab-only overrides, the full
verification checklist, teardown behavior, and the optional "bad practice"
anti-pattern demo. All commands assume the host-native runtime; for an execution
environment, substitute the `aap_run` / `aap_vault` wrappers from
[runtimes-and-prerequisites.md](runtimes-and-prerequisites.md).

## Deploy without local users

To bootstrap without local users — for example when the teams map to an external
identity provider — skip the demo-password step entirely. Team content roles are
still assigned; only user creation and user role assignments are skipped.

```bash
ansible-playbook bootstrap.yml \
  -e demo_scm_url='https://git.example.com/automation/aap25-demo-bootstrap.git' \
  -e demo_scm_branch='<commit-sha-or-immutable-tag>' \
  -e demo_create_users=false
```

## Re-run without generating new job history

The playbook is idempotent apart from job-history seeding: the final
history-seeding task intentionally creates additional job runs each time. That
task is tagged `seed_history`; skip it to reapply configuration without
generating new job records.

With local users:

```bash
ansible-playbook bootstrap.yml \
  -e demo_scm_url='https://git.example.com/automation/aap25-demo-bootstrap.git' \
  -e demo_scm_branch='<commit-sha-or-immutable-tag>' \
  -e @config/secrets.yml --ask-vault-pass \
  --skip-tags seed_history
```

Without local users:

```bash
ansible-playbook bootstrap.yml \
  -e demo_scm_url='https://git.example.com/automation/aap25-demo-bootstrap.git' \
  -e demo_scm_branch='<commit-sha-or-immutable-tag>' \
  -e demo_create_users=false \
  --skip-tags seed_history
```

## Lab-only insecure override

`bootstrap.yml` and `teardown.yml` refuse a plain-HTTP endpoint or disabled
certificate validation before sending the admin credential. For a private CA,
install the CA trust on the control node (see
[runtimes-and-prerequisites.md](runtimes-and-prerequisites.md)) rather than
turning validation off.

In a throwaway lab only, override the check:

```bash
ansible-playbook bootstrap.yml \
  -e demo_scm_url='https://git.example.com/automation/aap25-demo-bootstrap.git' \
  -e demo_scm_branch='<commit-sha-or-immutable-tag>' \
  -e @config/secrets.yml --ask-vault-pass \
  -e bootstrap_allow_insecure=true

ansible-playbook teardown.yml -e teardown_allow_insecure=true
```

`verify_smoke.yml` accepts `-e smoke_allow_insecure=true` in the same spirit;
never use these against a customer or production endpoint.

## Full post-bootstrap checklist

In every mode, verify in the unified UI:

1. Access Management → Organizations: `Demo Linux`, `Demo Network`, and
   `Demo Platform`.
2. Access Management → Teams: three teams, each with roles on its organization's
   content.
3. Automation Execution → Infrastructure → Inventories: three demo inventories.
4. Automation Execution → Projects: three successful SCM project syncs.
5. Automation Execution → Templates: five demo job templates.
6. Jobs: successful runs plus one intentional failed run.
7. Automation Execution → Templates: the `Demo WF - Linux hello then report`
   workflow template.
8. Automation Execution → Schedules: `Demo Weekly Hello`, enabled, with a
   populated next run.
9. Automation Execution → Administration → Notifiers: `Demo Webhook Notifier`.
10. Automation Execution → Infrastructure → Credentials: `Demo Platform Machine
    Credential` (attached to Demo 04).

When `demo_create_users=true`, also verify:

1. Access Management → Users: `demo-alice`, `demo-bob`, `demo-carol`,
   `demo-dave`, `demo-erin`, and `demo-frank`.
2. Access Management → Teams: each team has one `Team Admin` and one
   `Team Member` user.
3. Log in as `demo-alice` (Demo Linux team admin): only the Demo Linux
   inventory, project, and templates are visible and manageable; the other two
   organizations' content is not.

For a scriptable equivalent, run **one** smoke command matching the mode the
bootstrap used (do not run both):

```bash
# bootstrap ran with local users
ansible-playbook verify_smoke.yml

# bootstrap ran with demo_create_users=false
ansible-playbook verify_smoke.yml -e demo_create_users=false
```

This asserts the demo objects, project sync state, and job history, and exits
non-zero on failure. It authenticates as the admin user throughout, so it proves
availability and content but not RBAC. To verify team-scoped visibility, see
[migration-verification.md](migration-verification.md) (Layer 4).

## Removing the demo content

```bash
# Secure bootstrap:
ansible-playbook teardown.yml

# Bootstrap used bootstrap_allow_insecure=true in a throwaway lab:
ansible-playbook teardown.yml -e teardown_allow_insecure=true
```

Removes the demo organizations and every object the bootstrap created inside
them. Two things are left behind, both controller behavior: the `demo-controlled`
label, which cannot be deleted through the controller API and is
garbage-collected once nothing references it, and job-history rows belonging to
deleted templates.

## Optional: the Default-organization anti-pattern

`badpractice.yml` deliberately seeds "Bad Demo" / `baddemo-` prefixed content
into the platform's pre-existing **Default** organization — an inventory,
project, job template, machine credential (fake password), and two users, one
with Organization Admin on Default and one with direct per-object admin grants
that bypass teams. Use it to show what "just put it in Default" sprawl looks like
next to the properly organized demo content.

```bash
# do
ansible-playbook badpractice.yml -e demo_scm_url=<url> \
  -e @config/secrets.yml --ask-vault-pass

# undo
ansible-playbook badpractice.yml -e badpractice_state=absent
```

Both directions are idempotent. The undo removes only the seeded content; the
Default organization itself is never created, modified, or deleted, and the
proper demo content from `bootstrap.yml` is never touched (nor does
`teardown.yml` remove bad-practice content — each playbook owns its own objects).
For a throwaway lab that used the insecure override, add
`-e badpractice_allow_insecure=true`.
