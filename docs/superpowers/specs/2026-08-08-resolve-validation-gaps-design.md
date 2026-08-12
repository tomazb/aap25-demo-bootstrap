# Resolve validation gaps — design

Date: 2026-08-08
Status: approved (user directive: "assess, validate and resolve the gaps and open a PR when done")

## Background

A deep validation of this repository (offline suite fully green: 32 pytest
units + 7 offline integration scripts) found five concrete gaps between what
the repository claims and what it enforces. This spec resolves them.

## Gaps and resolutions

### 1. Transport enforcement in bootstrap.yml and teardown.yml

**Gap.** Every `verify_*` playbook asserts HTTPS + certificate validation
before sending credentials. `bootstrap.yml` and `teardown.yml` do not — they
send the platform **admin** credential over whatever `AAP_HOSTNAME` says,
including plain HTTP.

**Resolution.** Add the same pre-task assert to both playbooks, with the same
lab-only escape hatch pattern (`bootstrap_allow_insecure` /
`teardown_allow_insecure`, default `false`). Assert:

- `AAP_HOSTNAME` matches `^https://`
- `AAP_VALIDATE_CERTS` resolves true

No behavior change for correctly-configured runs.

### 2. Assert the expect_failure seed outcome

**Gap.** `bootstrap.yml` seeds one intentional failure with
`ignore_errors: "{{ item.expect_failure | default(false) }}"`. This swallows
*both* outcomes: if the "controlled failure" unexpectedly succeeds, bootstrap
stays green and only the later smoke gate catches it.

**Resolution.** Register the seed-job results. After the loop, assert that
every item with `expect_failure: true` actually failed. Items without
`expect_failure` keep the existing behavior (module failure fails the task).

### 3. Seed the unexercised parity types

**Gap.** `parity_types` compares 13 object types; the seeder creates only 7.
Credentials, workflow job templates, schedules, notification templates,
execution environments and labels pass trivially empty in a seed → migrate →
verify lab, so the parity layer is never exercised on them.

**Resolution.** Extend `config/demo.yml` + `bootstrap.yml` with, all
`Demo`-prefixed, config-driven:

- `demo_credentials`: one Machine credential (`Demo Platform` org) with a
  dummy username and a harmless literal password (clearly not a secret;
  parity compares existence + credential type only).
- `demo_labels`: one label (`Demo Platform` org) attached to
  `Demo 05 - Controlled outcome`.
- `demo_notification_templates`: one webhook notification template
  (`Demo Linux` org) pointing at a safe non-routable URL
  (`https://demo-notifications.invalid/hook`). Existence + type is what
  parity checks; it is not test-fired by default.
- `demo_schedules`: one enabled weekly-RRULE schedule on
  `Demo 01 - Linux hello` (safe: local connection, seconds long). Enabled so
  the controller populates `next_run` and the functional enabled-schedule
  check gets real data.
- `demo_workflow_job_templates`: one workflow (`Demo Platform` org) with two
  nodes chaining Demo 01 → Demo 02.
- **Execution environments: deliberately NOT seeded.** A custom EE requires a
  pullable image; a broken image reference is worse demo content than none.
  Default EEs exist on both sides of a migration and exercise the parity
  type. Documented in config comments and README.

**Ripple effects (in scope):**

- `teardown.yml`: remove new objects in reverse dependency order (schedule →
  workflow JT → notification template → credential). Labels: the controller
  garbage-collects unreferenced labels and the `ansible.controller.label`
  module has no `state: absent`; documented in teardown comments (verify
  during implementation).
- `verify_smoke.yml`: existence checks for the new workflow JT, notification
  template, schedule and credential (org-scoped, same failure-collection
  pattern as existing checks).
- `tests/mock_aap_server.py` + offline suites: serve the new endpoints so
  smoke stays green offline (TDD: extend the mock/tests first, watch fail,
  implement).
- README object counts and post-bootstrap checklist; AGENTS.md layout notes.

### 4. Document RHEL8 control-node prerequisites

**Gap.** ansible-core 2.16 (the AAP 2.5 tooling line) requires Python
3.10–3.12 on the control node; stock RHEL8 default python3 is 3.6. Nothing in
the README says so.

**Resolution.** Short README section: use the python3.11 or python3.12
RHEL8 application stream (`dnf install python3.12`), or run from an
execution environment via `ansible-navigator`. No code change.

### 5. ansible-lint in CI

**Gap.** CI runs syntax + offline behavioural suites but no lint.

**Resolution.** Add a pinned `ansible-lint` step to
`.github/workflows/ci.yml`, offline-compatible. Fix any findings on existing
code; add a minimal `.ansible-lint` config only if a rule conflicts with the
repository's established patterns (each skip justified inline).

## Out of scope (documented for follow-up)

- Restricted-user RBAC extension to inventories/projects.
- Parity ignore/allowlist patterns for system users and default EEs.
- Org-qualified host and schedule parity keys.
- Live AAP acceptance run (still outstanding; this PR does not claim it).

## Testing

- Extend offline tests first (mock endpoints, expected assertions), then
  implement until green.
- Full gate before PR: `python3 -m pytest tests/`, `bash -n tests/*.sh`, all
  seven `tests/*_offline.sh` suites, plus the new ansible-lint step run
  locally.
