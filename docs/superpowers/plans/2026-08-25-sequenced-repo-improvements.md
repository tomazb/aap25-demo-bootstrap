# Sequenced Repo Improvements (A→B→C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make existing capabilities discoverable (A), deepen the safe three-org demo narrative (B), then complete the verification operator story with Layer 4 RBAC and conservative parity policy (C).

**Architecture:** Three sequential phases land as separate commits (and ideally separate PRs). Phase A is documentation and CI hygiene only. Phase B adds two safe content playbooks, rewires Demo 03/04, attaches the demo machine credential to Demo 04, and updates smoke/docs. Phase C documents Layer 4, adds a lab RBAC example overlay, records parity-expansion policy, and adds a live-acceptance prep checklist without claiming live results.

**Tech Stack:** Markdown docs, Ansible Core 2.16.x playbooks/YAML config, existing offline mock/smoke harness, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-25-sequenced-repo-improvements-design.md`

## Global Constraints

- AAP 2.5 only; do not add AAP 2.6 APIs, collections, or documentation.
- `ansible.platform` stays `2.5.x` (`>=2.5.20250702`); `ansible.controller` stays `4.6.x` (`>=4.6.20,<4.7.0` for export/import).
- No default contact with real managed hosts; SSH canary remains opt-in + exact allowlist.
- No custom execution-environment seeding.
- Never compare or print credential secrets; never weaken HTTPS / certificate validation defaults.
- Offline CI stays fully offline (no Galaxy, Hub, or live AAP in CI).
- Keep `Demo` / `baddemo-` prefixes and org-scoping; Default organization only via `badpractice.yml`.
- Do not add Co-Authored-By lines; keep `AGENTS.md` current when layout or operator-facing conventions change.
- Implement phases in order: finish A before B, finish B before C.

## File map

| File | Phase | Role |
|---|---|---|
| `README.md` | A, B, C | Operator entry: map, architecture, Layers 1–4, object transfer, content counts, live-acceptance prep |
| `QUICK-HOWTO.md` | A, B | One-page path + “Where to go next” links; content checklist counts |
| `.github/workflows/ci.yml` | A | Push branch filter hygiene |
| `AGENTS.md` | A/B/C as needed | Layout / convention sync |
| `content/playbooks/network_discovery.yml` | B | New Network narrative |
| `content/playbooks/platform_change_window.yml` | B | New Platform narrative (Demo 04) |
| `content/playbooks/surveyed_change.yml` | B | Keep on disk; no longer referenced by `demo.yml` |
| `config/demo.yml` | B | Playbook paths, credential list on Demo 04 |
| `bootstrap.yml` | B | Credentials before JTs; `credentials:` on JT module |
| `verify_smoke.yml` | B | Only if assertions depend on playbook path (usually none) |
| `tests/smoke_offline.sh` / `tests/mock_aap_server.py` | B | Only if template names/counts change (they should not) |
| `config/verify.rbac.example.yml` | C | Lab-ready `rbac_users` overlay |
| `config/verify.yml` | C | Parity expansion policy comment |
| `config/verify.customer.example.yml` | C | Pointer to RBAC example |
| `docs/live-acceptance-prep.md` | C | Live acceptance prep checklist |
| `verify_rbac.yml` | C | NOT_RUN message mentions new example path |

---

# Phase A — Docs discoverability

## Task 1: README map, architecture, Layer 4 stub, object transfer

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: existing sections 1–7 and security notes; `docs/controller-object-transfer.md`; `verify_rbac.yml` behavior.
- Produces: discoverable entry points for all playbooks named in `AGENTS.md` layout.

- [ ] **Step 1: Insert a “What’s in this repo” block immediately after the opening bullet list (before the QUICK-HOWTO pointer).**

Use this content (adjust wording slightly only if it would duplicate an adjacent sentence):

```markdown
## What’s in this repo

| Path | Purpose |
|---|---|
| `bootstrap.yml` / `teardown.yml` | Seed and remove disposable `Demo` content |
| `verify_smoke.yml` | Layer 1 — admin smoke gate on one AAP |
| `verify_parity.yml` | Layer 2 — source→target content parity |
| `verify_functional.yml` | Layer 3 — curated functional checks |
| `verify_rbac.yml` | Layer 4 — restricted-user visibility (not covered by smoke) |
| `badpractice.yml` | Optional Default-organization anti-pattern demo |
| `export.yml` / `import.yml` | Supplemental controller object transfer (not a DB migration) |
| `docs/controller-object-transfer.md` | Operator procedure and safety boundary for export/import |
| `config/demo.yml` | All seeded demo objects |
| `config/verify.yml` | Parity types and functional/RBAC defaults |
```

- [ ] **Step 2: Insert an architecture subsection after the new map (or after the safety paragraph above section 1).**

Add heading `## Architecture (gateway → controller → verify)`, then a mermaid diagram with this graph definition (single fence in README — do not nest fences):

```text
flowchart LR
  GW[Platform gateway orgs teams users RBAC]
  WAIT[Wait for org propagation]
  CTL[Controller inventories projects templates workflows schedules]
  SEED[Seed job history]
  V1[verify_smoke admin]
  V4[verify_rbac as demo user]
  V2[verify_parity source to target]
  GW --> WAIT --> CTL --> SEED
  SEED --> V1
  SEED --> V4
  CTL --> V2
```

Then these bullets:

- Gateway-managed identity/access objects are created first; controller objects wait until organizations are visible on `/api/controller/v2/organizations/`.
- Admin smoke proves availability and seeded content; it does **not** prove RBAC.
- Restricted-user RBAC authenticates **as** each configured demo user.
- Parity compares a read-only source gateway/controller to a target.

- [ ] **Step 3: In section 7, after Layer 3 and before “### Operator runbook”, add Layer 4.**

````markdown
### Layer 4 - restricted-user RBAC

`verify_smoke.yml` authenticates as the admin user and therefore does **not**
prove team-scoped visibility. After bootstrap with local users, run:

```bash
export RBAC_DEMO_PASSWORD='…'   # same value as demo_user_password; never commit
aap_run verify_rbac.yml -e @config/verify.rbac.example.yml
```

Or pass Vault: `aap_run verify_rbac.yml -e @config/verify.rbac.example.yml -e @config/secrets.yml --ask-vault-pass`.

Each `rbac_users` entry must list `expected_job_templates` (positive: visible
exactly once in the user's organization) and `forbidden_organizations`
(negative: no templates from those orgs). Empty `rbac_users` writes
`RESULT: NOT_RUN` and exits non-zero unless `-e rbac_allow_empty=true`.
Passwords never appear in reports. See `config/verify.rbac.example.yml`
(Phase C adds this file; until then point at the `rbac_users` block in
`config/verify.customer.example.yml`).
````

**Phase A interim:** In Task 1, point Layer 4 at `config/verify.customer.example.yml` only. Task 7 (Phase C) switches the README link to `config/verify.rbac.example.yml` when that file exists. Do **not** leave a broken link in the merged Phase A README.

Use this Phase A Layer 4 command block instead:

```bash
export RBAC_DEMO_PASSWORD='…'
aap_run verify_rbac.yml -e @config/verify.customer.example.yml
```

And say: “Use the `rbac_users` block in `config/verify.customer.example.yml` (copy to a gitignored overlay if you add real names). Phase C adds a dedicated lab RBAC example.”

- [ ] **Step 4: Add a short supplemental object-transfer section after section 7’s live acceptance status (or as section 8 before Security).**

```markdown
## 8. Supplemental controller object transfer

`export.yml` and `import.yml` capture and recreate Automation Controller
objects supported by the installed AAP 2.5 `ansible.controller` collection.
They are a supplemental configuration-transfer artifact. They do **not**
replace the supported component database and secrets migration.

- Procedure and safety boundary: [docs/controller-object-transfer.md](docs/controller-object-transfer.md)
- Export writes a mode-`0600` assets YAML plus a SHA-256 sidecar under a mode-`0700` directory.
- Import requires `-e import_confirm=true`, matching checksum, and a `4.6.x` controller behind the Platform Gateway root in `AAP_HOSTNAME`.
```

- [ ] **Step 5: Update the operator runbook list to include Layer 4.**

Change steps so verification includes RBAC on the target, for example:

```markdown
4. Run `verify_parity.yml` (source -> target), `verify_functional.yml`, and
   `verify_rbac.yml` against the target (RBAC only when local demo users exist).
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: surface RBAC, object transfer, and architecture in README

Make Layer 4 and supplemental export/import discoverable from the operator
entry point instead of only AGENTS.md.
EOF
)"
```

## Task 2: QUICK-HOWTO links and CI branch hygiene

**Files:**
- Modify: `QUICK-HOWTO.md` (Where to go next)
- Modify: `.github/workflows/ci.yml` (push branches)
- Modify: `AGENTS.md` only if the layout bullet list should mention the README map (optional one-line; skip if redundant)

**Interfaces:**
- Consumes: Task 1 README anchors for section 7 Layer 4 and section 8.
- Produces: one-page path that points at RBAC and object transfer without pasting full procedures.

- [ ] **Step 1: Replace the “Where to go next” list with:**

```markdown
## Where to go next

- [README section 7](README.md#7-migration-verification-aap-25-rpm---aap-25-on-openshift)
  covers migration verification (smoke, parity, functional, **RBAC**) and the
  operator runbook for an RPM-to-OpenShift migration.
- [README section 8](README.md#8-supplemental-controller-object-transfer) and
  [docs/controller-object-transfer.md](docs/controller-object-transfer.md)
  cover supplemental controller export/import (not a database migration).
- `config/demo.yml` defines every seeded object; edit it to change the demo
  content.
- [README security and lifecycle notes](README.md#security-and-lifecycle-notes)
  covers credential handling and the constraints on demo objects.
```

Verify the README heading anchors match GitHub’s slug rules after Task 1 (adjust links if the rendered anchor differs).

- [ ] **Step 2: In `.github/workflows/ci.yml`, set push branches to main only:**

```yaml
on:
  push:
    branches: [main]
  pull_request:
```

Keep `pull_request:` without branch filter so PRs from feature branches still run CI.

- [ ] **Step 3: Run a docs sanity check (no playbook changes expected).**

```bash
rg -n 'verify_rbac|object transfer|controller-object-transfer|Layer 4' README.md QUICK-HOWTO.md
rg -n 'worktree-migration-verification|customer-shaped-migration-lab' .github/workflows/ci.yml
```

Expected: README/QUICK-HOWTO hit RBAC and object transfer; CI file has **no** matches for the stale branch names.

- [ ] **Step 4: Commit**

```bash
git add QUICK-HOWTO.md .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
docs: link RBAC and object transfer from QUICK-HOWTO

Drop stale CI push branch filters so only main triggers push workflows.
EOF
)"
```

**Phase A gate:** Do not start Phase B until Tasks 1–2 are committed and the README has no broken links to files that do not exist yet.

---

# Phase B — Richer safe demo content

## Task 3: Network discovery playbook + Demo 03 wiring

**Files:**
- Create: `content/playbooks/network_discovery.yml`
- Modify: `config/demo.yml` (Demo 03 `playbook` and `description`)
- Test: `tests/syntax_check.sh` (covers `content/`); ansible-lint `content/`

**Interfaces:**
- Consumes: host/group vars already seeded (`demo_role`, `demo_site`, `network_os_family`, `ansible_connection`).
- Produces: Demo 03 runs a Network-specific playbook path.

- [ ] **Step 1: Create `content/playbooks/network_discovery.yml` with this exact playbook:**

```yaml
---
- name: Simulate network discovery without contacting devices
  hosts: all
  gather_facts: false
  tasks:
    - name: Require local connection for synthetic network hosts
      ansible.builtin.assert:
        that:
          - (ansible_connection | default('')) == 'local'
        fail_msg: >-
          Demo network hosts must use ansible_connection=local; refusing to
          continue against a remote connection.

    - name: Emit simulated discovery facts
      ansible.builtin.debug:
        msg:
          host: "{{ inventory_hostname }}"
          role: "{{ demo_role | default('unspecified') }}"
          site: "{{ demo_site | default('unspecified') }}"
          network_os_family: "{{ network_os_family | default('unspecified') }}"
          groups: "{{ group_names | sort }}"
          contacted_real_device: false

    - name: Publish aggregate discovery statistics
      ansible.builtin.set_stats:
        data:
          demo_discovery_id: "{{ report_id | default('DEMO-NET-DISCOVERY') }}"
          demo_environment: "{{ demo_environment | default('lab') }}"
        aggregate: true
        per_host: false
```

- [ ] **Step 2: In `config/demo.yml`, change Demo 03 to:**

```yaml
  - name: Demo 03 - Network discovery simulation
    organization: Demo Network
    inventory: Demo Network Inventory
    project: Demo Network Content
    playbook: content/playbooks/network_discovery.yml
    description: Simulates network discovery without contacting network equipment
    survey: false
```

- [ ] **Step 3: Syntax-check content playbooks.**

```bash
ansible-playbook --syntax-check content/playbooks/network_discovery.yml
bash tests/syntax_check.sh
```

Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add content/playbooks/network_discovery.yml config/demo.yml
git commit -m "$(cat <<'EOF'
feat: add Network discovery demo playbook

Point Demo 03 at a Network-specific local-only playbook instead of reusing
the Linux inventory report.
EOF
)"
```

## Task 4: Platform change-window playbook + Demo 04 wiring + credential attach

**Files:**
- Create: `content/playbooks/platform_change_window.yml`
- Modify: `config/demo.yml` (Demo 04 playbook path, description, `credentials` list)
- Modify: `bootstrap.yml` (reorder credentials before job templates; pass `credentials`)
- Keep: `content/playbooks/surveyed_change.yml` (unchanged file; no longer referenced)
- Modify: `README.md` / `QUICK-HOWTO.md` / `AGENTS.md` only for wording if Demo 04 description changes (still five templates)

**Interfaces:**
- Consumes: existing survey fields (`change_ticket`, `change_summary`, `requested_environment`); credential name `Demo Platform Machine Credential`.
- Produces: Demo 04 uses the new playbook; JT associates the demo machine credential; credentials exist before JT create/update.

- [ ] **Step 1: Create `content/playbooks/platform_change_window.yml`:**

```yaml
---
- name: Demonstrate a synthetic platform change window
  hosts: all
  gather_facts: false
  tasks:
    - name: Validate required change-window survey data
      ansible.builtin.assert:
        that:
          - change_ticket | length > 0
          - change_summary | length > 0
          - requested_environment in ['development', 'test', 'production']
        fail_msg: Required survey values are missing or invalid

    - name: Require local connection for synthetic platform hosts
      ansible.builtin.assert:
        that:
          - (ansible_connection | default('')) == 'local'
        fail_msg: >-
          Demo platform hosts must use ansible_connection=local; refusing to
          continue against a remote connection.

    - name: Display the synthetic change window
      ansible.builtin.debug:
        msg:
          host: "{{ inventory_hostname }}"
          change_ticket: "{{ change_ticket }}"
          change_summary: "{{ change_summary }}"
          requested_environment: "{{ requested_environment }}"
          change_window: "{{ change_window | default('lab-maintenance') }}"
          changed_real_systems: false
```

- [ ] **Step 2: Update Demo 04 in `config/demo.yml` to:**

```yaml
  - name: Demo 04 - Surveyed platform change
    organization: Demo Platform
    inventory: Demo Platform Inventory
    project: Demo Platform Content
    playbook: content/playbooks/platform_change_window.yml
    description: Demonstrates a required survey, change-window metadata, and an attached machine credential
    survey: true
    credentials:
      - Demo Platform Machine Credential
```

Leave `demo_credentials` and `demo_seed_jobs` for Demo 04 unchanged (same extra_vars).

- [ ] **Step 3: In `bootstrap.yml`, move the entire “Create demo credentials” task so it runs immediately before “Create demo job templates”.**

Current order creates JTs then credentials. New order: … projects → **credentials** → **job templates** → labels → …

- [ ] **Step 4: Add credentials to the job_template task:**

```yaml
    - name: Create demo job templates
      ansible.controller.job_template:
        name: "{{ item.name }}"
        organization: "{{ item.organization }}"
        description: "{{ item.description }}"
        job_type: run
        inventory: "{{ item.inventory }}"
        project: "{{ item.project }}"
        playbook: "{{ item.playbook }}"
        credentials: "{{ item.credentials | default(omit) }}"
        ask_variables_on_launch: true
        survey_enabled: "{{ item.survey }}"
        survey_spec: "{{ demo_change_survey if item.survey else omit }}"
        verbosity: 0
        state: present
```

- [ ] **Step 5: Update README opening bullets if they still say the machine credential is only for parity — mention it is attached to Demo 04.**

Example replacement fragment for the credential bullet:

```markdown
- one enabled weekly schedule, one webhook notification template pointing at
  a non-routable URL, one machine credential (fake password) attached to the
  surveyed platform-change template, and one label — so every object type
  compared by `verify_parity.yml` is exercised by seeded content (execution
  environments excepted: a custom EE needs a pullable image, and the default
  EEs already exercise that type);
```

In post-bootstrap checks, keep the Credentials checklist item; optionally note Demo 04 shows the credential attached.

- [ ] **Step 6: Run offline gates touched by content/bootstrap.**

```bash
ansible-playbook --syntax-check content/playbooks/platform_change_window.yml
bash tests/syntax_check.sh
ANSIBLE_COLLECTIONS_PATH=.tmp/collections ansible-lint --offline \
  bootstrap.yml content/
```

If `.tmp/collections` is missing, run `tests/syntax_check.sh` first (it builds stubs), then re-run lint as in CI:

```bash
ANSIBLE_COLLECTIONS_PATH=.tmp/collections ansible-lint --offline \
  bootstrap.yml teardown.yml badpractice.yml export.yml import.yml \
  verify_smoke.yml verify_parity.yml verify_functional.yml verify_rbac.yml \
  tasks/ content/
bash tests/smoke_offline.sh
```

Expected: all exit 0. Template **names** are unchanged, so mock smoke should not need edits; if smoke fails, fix mock only if a new assertion was added (prefer not adding name-based playbook-path checks).

- [ ] **Step 7: Commit**

```bash
git add content/playbooks/platform_change_window.yml config/demo.yml \
  bootstrap.yml README.md QUICK-HOWTO.md AGENTS.md
git commit -m "$(cat <<'EOF'
feat: add Platform change-window demo and attach credential

Point Demo 04 at a Platform-specific playbook, create credentials before job
templates, and associate the demo machine credential with Demo 04.
EOF
)"
```

**Phase B gate:** Still five job templates; workflow unchanged (two nodes); `surveyed_change.yml` remains in the tree; no inventory sources; no approval nodes.

---

# Phase C — Verification depth

## Task 5: Lab RBAC example overlay

**Files:**
- Create: `config/verify.rbac.example.yml`
- Modify: `config/verify.customer.example.yml` (pointer comment above `rbac_users`)
- Modify: `verify_rbac.yml` (NOT_RUN help text paths)
- Modify: `README.md` Layer 4 commands to use the new example file

**Interfaces:**
- Consumes: seeded usernames/templates from `config/demo.yml`.
- Produces: copy-pasteable lab overlay; default `config/verify.yml` remains without `rbac_users` (empty → NOT_RUN).

- [ ] **Step 1: Create `config/verify.rbac.example.yml`:**

```yaml
---
# EXAMPLE lab RBAC overlay for verify_rbac.yml against the seeded demo users.
# Copy to a gitignored file (for example config/verify.rbac.yml) if you customize
# it. Passwords are NEVER set here — use RBAC_DEMO_PASSWORD or Vault
# demo_user_password.
#
#   export RBAC_DEMO_PASSWORD='…'
#   ansible-playbook verify_rbac.yml -e @config/verify.rbac.example.yml
#
# Default config/verify.yml leaves rbac_users empty so accidental runs are
# NOT_RUN unless explicitly opted in.

rbac_allow_empty: false
rbac_users:
  - username: demo-alice
    organization: Demo Linux
    expected_job_templates:
      - Demo 01 - Linux hello
      - Demo 02 - Linux inventory report
    forbidden_organizations:
      - Demo Network
      - Demo Platform
  - username: demo-carol
    organization: Demo Network
    expected_job_templates:
      - Demo 03 - Network discovery simulation
    forbidden_organizations:
      - Demo Linux
      - Demo Platform
  - username: demo-erin
    organization: Demo Platform
    expected_job_templates:
      - Demo 04 - Surveyed platform change
      - Demo 05 - Controlled outcome
    forbidden_organizations:
      - Demo Linux
      - Demo Network
```

- [ ] **Step 2: In `config/verify.customer.example.yml`, above the `rbac_users` key, add:**

```yaml
# For the stock seeded demo users only, prefer config/verify.rbac.example.yml.
# Keep this customer file for mixed customer-shaped functional + RBAC overlays.
```

- [ ] **Step 3: In `verify_rbac.yml`, update the NOT_RUN report and fail_msg to mention both example paths:**

Replace the “No rbac_users configured…” lines so they say:

```text
No rbac_users configured (see config/verify.rbac.example.yml or
config/verify.customer.example.yml).
```

and the assert `fail_msg` similarly references `config/verify.rbac.example.yml` first.

- [ ] **Step 4: Update README Layer 4 to use `-e @config/verify.rbac.example.yml`.**

- [ ] **Step 5: Run RBAC offline suite.**

```bash
bash tests/rbac_offline.sh
```

Expected: exit 0 (suite uses its own fixtures; example YAML is not required to be loaded by the offline harness).

- [ ] **Step 6: Commit**

```bash
git add config/verify.rbac.example.yml config/verify.customer.example.yml \
  verify_rbac.yml README.md
git commit -m "$(cat <<'EOF'
docs: add lab RBAC example overlay for verify_rbac

Give operators a seeded-demo rbac_users file and point Layer 4 docs at it.
EOF
)"
```

## Task 6: Parity expansion policy + live acceptance prep

**Files:**
- Modify: `config/verify.yml` (comment block after `parity_types` / near the Phase 2 note)
- Create: `docs/live-acceptance-prep.md`
- Modify: `README.md` (Live acceptance status → link the prep doc; mention parity policy)
- Modify: `AGENTS.md` (one-line pointer under verification if useful)

**Interfaces:**
- Consumes: Phase 2 design “Expanded parity” and “Live acceptance” lists.
- Produces: explicit non-enablement policy + prep checklist without live claims.

- [ ] **Step 1: Extend the comment in `config/verify.yml` after the labels type (near the existing “Gateway RBAC… Phase 2” note) with:**

```yaml
# Expanded parity (disabled until real AAP 2.5 response fixtures exist).
# Do not enable these by guessing API shapes. To promote a type:
#   1. Capture a real AAP 2.5 list response for source and target routes.
#   2. Add offline fixtures under tests/fixtures/parity/.
#   3. Enable the type here with verified key/field paths only.
# Candidates: groups; group-host associations; inventory sources;
# custom credential types; JT inventory/credentials/EE/survey/notification
# associations; workflow nodes/edges; schedule rrule detail;
# organization/team memberships; platform role assignments;
# gateway authenticator definitions and maps.
# Never compare credential secrets.
```

- [ ] **Step 2: Create `docs/live-acceptance-prep.md`:**

```markdown
# Live acceptance prep (AAP 2.5 RPM → AAP 2.5 on OpenShift)

This repository **verifies** a migration; it does not perform one. Offline CI
passing does **not** mean live acceptance has been run.

## What offline CI already proves

- Pure-Python parity filters and pagination URL pinning
- Playbook syntax and ansible-lint against stub collections
- Smoke / parity / functional / customer-functional / RBAC behaviours against
  local mocks and stubs
- Export/import fail-closed contract and offline runtime harness

## What a live acceptance run must still cover

- Source and target gateway authentication (HTTPS + cert validation)
- Multi-page API content and duplicate names across organizations
- Private SCM project sync (if in scope for the lab)
- Custom EE pull + launch (if in scope; not seeded by default bootstrap)
- External credential use (for example CyberArk) without reading secrets back
- Disposable SSH canary only with allowlist gates
- Workflow launch; inventory-source update when used
- Schedule verification; ServiceNow **sandbox** notifier if used
- Restricted-user visibility via `verify_rbac.yml`
- Manual reviews: AD/SSO mapping, instance/container groups, mesh, private
  automation hub

## What this repository will never claim from offline tests alone

- On-premises GitHub connectivity
- CyberArk or ServiceNow integration success
- That a custom EE image pulls on OpenShift
- Tier-2 firewall/SSH reachability
- AD login or group mapping correctness
- Any AAP 2.6 behaviour
```

- [ ] **Step 3: Replace README “### Live acceptance status” body with a short pointer:**

```markdown
### Live acceptance status

Offline tests pass in CI. Live AAP 2.5 RPM-to-OpenShift acceptance remains
outstanding; no live AAP result is claimed here. See
[docs/live-acceptance-prep.md](docs/live-acceptance-prep.md) for what offline
covers, what a live run must still prove, and what this repository will never
claim from mocks alone.
```

- [ ] **Step 4: Commit**

```bash
git add config/verify.yml docs/live-acceptance-prep.md README.md AGENTS.md
git commit -m "$(cat <<'EOF'
docs: record parity expansion policy and live acceptance prep

Keep speculative parity types disabled until fixture-backed, and document
what live acceptance must still cover.
EOF
)"
```

## Task 7: Final initiative verification

**Files:**
- None required beyond fixes if gates fail

**Interfaces:**
- Consumes: all Phase A–C commits on the branch.
- Produces: green offline suite + doc coverage checklist.

- [ ] **Step 1: Confirm discoverability.**

```bash
rg -n 'verify_rbac|verify\.rbac\.example|object transfer|network_discovery|platform_change_window|live-acceptance-prep' \
  README.md QUICK-HOWTO.md AGENTS.md docs/
```

Expected: hits for RBAC example, object transfer, both new playbooks, live-acceptance prep.

- [ ] **Step 2: Run the full offline suite used by CI.**

```bash
python3 -m pytest tests/ -q
bash -n tests/*.sh
bash tests/syntax_check.sh
ANSIBLE_COLLECTIONS_PATH=.tmp/collections ansible-lint --offline \
  bootstrap.yml teardown.yml badpractice.yml export.yml import.yml \
  verify_smoke.yml verify_parity.yml verify_functional.yml verify_rbac.yml \
  tasks/ content/
bash tests/export_import_offline.sh
bash tests/pagination_offline.sh
bash tests/parity_offline.sh
bash tests/smoke_offline.sh
bash tests/functional_offline.sh
bash tests/customer_functional_offline.sh
bash tests/rbac_offline.sh
```

Expected: every command exits 0.

- [ ] **Step 3: If anything fails, fix in a focused follow-up commit; do not weaken safety gates.**

- [ ] **Step 4: Final commit only if Task 7 produced fixes; otherwise stop.**

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|---|---|
| README map + architecture + Layer 4 + object transfer | Task 1 |
| QUICK-HOWTO links | Task 2 |
| CI stale branches | Task 2 |
| Network playbook + Demo 03 | Task 3 |
| Platform playbook + Demo 04 + credential attach + credential-before-JT | Task 4 |
| Keep surveyed_change.yml; no approval/inventory source/third WF node | Task 4 gate |
| Lab RBAC example; default verify.yml empty rbac | Task 5 |
| Parity expansion policy | Task 6 |
| Live acceptance prep only | Task 6 |
| No LICENSE; no bootstrap split; no live AAP run | Out of plan (explicit) |

No TBD/TODO placeholders remain. Phase A does not link a not-yet-created RBAC file.
