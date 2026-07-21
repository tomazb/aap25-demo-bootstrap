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
  groups, projects, job templates, seed jobs.
- `config/secrets.example.yml` — template for the Vault-encrypted
  `config/secrets.yml` (gitignored) holding `demo_user_password`.
- `content/playbooks/` — playbooks synced into the controller projects via SCM.
- `requirements.yml` — pins `ansible.platform` 2.5.x and `ansible.controller`
  4.6.x. Do not bump to 2.6/2.7 families against AAP 2.5.

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
- Tags: `users` gates the local user block (also gated by `demo_create_users`),
  `rbac` marks the team content grants, `seed_history` marks job seeding.

## Run
See README.md. Short form:
`ansible-playbook bootstrap.yml -e demo_scm_url=<git-url> -e @config/secrets.yml --ask-vault-pass`

## Rules
- Do not create WARP.md; keep this file current for significant changes.
- Do not add Co-Authored-By lines to commit messages.
