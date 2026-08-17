# AGENTS

## Purpose
Bootstraps an empty Ansible Automation Platform 2.5 with safe demo content:
three organizations, teams, local users with team-scoped RBAC, inventories,
SCM projects, job templates, and seeded job history. No task contacts a real
managed host.

## Layout
- `bootstrap.yml` — single playbook; runs from localhost against the platform
  gateway (`ansible.platform`) and controller (`ansible.controller`).
- `config/demo.yml` — all demo data: orgs, teams, users, inventories, hosts,
  groups, projects, job templates, seed jobs, plus credentials, labels,
  notification templates, workflow job templates and schedules so every
  enabled `parity_types` entry is exercised by seeded content (execution
  environments deliberately excepted — a custom EE needs a pullable image;
  the default EEs exercise that parity type).
- `config/secrets.example.yml` — template for the Vault-encrypted
  `config/secrets.yml` (gitignored) holding `demo_user_password`.
- `content/playbooks/` — playbooks synced into the controller projects via SCM.
- `requirements.yml` — pins `ansible.platform` 2.5.x (floor 2.5.20250702,
  first build with `object_ids` name lookup on `role_user_assignment`) and
  `ansible.controller >=4.6.20,<4.7.0` (AAP 2.5 Platform Gateway-compatible
  export/import floor). Do not bump to 2.6/2.7 families against AAP 2.5.
- `teardown.yml` — removes everything bootstrap.yml created (reverse order).
- `verify_smoke.yml` / `verify_parity.yml` / `verify_functional.yml` —
  three-layer migration verification (see README section 7); config in
  `config/verify.yml`, shared pagination in `tasks/`, diff logic in
  `filter_plugins/parity.py` (pytest-covered in `tests/`).
- `export.yml` / `import.yml` — supplemental Automation Controller object
  transfer. The on-disk YAML is exactly the export module's `assets` mapping,
  protected by a SHA-256 sidecar; import requires explicit confirmation and
  consumes that mapping directly. These playbooks do not replace the supported
  component database/secrets migration and do not preserve full history.
- `docs/controller-object-transfer.md` — operator procedure and safety boundary
  for the supplemental export/import workflow.

## Conventions
- Keep every demo object prefixed with `Demo` so it can be identified and removed.
- Never commit secrets. User passwords come only from `demo_user_password` in
  the Vault-encrypted `config/secrets.yml`.
- Gateway objects (orgs, teams, users, Team*/Organization* role assignments)
  use `ansible.platform`; controller objects (inventories, hosts, groups,
  projects, templates, team content roles, job launches) use `ansible.controller`.
- `ansible.platform` 2.5.x has no `role_team_assignment` module; team grants on
  controller objects use `ansible.controller.role_team_assignment` with numeric
  `object_id` captured from the `register`ed creation results.
- RBAC model: each team gets `Inventory Admin` / `Project Admin` /
  `JobTemplate Admin` on its own organization's objects; each user gets
  `Organization Member` plus a `Team Admin` or `Team Member` team role.
- Controller auth: only `AAP_*` env vars are required. `bootstrap.yml` bridges
  them to the `ansible.controller` modules via
  `module_defaults: group/ansible.controller.controller` because most 4.6.x
  builds only read `CONTROLLER_*` env vars. Keep new controller tasks inside
  that group's coverage (all standard modules are).
- Controller object export/import uses the Platform Gateway root in
  `AAP_HOSTNAME`, probes `/api/controller/v2/config/`, requires controller
  `4.6.x`, and sets
  `CONTROLLER_OPTIONAL_API_URLPATTERN_PREFIX=/api/controller/` explicitly on
  the AWXKit-backed modules. Exported payloads stay mode `0600` under a mode
  `0700` directory; import fails closed on missing/malformed payloads,
  checksum mismatch, or absent `-e import_confirm=true`.
- `bootstrap.yml` and `teardown.yml` assert HTTPS + certificate validation
  before sending the admin credential (lab-only `bootstrap_allow_insecure` /
  `teardown_allow_insecure` overrides, default false). Do not weaken this.
- Workflow nodes are created in two passes (create all nodes, then link
  `success_nodes`) so a link never references a not-yet-created identifier.
- Labels cannot be deleted through the controller API; teardown relies on the
  controller garbage-collecting unreferenced labels once the referencing job
  templates are removed. The seed job history assert: items marked
  `expect_failure` must actually fail, or bootstrap fails.
- Gateway -> controller propagation is a periodic pull (15-minute default).
  The `Wait for gateway organizations to propagate to the controller` task
  polls `/api/controller/v2/organizations/` before any controller object is
  created; do not remove it or reorder controller tasks before it.
- Tags: `users` gates the local user block (also gated by `demo_create_users`),
  `rbac` marks the team content grants, `seed_history` marks job seeding.
- Verification is AAP 2.5 RPM (with gateway) -> AAP 2.5 on OpenShift. It
  verifies a migration; it does not perform one. Do not add AAP 2.6 API paths,
  collections, or docs. Source access is read-only (`SOURCE_AAP_*` env vars).
- Verification playbooks require HTTPS + cert validation before sending
  credentials (lab-only `*_allow_insecure` overrides default false and stamp
  the report UNSAFE), collect all failures, and fail once at the end. Reports
  go to `reports/` (gitignored).
- Operational errors (API/transport failure, pagination truncation, duplicate
  normalized keys, missing/invalid fixtures) always fail, in every
  `parity_fail_on` mode (`missing` | `drift` | `none`). Functional NOT_RUN is
  distinct from PASS.
- `filter_plugins/parity.py` stays free of Ansible imports so
  `python3 -m pytest tests/` runs without ansible installed. Pagination `next`
  links are untrusted: resolve_pagination_url pins the origin to the trusted
  host.
- Offline test entry points (also run in `.github/workflows/ci.yml`):
  `python3 -m pytest tests/`, `bash -n tests/*.sh`, `tests/syntax_check.sh`,
  `tests/export_import_offline.sh`, `tests/pagination_offline.sh`,
  `tests/parity_offline.sh`, `tests/smoke_offline.sh`,
  `tests/functional_offline.sh`, `tests/customer_functional_offline.sh`,
  `tests/rbac_offline.sh`. All are offline and need no AAP, Galaxy, or secrets.
  `tests/stubs/` holds local stub `ansible.controller` modules used by the
  customer-functional and controller object-transfer runtime tests;
  `tests/aap25_config_server.py` supplies the local 4.6.x/non-4.6.x endpoint.
  `tests/test_export_import_contract.py` pins the controller object-transfer
  payload and safety contract.
- Customer functional checks are opt-in and validated pre-flight
  (`tasks/functional_validate.yml` + `functional_field_specs`). `ssh_canary_job`
  is the only check that contacts a real host: it stays disabled unless
  `allow_real_managed_host_checks=true` AND `check.limit` exactly matches an
  entry in a non-empty `ssh_canary_allowlist` (broad targets rejected). Never
  weaken these gates.
- `verify_rbac.yml` proves positive (expected templates visible once in-org)
  and negative (no forbidden-org content) visibility, paginated as the user;
  `rbac_allow_empty` mirrors `functional_allow_empty` (NOT_RUN is never PASS).
  Reports/markers/output must never contain passwords, tokens, or extra_vars.

## Run
See README.md. Short form:
`ansible-playbook bootstrap.yml -e demo_scm_url=<git-url> -e @config/secrets.yml --ask-vault-pass`

## Rules
- Do not create WARP.md; keep this file current for significant changes.
- Do not add Co-Authored-By lines to commit messages.
