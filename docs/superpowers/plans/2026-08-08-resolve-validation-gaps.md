# Resolve Validation Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five validated gaps: transport asserts in bootstrap/teardown, expect_failure assertion, seed the six unexercised parity types, RHEL8 prereq docs, ansible-lint in CI.

**Architecture:** All demo data stays config-driven in `config/demo.yml`; `bootstrap.yml` gains new loop tasks inside the existing `module_defaults` group; `teardown.yml` removes in reverse order; `verify_smoke.yml` gains existence checks following the existing failure-collection pattern; `tests/mock_aap_server.py` answers for the new types from the same demo.yml load.

**Tech Stack:** Ansible (ansible-core 2.16 line), `ansible.platform` 2.5.x / `ansible.controller` 4.6.x, Python stdlib mock server, bash offline suites, GitHub Actions.

## Global Constraints

- AAP 2.5 only. Never add AAP 2.6/2.7 API paths or collection families.
- Every demo object name is prefixed `Demo`.
- No real secrets; the demo credential password is a clearly-fake literal.
- Verification/bootstrap playbooks must not send credentials over plain HTTP unless a lab-only `*_allow_insecure` var is explicitly true.
- Offline tests stay deterministic: no network, no Galaxy, no real AAP.
- Do not add Co-Authored-By lines to commit messages (AGENTS.md rule).

---

### Task 1: Transport asserts in bootstrap.yml and teardown.yml

**Files:**
- Modify: `bootstrap.yml` (pre_tasks, vars)
- Modify: `teardown.yml` (pre_tasks, vars)

**Interfaces:**
- Produces: `bootstrap_allow_insecure` / `teardown_allow_insecure` play vars (default false), documented in README by Task 5.

- [ ] **Step 1: Add to `bootstrap.yml` vars** `bootstrap_allow_insecure: false`, and to pre_tasks (after the existing input assert):

```yaml
    - name: Require secure transport before sending admin credentials
      ansible.builtin.assert:
        that:
          - aap_bootstrap_hostname is match('^https://')
          - aap_bootstrap_validate_certs | bool
        fail_msg: >-
          Export an HTTPS AAP_HOSTNAME and keep certificate validation enabled
          (install private CA trust rather than disabling it). Admin
          credentials must not be sent over HTTP or without certificate
          validation. Set -e bootstrap_allow_insecure=true only for a
          throwaway lab.
      when: not (bootstrap_allow_insecure | bool)
```

- [ ] **Step 2: Same for `teardown.yml`** with `teardown_allow_insecure` and the same assert against its `aap_bootstrap_hostname`/`aap_bootstrap_validate_certs` vars.
- [ ] **Step 3: Run** `tests/syntax_check.sh` — expect PASS.
- [ ] **Step 4: Commit** `git commit -m "Require HTTPS for bootstrap and teardown admin credentials"`

### Task 2: Assert the expect_failure seed outcome

**Files:**
- Modify: `bootstrap.yml` (the `Seed controller job history` task)

- [ ] **Step 1:** Add `register: demo_seed_results` to the seed task (keep `ignore_errors` as is).
- [ ] **Step 2:** Append after it:

```yaml
    - name: Assert intentional-failure seed jobs actually failed
      ansible.builtin.assert:
        that:
          - item is failed
        fail_msg: >-
          Seed job '{{ item.item.template }}' was expected to fail but
          succeeded; the controlled-outcome demo content is wrong.
      loop: "{{ demo_seed_results.results | selectattr('item.expect_failure', 'defined')
                | selectattr('item.expect_failure') | list }}"
      loop_control:
        label: "{{ item.item.template }}"
      tags:
        - seed_history
```

- [ ] **Step 3: Run** `tests/syntax_check.sh` — PASS. **Commit** `git commit -m "Assert intentional-failure seed job actually fails"`

### Task 3: Seed the unexercised parity types

**Files:**
- Modify: `config/demo.yml` (new lists: `demo_credentials`, `demo_labels`, `demo_notification_templates`, `demo_workflow_job_templates`, `demo_schedules`; EE non-seeding comment)
- Modify: `bootstrap.yml` (new tasks after job-template creation, before RBAC grants)
- Modify: `teardown.yml` (reverse-order removals at the top)

**Interfaces:**
- Produces: the five demo.yml list names above — consumed by Task 4's smoke checks and mock server (which loads demo.yml).

- [ ] **Step 1: demo.yml additions** (exact content):

```yaml
# Additional object types so every enabled parity type in config/verify.yml is
# exercised by seeded content. Execution environments are deliberately NOT
# seeded: a custom EE needs a pullable image, and a broken image reference is
# worse demo content than none. Default EEs exist on both sides of a
# migration and exercise that parity type.
demo_credentials:
  - name: Demo Platform Machine Credential
    organization: Demo Platform
    credential_type: Machine
    description: Synthetic machine credential; the password is a fake literal
    inputs:
      username: demo-service
      password: demo-not-a-real-secret

demo_labels:
  - name: demo-controlled
    organization: Demo Platform

demo_notification_templates:
  - name: Demo Webhook Notifier
    organization: Demo Linux
    notification_type: webhook
    description: Safe webhook notifier; target URL is non-routable by design
    notification_configuration:
      url: https://demo-notifications.invalid/hook
      http_method: POST
      headers: {}
      disable_ssl_verification: false
      username: ""
      password: ""

demo_workflow_job_templates:
  - name: Demo WF - Linux hello then report
    organization: Demo Platform
    description: Chains the hello demo into the inventory report demo
    nodes:
      - identifier: hello
        unified_job_template: Demo 01 - Linux hello
        success_nodes: [report]
      - identifier: report
        unified_job_template: Demo 02 - Linux inventory report
        success_nodes: []

demo_schedules:
  - name: Demo Weekly Hello
    unified_job_template: Demo 01 - Linux hello
    description: Weekly recurring safe hello run
    rrule: "DTSTART;TZID=UTC:20260803T060000 RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO"
    enabled: true
```

- [ ] **Step 2: bootstrap.yml tasks** (after `Create demo job templates`, before RBAC grants):

```yaml
    - name: Create demo credentials
      ansible.controller.credential:
        name: "{{ item.name }}"
        organization: "{{ item.organization }}"
        credential_type: "{{ item.credential_type }}"
        description: "{{ item.description }}"
        inputs: "{{ item.inputs }}"
        update_secrets: false
        state: present
      loop: "{{ demo_credentials }}"
      loop_control:
        label: "{{ item.organization }} / {{ item.name }}"

    - name: Create demo labels
      ansible.controller.label:
        name: "{{ item.name }}"
        organization: "{{ item.organization }}"
      loop: "{{ demo_labels }}"
      loop_control:
        label: "{{ item.organization }} / {{ item.name }}"

    - name: Create demo notification templates
      ansible.controller.notification_template:
        name: "{{ item.name }}"
        organization: "{{ item.organization }}"
        description: "{{ item.description }}"
        notification_type: "{{ item.notification_type }}"
        notification_configuration: "{{ item.notification_configuration }}"
        state: present
      loop: "{{ demo_notification_templates }}"
      loop_control:
        label: "{{ item.organization }} / {{ item.name }}"

    - name: Create demo workflow job templates
      ansible.controller.workflow_job_template:
        name: "{{ item.name }}"
        organization: "{{ item.organization }}"
        description: "{{ item.description }}"
        state: present
      loop: "{{ demo_workflow_job_templates }}"
      loop_control:
        label: "{{ item.organization }} / {{ item.name }}"

    - name: Create demo workflow nodes
      ansible.controller.workflow_job_template_node:
        workflow_job_template: "{{ item.0.name }}"
        organization: "{{ item.0.organization }}"
        identifier: "{{ item.1.identifier }}"
        unified_job_template: "{{ item.1.unified_job_template }}"
        state: present
      loop: "{{ demo_workflow_job_templates | subelements('nodes') }}"
      loop_control:
        label: "{{ item.0.name }} / {{ item.1.identifier }}"

    - name: Link demo workflow node success paths
      ansible.controller.workflow_job_template_node:
        workflow_job_template: "{{ item.0.name }}"
        organization: "{{ item.0.organization }}"
        identifier: "{{ item.1.identifier }}"
        success_nodes: "{{ item.1.success_nodes }}"
        state: present
      loop: "{{ demo_workflow_job_templates | subelements('nodes') }}"
      loop_control:
        label: "{{ item.0.name }} / {{ item.1.identifier }}"
      when: item.1.success_nodes | length > 0

    - name: Create demo schedules
      ansible.controller.schedule:
        name: "{{ item.name }}"
        unified_job_template: "{{ item.unified_job_template }}"
        description: "{{ item.description }}"
        rrule: "{{ item.rrule }}"
        enabled: "{{ item.enabled }}"
        state: present
      loop: "{{ demo_schedules }}"
      loop_control:
        label: "{{ item.name }}"

    - name: Attach demo labels to the controlled-outcome template
      ansible.controller.job_template:
        name: Demo 05 - Controlled outcome
        organization: Demo Platform
        labels: "{{ demo_labels | map(attribute='name') | list }}"
        state: present
```

  Note: two-pass node creation (create all nodes, then link success paths)
  avoids forward references to not-yet-created node identifiers.

- [ ] **Step 3: teardown.yml removals** at the TOP of tasks (before job template removal): schedules (`ansible.controller.schedule` state absent, name + unified_job_template), workflow JTs (`ansible.controller.workflow_job_template` state absent, name + organization), notification templates (state absent, name + organization), credentials (state absent, name + organization + credential_type). Comment that labels cannot be deleted through the API; the controller garbage-collects unreferenced labels.
- [ ] **Step 4: Run** `tests/syntax_check.sh` (auto-stubs the new module names via grep) — PASS.
- [ ] **Step 5: Commit** `git commit -m "Seed credentials, labels, notifier, workflow and schedule demo content"`

### Task 4: Smoke checks + mock server for the new types (TDD)

**Files:**
- Modify: `tests/mock_aap_server.py` (new endpoint handling + `missing_workflow` scenario)
- Modify: `tests/smoke_offline.sh` (new scenario assertion)
- Modify: `verify_smoke.yml` (four new check blocks)

**Interfaces:**
- Consumes: Task 3's demo.yml list names.

- [ ] **Step 1 (RED): mock server additions.** After the existing DEMO loads:

```python
WF = {w["name"]: w["organization"]
      for w in DEMO.get("demo_workflow_job_templates", [])}
NT = {t["name"]: t["organization"]
      for t in DEMO.get("demo_notification_templates", [])}
CRED = {c["name"]: c["organization"] for c in DEMO.get("demo_credentials", [])}
SCHED = {s["name"]: s["unified_job_template"]
         for s in DEMO.get("demo_schedules", [])}
```

  In `do_GET`: `workflow_job_templates/` returns an org-scoped row when
  `name in WF` (empty list when `SCENARIO == "missing_workflow"`), else
  `_list([])`. `credentials/` likewise from CRED. In the existing
  `notification_templates/` branch: when `name in NT`, return the demo row
  BEFORE the env-driven customer fallback. In the existing `schedules/`
  branch: when `name in SCHED`, return a row
  `{"name": name, "enabled": True, "next_run": "2027-01-04T06:00:00Z",
  "summary_fields": {"unified_job_template": {"name": SCHED[name]}}}`,
  keeping the empty default otherwise.
- [ ] **Step 2 (RED): smoke_offline.sh scenario** after the stale_history block:

```bash
# a missing workflow template must fail the smoke gate
run_smoke missing_workflow
[ "$RC" -ne 0 ] || fail "missing_workflow should fail"
grep -q 'workflow job template missing in org' "$REPORT" \
  || fail "missing workflow not reported"
```

- [ ] **Step 3: Run** `tests/smoke_offline.sh` — expect FAIL (verify_smoke.yml has no workflow check yet, happy path also unaffected → the new grep fails).
- [ ] **Step 4 (GREEN): verify_smoke.yml checks** — four new check/record pairs following the exact inventory-check pattern (uri lookup with `failed_when: false`, org-scoped selectattr, failure strings): workflow JTs (`workflow job template missing in org` / `request failed` / `duplicate`), notification templates (`notification template missing in org`), credentials (`credential missing in org`), schedules (lookup by `name`, match on `summary_fields.unified_job_template.name == item.unified_job_template`, failure `schedule missing: <name>`, plus `schedule disabled: <name>` when `enabled` is false and `schedule has no next_run: <name>` when `next_run` is none).
- [ ] **Step 5: Run** `tests/smoke_offline.sh` — PASS. Also run `tests/customer_functional_offline.sh` and `tests/rbac_offline.sh` (both use the same mock server) — PASS.
- [ ] **Step 6: Commit** `git commit -m "Smoke-verify seeded workflow, notifier, credential and schedule"`

### Task 5: README + AGENTS.md documentation

**Files:**
- Modify: `README.md` (intro list, new "Control node prerequisites (RHEL 8)" section after section 2, post-bootstrap checklist, security notes)
- Modify: `AGENTS.md` (Layout + Conventions entries for the new demo lists)

- [ ] **Step 1: README intro** — extend the bullet list: workflow template, weekly schedule, webhook notification template, machine credential (fake secret), label; EE non-seeding rationale sentence.
- [ ] **Step 2: RHEL8 section** (exact content): ansible-core 2.16 requires Python 3.10–3.12 on the control node; stock RHEL 8 `python3` is 3.6. Install the `python3.12` (or `python3.11`) application stream (`sudo dnf install python3.12`) and install ansible-core + collections under it, or run from an AAP execution environment via `ansible-navigator`. Bootstrap/teardown now refuse plain-HTTP endpoints unless `-e bootstrap_allow_insecure=true` / `-e teardown_allow_insecure=true` (lab only).
- [ ] **Step 3: Post-bootstrap checklist** — add: workflow template visible under Templates; schedule with a populated next run; notification template; credential.
- [ ] **Step 4: AGENTS.md** — document the new demo.yml lists, the two-pass workflow-node creation, the label-teardown caveat, and the transport asserts.
- [ ] **Step 5: Commit** `git commit -m "Document RHEL8 control-node prereqs and new demo content"`

### Task 6: ansible-lint in CI

**Files:**
- Modify: `.github/workflows/ci.yml` (install + step)
- Create (only if needed): `.ansible-lint`

- [ ] **Step 1:** Add `"ansible-lint==24.12.2"` to the pip install line and a step after "Offline playbook syntax check":

```yaml
      - name: Ansible lint
        run: ansible-lint --offline *.yml tasks/ content/
```

- [ ] **Step 2:** Run the same command locally (venv with CI-pinned versions if the system ansible-lint differs). Fix findings on existing code; only add `.ansible-lint` skips where a rule conflicts with an established repo pattern, each with an inline justification comment.
- [ ] **Step 3:** Re-run full local gate: `python3 -m pytest tests/`, `bash -n tests/*.sh`, all seven `tests/*_offline.sh`. All PASS.
- [ ] **Step 4: Commit** `git commit -m "Add ansible-lint to CI"`

### Task 7: Final gate + PR

- [ ] **Step 1:** Full suite once more from clean: pytest + all seven offline scripts.
- [ ] **Step 2:** Push branch, open draft PR (no live-AAP claims; body lists the five gaps, evidence, and the explicit out-of-scope follow-ups).
