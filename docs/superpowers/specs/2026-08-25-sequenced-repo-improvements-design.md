# Sequenced repo improvements (docs → content → verification)

Date: 2026-08-25
Status: approved (design dialogue); awaiting user review of this written spec
Scope: **AAP 2.5 only**. No AAP 2.6. Sequence **A → B → C**.

## Background

A deep repository audit found the project already mature on safety, offline CI,
and migration-verification machinery. The highest-ROI gaps are:

1. **Discoverability** — `verify_rbac.yml`, `export.yml` / `import.yml`, and
   (to a lesser extent) `badpractice.yml` exist but are under-documented in
   README / QUICK-HOWTO relative to AGENTS.md.
2. **Demo narrative depth** — Network and Platform organizations share thin
   playbook stories; the machine credential is seeded but not attached to a
   template.
3. **Verification story completeness** — Layer 4 RBAC is implemented but absent
   from the operator runbook; parity expansion beyond current types must stay
   fixture-backed.

This initiative closes those gaps in order. It does not claim live AAP
acceptance results and does not change the “no real managed hosts by default”
rule.

## Goals

- Make existing capabilities discoverable from README / QUICK-HOWTO.
- Deepen the safe three-org demo so Network and Platform feel distinct.
- Complete the verification operator story with documented Layer 4 RBAC and
  conservative parity policy.
- Keep offline CI green; keep hard safety gates intact.

## Hard constraints

- AAP 2.5 only: `ansible.platform` 2.5.x, `ansible.controller` 4.6.x
  (`>=4.6.20,<4.7.0` for export/import).
- No default contact with real managed hosts; SSH canary remains opt-in +
  exact allowlist.
- No custom execution-environment seeding (needs a pullable image).
- Never compare credential secrets; never weaken HTTPS / certificate
  validation defaults.
- Offline CI stays fully offline (no Galaxy, Hub, or live AAP in CI).
- Keep `Demo` / `baddemo-` prefixes and org-scoping; Default organization
  only via deliberate `badpractice.yml`.
- Do not add Co-Authored-By lines; do not create WARP.md; keep AGENTS.md
  current when behavior or layout changes significantly.

## Out of scope

- Live AAP 2.5 RPM → OpenShift acceptance execution (prep checklist only).
- AAP 2.6 API paths, collections, or docs.
- Speculative `parity_types` without real AAP 2.5 response fixtures.
- Automating AD / SSO login.
- Inventory sources / constructed inventories (deferred past Phase B).
- Workflow approval nodes (deferred past Phase B).
- Splitting `bootstrap.yml` into includes (maintainability nicety; not this
  initiative).
- Adding a LICENSE file (unless requested separately); Phase A stays
  documentation-focused.

## Sequence overview

| Phase | Focus | Success criteria |
|---|---|---|
| **A** | Docs discoverability | README/QUICK-HOWTO surface RBAC, object transfer, badpractice; architecture map present; CI branch filter cleaned |
| **B** | Richer safe content | Distinct Network/Platform playbooks; credential attached to a template; smoke/teardown/docs/AGENTS match |
| **C** | Verification depth | Layer 4 in operator runbook; lab-ready RBAC example; parity expansion policy explicit; live-acceptance prep checklist only |

Implement and merge (or PR) one phase at a time. Do not start B until A is
done; do not start C until B is done—unless a phase is explicitly narrowed
during planning.

---

## Phase A — Docs discoverability

### Intent

Surface capabilities that already exist so operators do not need AGENTS.md or
tribal knowledge.

### README

1. **Top “What’s in this repo” map** (short):
   - bootstrap / teardown
   - verification layers: smoke → parity → functional → **RBAC**
   - optional `badpractice.yml`
   - supplemental controller object transfer →
     `docs/controller-object-transfer.md`
2. **Architecture sketch** (mermaid or clear bullet flow):
   - gateway objects → wait for controller propagation → controller objects →
     seed history
   - verification lanes: admin smoke vs restricted-user RBAC vs source→target
     parity
3. **Section 7 operator runbook — Layer 4**:
   - `verify_rbac.yml`
   - password via `RBAC_DEMO_PASSWORD` or Vault `demo_user_password`
   - positive (`expected_job_templates`) vs negative
     (`forbidden_organizations`) visibility
   - explicit note that smoke does **not** prove RBAC
   - pointer to the customer / RBAC example config shape
4. **Short export/import section**:
   - supplemental, not a supported component DB/secrets migration
   - link to `docs/controller-object-transfer.md`
   - call out checksum sidecar and `-e import_confirm=true` only (no full
     procedure duplicate)
5. Keep security/lifecycle badpractice pointer aligned with QUICK-HOWTO.

### QUICK-HOWTO

- Extend “Where to go next” with RBAC verification and object-transfer links.
- Remain one-page; do not paste the full export/import procedure.

### Hygiene

- CI `on.push.branches`: remove stale branch names
  (`worktree-migration-verification`, `customer-shaped-migration-lab`); keep
  `main`. Do not add ephemeral agent branches unless they are intentional
  long-lived integration branches.
- Update AGENTS.md only if the public layout/docs map description needs a
  one-line sync (prefer README as the operator entry point).

### Phase A non-goals

- No playbook or `config/demo.yml` content changes.
- No LICENSE addition in this phase.
- No rewrite of QUICK-HOWTO into a second full README.

### Phase A verification

- Manual doc review: every playbook named in AGENTS layout is reachable from
  README or a clearly linked child doc.
- Existing offline CI unchanged and still green (docs-only diff).

---

## Phase B — Richer safe demo content

### Intent

Make Demo Linux / Demo Network / Demo Platform feel distinct in the UI and
job history while remaining fully synthetic.

### Content

1. **Network playbook** — `content/playbooks/network_discovery.yml`
   - Simulated discovery: role, site, `network_os_family`, local-connection
     assertion, optional `set_stats`.
   - Point Demo 03 at this playbook (stop reusing `inventory_report.yml`).

2. **Platform playbook** — `content/playbooks/platform_change_window.yml`
   - Assert change-window / maintenance-style vars (or survey-compatible
     fields); emphasize no real systems changed.
   - Keep `surveyed_change.yml` and `controlled_outcome.yml`.
   - Add or retarget one Platform job template to this playbook if needed for
     a clear Platform narrative without overlapping Controlled outcome.

3. **Credential in use**
   - Attach `Demo Platform Machine Credential` to one Platform job template
     (Demo 04 or the new Platform template).
   - Password remains the obvious fake literal; parity continues to compare
     existence + type only.

4. **Workflow**
   - Keep the existing hello → report chain.
   - **No approval nodes** in this phase.
   - Optional third node only if it stays teardown-safe and smoke-covered;
     default is leave the two-node workflow unchanged unless planning shows a
     clear need.

5. **Deferred past B**
   - Inventory sources / constructed inventories.
   - Custom EEs, CyberArk, ServiceNow, real SSH.

### Ripple updates (required)

- `config/demo.yml` — playbook paths, template descriptions, credential
  association field(s) the bootstrap understands.
- `bootstrap.yml` — pass credential name(s) into `ansible.controller.job_template`
  where configured.
- `teardown.yml` — preserve reverse dependency order; no orphan types.
- `verify_smoke.yml`, `tests/mock_aap_server.py`, `tests/smoke_offline.sh` —
  names/counts stay accurate.
- README / QUICK-HOWTO object counts and post-bootstrap checklist.
- AGENTS.md if seeded object inventory description changes.

### Phase B verification

- Offline: `tests/syntax_check.sh`, ansible-lint on touched playbooks,
  `tests/smoke_offline.sh`, and any contract tests affected by demo shape.
- Content playbooks must not introduce modules that contact remote systems;
  keep `gather_facts: false` and local-connection assumptions.

---

## Phase C — Verification depth

### Intent

Close the “smoke ≠ RBAC” hole in the operator story; make lab RBAC runnable
via an example overlay; keep parity expansion honest.

### C1 — Document Layer 4 RBAC

- README operator runbook after Layer 3:
  - how to run `verify_rbac.yml`
  - password sourcing rules
  - positive vs negative visibility
  - `rbac_allow_empty` / `NOT_RUN` semantics (empty is never PASS)
- Link the example config shape.

### C2 — Lab-ready RBAC example

- Extend `config/verify.customer.example.yml` **or** add
  `config/verify.rbac.example.yml` with `rbac_users` entries for the seeded
  demo users / three orgs (at least one Team Admin such as `demo-alice` with
  expected Linux templates and forbidden Network/Platform orgs; optionally
  mirror for the other orgs).
- Default `config/verify.yml` keeps `rbac_users` empty (or unset) so
  accidental runs stay `NOT_RUN` unless explicitly opted in—same pattern as
  `functional_checks`.

### C3 — Parity expansion policy

- Do **not** enable new `parity_types` (groups, inventory sources, survey
  specs, workflow edges, role assignments, authenticators) until each has:
  - a real AAP 2.5 response shape confirmed, and
  - offline fixture coverage.
- Document the disabled-until-fixtures list in README and/or
  `config/verify.yml` comments; optionally add a one-line “how to promote a
  type” note for contributors.
- Never guess gateway RBAC / authenticator API shapes.

### C4 — Live acceptance prep only

- Short checklist (README subsection or `docs/` page) listing what a live
  RPM→OCP acceptance must cover, what offline already proves, and what this
  repo will never claim.
- No requirement to execute against a real AAP in this initiative.

### Phase C non-goals

- Claiming live acceptance results.
- Enabling speculative parity fields.
- Automating AD/SSO.
- Changing fail-closed pagination or secret-sentinel rules.

### Phase C verification

- Docs accuracy against `verify_rbac.yml` and
  `config/verify.customer.example.yml` (or the new RBAC example).
- `tests/rbac_offline.sh` remains green; no weakening of empty/`NOT_RUN`
  semantics.
- If only docs + example YAML change, full offline suite still green.

---

## Error handling and safety (all phases)

- Do not print passwords, tokens, or `extra_vars` values in reports or docs
  examples that look like real secrets.
- Example configs remain placeholders or demo-prefixed lab names only.
- Export/import docs continue to stress disposable/recoverable targets and
  explicit import confirmation.
- Insecure overrides stay lab-only and documented as such.

## Testing strategy

| Phase | Required checks |
|---|---|
| A | Manual link/coverage review; existing CI green |
| B | syntax, lint, smoke offline (+ pytest if contracts touch demo shape) |
| C | rbac offline + docs consistency; full offline suite if examples change validation paths |

Prefer TDD when changing playbook behavior or mock-server scenarios (failing
offline test first). Docs-only phases need review, not new unit tests.

## Rollout

1. Implement Phase A → PR → merge (or land on agreed branch).
2. Implement Phase B → PR.
3. Implement Phase C → PR.
4. Update AGENTS.md when each phase changes layout or operator-facing
   conventions significantly.

## Success definition (initiative complete)

- An operator reading only README + QUICK-HOWTO can find bootstrap, teardown,
  all four verification layers, badpractice, and object transfer.
- Demo Network and Demo Platform have distinct safe playbook narratives; a
  Platform template shows the demo machine credential attached.
- Operator runbook includes Layer 4 RBAC with a lab-ready example; parity
  policy forbids speculative types; live acceptance remains explicitly
  outstanding without false claims.
