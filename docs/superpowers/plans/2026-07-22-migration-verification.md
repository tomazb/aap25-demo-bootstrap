# Migration Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three-layer AAP 2.5 RPM→OCP migration verification (smoke gate, content parity, functional equivalence) to aap25-demo-bootstrap per `docs/superpowers/specs/2026-07-22-migration-verification-design.md`.

**Architecture:** Four flat top-level playbooks (`teardown.yml`, `verify_smoke.yml`, `verify_parity.yml`, `verify_functional.yml`) sharing a pagination task file and a pure-Python filter plugin (`filter_plugins/parity.py`) for normalize/diff/report logic. All API reads via `ansible.builtin.uri`; object mutation only via existing collections with the `module_defaults` auth bridge.

**Tech Stack:** ansible-core ≥2.15, `ansible.platform` ≥2.5.20250702, `ansible.controller` 4.6.x, Python 3 stdlib only, pytest for filter tests.

## Global Constraints

- Target auth: `AAP_HOSTNAME`/`AAP_USERNAME`/`AAP_PASSWORD`/`AAP_VALIDATE_CERTS` env vars. Source auth (parity only): `SOURCE_AAP_*` equivalents.
- Read-only against the source, always.
- Verify playbooks collect all failures and fail once at the end.
- Reports to `reports/` (gitignored), Markdown + raw JSON.
- No secrets in output; `no_log: true` on any task registering auth-bearing request loops is not needed for `uri` with `url_username` (not echoed), but never put passwords in URLs.
- Commit messages: no Co-Authored-By, no "Generated with" footers.

---

### Task 1: Filter plugin — `normalize_objects`

**Files:**
- Create: `filter_plugins/parity.py`
- Test: `tests/test_parity_filters.py`

**Interfaces:**
- Produces: `normalize_objects(rows, key, fields=None, exclude=None) -> dict[str, dict]` — `rows`: list of raw API row dicts; `key`: dotted path str or list of dotted path strs (joined with `" / "`); `fields`: dict `{out_name: dotted_path}`; `exclude`: dict `{dotted_path: [values]}` (row dropped when its value at path is in the list). Missing paths resolve to `None`. Duplicate keys: last row wins.
- Produces: internal helper `_get(row, dotted_path)` used by later tasks' functions.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_parity_filters.py
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "filter_plugins"))

from parity import normalize_objects


def test_normalize_simple_key_and_fields():
    rows = [
        {"name": "Demo Linux", "description": "x",
         "summary_fields": {"organization": {"name": "Org A"}}},
    ]
    out = normalize_objects(
        rows, key="name",
        fields={"organization": "summary_fields.organization.name"})
    assert out == {"Demo Linux": {"organization": "Org A"}}


def test_normalize_compound_key():
    rows = [{"name": "web01", "summary_fields": {"inventory": {"name": "Inv"}}}]
    out = normalize_objects(rows, key=["summary_fields.inventory.name", "name"])
    assert list(out) == ["Inv / web01"]


def test_normalize_missing_path_is_none():
    out = normalize_objects([{"name": "a"}], key="name", fields={"image": "image"})
    assert out["a"]["image"] is None


def test_normalize_exclude():
    rows = [{"name": "smart", "kind": "smart"}, {"name": "plain", "kind": ""}]
    out = normalize_objects(rows, key="name", exclude={"kind": ["smart", "constructed"]})
    assert list(out) == ["plain"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_parity_filters.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'parity'`.

- [ ] **Step 3: Write minimal implementation**

```python
# filter_plugins/parity.py
"""Parity comparison filters for AAP migration verification.

Pure functions; no Ansible imports so they are unit-testable with pytest.
"""


def _get(row, dotted_path):
    cur = row
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def normalize_objects(rows, key, fields=None, exclude=None):
    """Map raw API rows to {key: {field: value}} for comparison."""
    key_paths = [key] if isinstance(key, str) else list(key)
    fields = fields or {}
    exclude = exclude or {}
    out = {}
    for row in rows or []:
        if any(_get(row, path) in values for path, values in exclude.items()):
            continue
        k = " / ".join(str(_get(row, p)) for p in key_paths)
        out[k] = {name: _get(row, path) for name, path in fields.items()}
    return out


class FilterModule(object):
    def filters(self):
        return {
            "normalize_objects": normalize_objects,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_parity_filters.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add filter_plugins/parity.py tests/test_parity_filters.py
git commit -m "Add normalize_objects parity filter"
```

### Task 2: Filter plugin — `parity_diff` and `parity_report`

**Files:**
- Modify: `filter_plugins/parity.py`
- Test: `tests/test_parity_filters.py`

**Interfaces:**
- Consumes: `normalize_objects` output maps.
- Produces: `parity_diff(source_map, target_map) -> {"missing_on_target": [keys], "extra_on_target": [keys], "field_mismatches": [{"key","field","source","target"}]}` (all lists sorted).
- Produces: `parity_report(results, meta) -> str` (Markdown). `results`: dict `{type_name: diff_dict}`; `meta`: dict with `source`, `target`, `timestamp`, `fail_on` strings. Report has one section per type, a `## Summary` table, and ends with `RESULT: PASS` or `RESULT: FAIL` (FAIL when any type has `missing_on_target` or `field_mismatches` and `meta["fail_on"] == "missing"`; always PASS when `fail_on == "none"`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_parity_filters.py`:

```python
from parity import parity_diff, parity_report


def test_diff_missing_extra_mismatch():
    src = {"a": {"f": 1}, "b": {"f": 2}, "c": {"f": 3}}
    tgt = {"a": {"f": 1}, "c": {"f": 9}, "d": {"f": 4}}
    d = parity_diff(src, tgt)
    assert d["missing_on_target"] == ["b"]
    assert d["extra_on_target"] == ["d"]
    assert d["field_mismatches"] == [
        {"key": "c", "field": "f", "source": 3, "target": 9}]


def test_diff_clean():
    d = parity_diff({"a": {}}, {"a": {}})
    assert d == {"missing_on_target": [], "extra_on_target": [],
                 "field_mismatches": []}


def test_report_fail_and_pass():
    results = {"projects": {"missing_on_target": ["P1"],
                            "extra_on_target": [], "field_mismatches": []}}
    meta = {"source": "s", "target": "t", "timestamp": "T", "fail_on": "missing"}
    md = parity_report(results, meta)
    assert "RESULT: FAIL" in md and "P1" in md and "projects" in md
    meta["fail_on"] = "none"
    assert "RESULT: PASS" in parity_report(results, meta)
    clean = {"projects": {"missing_on_target": [], "extra_on_target": [],
                          "field_mismatches": []}}
    meta["fail_on"] = "missing"
    assert "RESULT: PASS" in parity_report(clean, meta)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_parity_filters.py -v`
Expected: ImportError on `parity_diff`.

- [ ] **Step 3: Implement**

Add to `filter_plugins/parity.py` (and register both in `FilterModule.filters`):

```python
def parity_diff(source_map, target_map):
    missing = sorted(k for k in source_map if k not in target_map)
    extra = sorted(k for k in target_map if k not in source_map)
    mismatches = []
    for k in sorted(set(source_map) & set(target_map)):
        for field, sval in source_map[k].items():
            tval = target_map[k].get(field)
            if sval != tval:
                mismatches.append(
                    {"key": k, "field": field, "source": sval, "target": tval})
    return {"missing_on_target": missing, "extra_on_target": extra,
            "field_mismatches": mismatches}


def parity_report(results, meta):
    failed = any(d["missing_on_target"] or d["field_mismatches"]
                 for d in results.values())
    verdict = "FAIL" if failed and meta.get("fail_on") == "missing" else "PASS"
    lines = [
        "# Migration content parity report",
        "",
        f"- Source: {meta.get('source')}",
        f"- Target: {meta.get('target')}",
        f"- Timestamp: {meta.get('timestamp')}",
        f"- Fail mode: {meta.get('fail_on')}",
        "",
        "## Summary",
        "",
        "| Type | Missing on target | Field mismatches | Extra on target |",
        "|---|---|---|---|",
    ]
    for name in sorted(results):
        d = results[name]
        lines.append(
            f"| {name} | {len(d['missing_on_target'])} "
            f"| {len(d['field_mismatches'])} | {len(d['extra_on_target'])} |")
    for name in sorted(results):
        d = results[name]
        lines += ["", f"## {name}", ""]
        if not (d["missing_on_target"] or d["extra_on_target"]
                or d["field_mismatches"]):
            lines.append("Clean.")
            continue
        for k in d["missing_on_target"]:
            lines.append(f"- MISSING on target: `{k}`")
        for m in d["field_mismatches"]:
            lines.append(
                f"- MISMATCH `{m['key']}` field `{m['field']}`: "
                f"source=`{m['source']}` target=`{m['target']}`")
        for k in d["extra_on_target"]:
            lines.append(f"- extra on target (info): `{k}`")
    lines += ["", f"RESULT: {verdict}", ""]
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_parity_filters.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add filter_plugins/parity.py tests/test_parity_filters.py
git commit -m "Add parity_diff and parity_report filters"
```

### Task 3: Syntax-check harness and pagination task file

**Files:**
- Create: `tests/syntax_check.sh`
- Create: `tasks/paginated_get.yml`

**Interfaces:**
- Produces: `tasks/paginated_get.yml` — include with vars `pg_host` (no trailing slash), `pg_path` (starts `/`, should carry `?page_size=200`), `pg_user`, `pg_password`, `pg_validate_certs`; before first include the caller MUST `set_fact: pg_results: []`, `pg_next: "{{ pg_path }}"`, `pg_pages: 0`. After it returns, `pg_results` holds all rows. Bound: `parity_max_pages` (default 100).
- Produces: `tests/syntax_check.sh` — creates stub `ansible.platform` + copies installed-or-stub `ansible.controller` under `.tmp/collections`, then `--syntax-check`s every playbook passed as args (default: all four verify/teardown playbooks + bootstrap.yml).

- [ ] **Step 1: Write `tests/syntax_check.sh`**

```bash
#!/usr/bin/env bash
# Syntax-check playbooks without Red Hat hub access: stub the certified
# collections just enough for module resolution.
set -euo pipefail
cd "$(dirname "$0")/.."
CP=.tmp/collections/ansible_collections
mkdir -p "$CP/ansible/platform/plugins/modules" "$CP/ansible/platform/meta"
printf 'requires_ansible: ">=2.15"\n' > "$CP/ansible/platform/meta/runtime.yml"
cat > "$CP/ansible/platform/galaxy.yml" <<'EOF'
namespace: ansible
name: platform
version: 2.5.20250702
EOF
for m in organization team user role_user_assignment; do
  cat > "$CP/ansible/platform/plugins/modules/$m.py" <<'EOF'
DOCUMENTATION = '''
module: stub
short_description: stub
description: [stub]
options: {}
author: [stub]
'''
EOF
done
if [ ! -d "$CP/ansible/controller" ]; then
  if [ -d "$HOME/.ansible/collections/ansible_collections/ansible/controller" ]; then
    cp -r "$HOME/.ansible/collections/ansible_collections/ansible/controller" "$CP/ansible/controller"
  else
    ansible-galaxy collection install 'awx.awx:>=24.6.0,<24.7.0' -p .tmp/collections >/dev/null
    cp -r "$CP/awx/awx" "$CP/ansible/controller"
    printf '{"collection_info": {"namespace": "ansible", "name": "controller", "version": "4.6.99"}}\n' \
      > "$CP/ansible/controller/MANIFEST.json"
  fi
fi
PLAYBOOKS=("$@")
[ ${#PLAYBOOKS[@]} -gt 0 ] || PLAYBOOKS=(bootstrap.yml teardown.yml verify_smoke.yml verify_parity.yml verify_functional.yml)
for pb in "${PLAYBOOKS[@]}"; do
  ANSIBLE_COLLECTIONS_PATH=.tmp/collections ansible-playbook --syntax-check "$pb"
done
echo "SYNTAX OK: ${PLAYBOOKS[*]}"
```

- [ ] **Step 2: Write `tasks/paginated_get.yml`**

```yaml
---
# Follow API pagination, accumulating rows into pg_results.
# Caller must set_fact first: pg_results: [], pg_next: "{{ pg_path }}", pg_pages: 0
- name: Fetch one page
  ansible.builtin.uri:
    url: "{{ pg_host }}{{ pg_next }}"
    method: GET
    url_username: "{{ pg_user }}"
    url_password: "{{ pg_password }}"
    force_basic_auth: true
    validate_certs: "{{ pg_validate_certs }}"
    return_content: true
    status_code: [200]
  register: pg_page

- name: Accumulate page results
  ansible.builtin.set_fact:
    pg_results: "{{ pg_results + (pg_page.json.results | default([])) }}"
    pg_next: "{{ pg_page.json.next | default('') }}"
    pg_pages: "{{ pg_pages | int + 1 }}"

- name: Fetch next page
  ansible.builtin.include_tasks: paginated_get.yml
  when:
    - pg_next | length > 0
    - pg_pages | int < parity_max_pages | default(100)
```

- [ ] **Step 3: Verify harness works against existing playbook**

Run: `chmod +x tests/syntax_check.sh && tests/syntax_check.sh bootstrap.yml`
Expected: `SYNTAX OK: bootstrap.yml`. Also add `.tmp/` to `.gitignore`.

- [ ] **Step 4: Commit**

```bash
git add tests/syntax_check.sh tasks/paginated_get.yml .gitignore
git commit -m "Add pagination task file and offline syntax-check harness"
```

### Task 4: Verification config and report dir

**Files:**
- Create: `config/verify.yml`
- Modify: `.gitignore` (add `reports/`)

**Interfaces:**
- Produces: vars consumed by verify playbooks: `parity_types` (dict described below), `parity_fail_on` (`missing`|`none`, default `missing`), `parity_max_pages`, `functional_checks` (list, default empty), `verify_report_dir` (default `reports`).

- [ ] **Step 1: Write `config/verify.yml`**

```yaml
---
# Configuration for the migration verification playbooks
# (verify_parity.yml, verify_functional.yml). See README section
# "Migration verification".

verify_report_dir: reports
parity_fail_on: missing        # missing | none
parity_max_pages: 100

# Object types compared by verify_parity.yml. source paths are RPM
# controller API (/api/v2, works for AAP 2.4 and 2.5 sources); target
# paths are AAP 2.5 gateway/controller. Disable a type with enabled: false.
parity_types:
  organizations:
    enabled: true
    source_path: /api/v2/organizations/?page_size=200
    target_path: /api/gateway/v1/organizations/?page_size=200
    key: name
  users:
    enabled: true
    source_path: /api/v2/users/?page_size=200
    target_path: /api/gateway/v1/users/?page_size=200
    key: username
    fields:
      is_superuser: is_superuser
  teams:
    enabled: true
    source_path: /api/v2/teams/?page_size=200
    target_path: /api/gateway/v1/teams/?page_size=200
    key: name
  credentials:
    enabled: true
    source_path: /api/v2/credentials/?page_size=200
    target_path: /api/controller/v2/credentials/?page_size=200
    key: name
    fields:
      credential_type: summary_fields.credential_type.name
  projects:
    enabled: true
    source_path: /api/v2/projects/?page_size=200
    target_path: /api/controller/v2/projects/?page_size=200
    key: name
    fields:
      scm_type: scm_type
      scm_url: scm_url
      scm_branch: scm_branch
  inventories:
    enabled: true
    source_path: /api/v2/inventories/?page_size=200
    target_path: /api/controller/v2/inventories/?page_size=200
    key: name
    fields:
      organization: summary_fields.organization.name
      kind: kind
  hosts:
    enabled: true
    source_path: /api/v2/hosts/?page_size=200
    target_path: /api/controller/v2/hosts/?page_size=200
    key:
      - summary_fields.inventory.name
      - name
    exclude:
      summary_fields.inventory.kind: [smart, constructed]
  job_templates:
    enabled: true
    source_path: /api/v2/job_templates/?page_size=200
    target_path: /api/controller/v2/job_templates/?page_size=200
    key: name
    fields:
      playbook: playbook
      project: summary_fields.project.name
  workflow_job_templates:
    enabled: true
    source_path: /api/v2/workflow_job_templates/?page_size=200
    target_path: /api/controller/v2/workflow_job_templates/?page_size=200
    key: name
  schedules:
    enabled: true
    source_path: /api/v2/schedules/?page_size=200
    target_path: /api/controller/v2/schedules/?page_size=200
    key: name
    fields:
      enabled: enabled
      unified_job_template: summary_fields.unified_job_template.name
  notification_templates:
    enabled: true
    source_path: /api/v2/notification_templates/?page_size=200
    target_path: /api/controller/v2/notification_templates/?page_size=200
    key: name
    fields:
      notification_type: notification_type
  execution_environments:
    enabled: true
    source_path: /api/v2/execution_environments/?page_size=200
    target_path: /api/controller/v2/execution_environments/?page_size=200
    key: name
    fields:
      image: image
  labels:
    enabled: true
    source_path: /api/v2/labels/?page_size=200
    target_path: /api/controller/v2/labels/?page_size=200
    key: name

# Layer 3: curated, per-migration functional checks. Empty by default —
# verify_functional.yml then reports "nothing configured" and exits 0.
# Supported types:
#   - type: job_template      # launches and waits; success required
#     name: My migrated JT
#     organization: My Org
#     job_type: run           # or check
#     limit: ""               # optional
#     extra_vars: {}          # optional
#   - type: project_update    # sync + wait; proves SCM credential decrypt
#     name: My migrated project
#     organization: My Org
#   - type: notification_test # fires test notification, polls for success
#     name: My notifier
functional_checks: []
```

- [ ] **Step 2: Add `reports/` (and `.tmp/` if not yet) to `.gitignore`, verify YAML parses**

Run: `python3 -c "import yaml; yaml.safe_load(open('config/verify.yml')); print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add config/verify.yml .gitignore
git commit -m "Add migration verification configuration"
```

### Task 5: `teardown.yml`

**Files:**
- Create: `teardown.yml`

**Interfaces:**
- Consumes: `config/demo.yml` lists; `AAP_*` env vars; `module_defaults` bridge identical to `bootstrap.yml`.

- [ ] **Step 1: Write `teardown.yml`**

```yaml
---
- name: Remove all demo content created by bootstrap.yml
  hosts: localhost
  connection: local
  gather_facts: false

  vars_files:
    - config/demo.yml

  vars:
    aap_bootstrap_hostname: "{{ lookup('ansible.builtin.env', 'AAP_HOSTNAME') }}"
    aap_bootstrap_username: "{{ lookup('ansible.builtin.env', 'AAP_USERNAME') }}"
    aap_bootstrap_password: "{{ lookup('ansible.builtin.env', 'AAP_PASSWORD') }}"
    aap_bootstrap_validate_certs: >-
      {{ (lookup('ansible.builtin.env', 'AAP_VALIDATE_CERTS') or 'true') | bool }}

  module_defaults:
    group/ansible.controller.controller:
      controller_host: "{{ aap_bootstrap_hostname }}"
      controller_username: "{{ aap_bootstrap_username }}"
      controller_password: "{{ aap_bootstrap_password }}"
      validate_certs: "{{ aap_bootstrap_validate_certs }}"

  pre_tasks:
    - name: Validate required inputs
      ansible.builtin.assert:
        that:
          - lookup('ansible.builtin.env', 'AAP_HOSTNAME') | length > 0
          - lookup('ansible.builtin.env', 'AAP_USERNAME') | length > 0
          - lookup('ansible.builtin.env', 'AAP_PASSWORD') | length > 0
        fail_msg: Export AAP_HOSTNAME, AAP_USERNAME and AAP_PASSWORD first.

  tasks:
    # Strict reverse dependency order relative to bootstrap.yml. Job
    # history of deleted templates remains visible in the controller by
    # design.
    - name: Remove demo job templates
      ansible.controller.job_template:
        name: "{{ item.name }}"
        organization: "{{ item.organization }}"
        state: absent
      loop: "{{ demo_job_templates }}"
      loop_control:
        label: "{{ item.organization }} / {{ item.name }}"

    - name: Remove demo projects
      ansible.controller.project:
        name: "{{ item.name }}"
        organization: "{{ item.organization }}"
        state: absent
      loop: "{{ demo_projects }}"
      loop_control:
        label: "{{ item.organization }} / {{ item.name }}"

    - name: Remove demo inventories (hosts and groups are removed with them)
      ansible.controller.inventory:
        name: "{{ item.name }}"
        organization: "{{ item.organization }}"
        state: absent
      loop: "{{ demo_inventories }}"
      loop_control:
        label: "{{ item.organization }} / {{ item.name }}"

    - name: Remove demo users
      ansible.platform.user:
        username: "{{ item.username }}"
        state: absent
      loop: "{{ demo_users }}"
      loop_control:
        label: "{{ item.username }}"

    - name: Remove demo teams
      ansible.platform.team:
        name: "{{ item.name }}"
        organization: "{{ item.organization }}"
        state: absent
      loop: "{{ demo_teams }}"
      loop_control:
        label: "{{ item.organization }} / {{ item.name }}"

    - name: Remove demo organizations
      ansible.platform.organization:
        name: "{{ item.name }}"
        state: absent
      loop: "{{ demo_organizations }}"
      loop_control:
        label: "{{ item.name }}"
```

- [ ] **Step 2: Syntax check**

Run: `tests/syntax_check.sh teardown.yml`
Expected: `SYNTAX OK: teardown.yml`

- [ ] **Step 3: Commit**

```bash
git add teardown.yml
git commit -m "Add teardown playbook for demo content"
```

### Task 6: `verify_smoke.yml`

**Files:**
- Create: `verify_smoke.yml`

**Interfaces:**
- Consumes: `config/demo.yml` lists, `AAP_*` env vars, `verify_report_dir` from `config/verify.yml`.
- Produces: `reports/smoke-<UTC timestamp>.md`; rc 0 iff all checks pass.

- [ ] **Step 1: Write `verify_smoke.yml`**

Checks are pure GETs; each appends to `smoke_failures` instead of failing immediately. Count checks use exact-name filters.

```yaml
---
- name: Smoke-verify demo state on the AAP 2.5 target
  hosts: localhost
  connection: local
  gather_facts: false

  vars_files:
    - config/demo.yml
    - config/verify.yml

  vars:
    aap_hostname: >-
      {{ lookup('ansible.builtin.env', 'AAP_HOSTNAME') | regex_replace('/+$', '') }}
    aap_username: "{{ lookup('ansible.builtin.env', 'AAP_USERNAME') }}"
    aap_password: "{{ lookup('ansible.builtin.env', 'AAP_PASSWORD') }}"
    aap_validate_certs: >-
      {{ (lookup('ansible.builtin.env', 'AAP_VALIDATE_CERTS') or 'true') | bool }}
    smoke_failures: []
    smoke_timestamp: "{{ lookup('ansible.builtin.pipe', 'date -u +%Y%m%dT%H%M%SZ') }}"

  pre_tasks:
    - name: Validate required inputs
      ansible.builtin.assert:
        that:
          - aap_hostname | length > 0
          - aap_username | length > 0
          - aap_password | length > 0
        fail_msg: Export AAP_HOSTNAME, AAP_USERNAME and AAP_PASSWORD first.

  tasks:
    - name: Check gateway organizations exist
      ansible.builtin.uri:
        url: "{{ aap_hostname }}/api/gateway/v1/organizations/?name={{ item.name | urlencode }}"
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: smoke_orgs
      loop: "{{ demo_organizations }}"
      loop_control:
        label: "{{ item.name }}"

    - name: Record missing organizations
      ansible.builtin.set_fact:
        smoke_failures: "{{ smoke_failures + ['organization missing: ' ~ item.item.name] }}"
      loop: "{{ smoke_orgs.results }}"
      loop_control:
        label: "{{ item.item.name }}"
      when: (item.json.count | default(0) | int) < 1

    - name: Check gateway teams exist
      ansible.builtin.uri:
        url: "{{ aap_hostname }}/api/gateway/v1/teams/?name={{ item.name | urlencode }}"
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: smoke_teams
      loop: "{{ demo_teams }}"
      loop_control:
        label: "{{ item.name }}"

    - name: Record missing teams
      ansible.builtin.set_fact:
        smoke_failures: "{{ smoke_failures + ['team missing: ' ~ item.item.name] }}"
      loop: "{{ smoke_teams.results }}"
      loop_control:
        label: "{{ item.item.name }}"
      when: (item.json.count | default(0) | int) < 1

    - name: Check gateway users exist
      ansible.builtin.uri:
        url: "{{ aap_hostname }}/api/gateway/v1/users/?username={{ item.username | urlencode }}"
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: smoke_users
      loop: "{{ demo_users }}"
      loop_control:
        label: "{{ item.username }}"
      when: demo_create_users | default(true) | bool

    - name: Record missing users
      ansible.builtin.set_fact:
        smoke_failures: "{{ smoke_failures + ['user missing: ' ~ item.item.username] }}"
      loop: "{{ smoke_users.results | default([]) }}"
      loop_control:
        label: "{{ item.item.username | default('skipped') }}"
      when:
        - demo_create_users | default(true) | bool
        - (item.json.count | default(0) | int) < 1

    - name: Check controller inventories exist
      ansible.builtin.uri:
        url: "{{ aap_hostname }}/api/controller/v2/inventories/?name={{ item.name | urlencode }}"
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: smoke_inventories
      loop: "{{ demo_inventories }}"
      loop_control:
        label: "{{ item.name }}"

    - name: Record missing inventories
      ansible.builtin.set_fact:
        smoke_failures: "{{ smoke_failures + ['inventory missing: ' ~ item.item.name] }}"
      loop: "{{ smoke_inventories.results }}"
      loop_control:
        label: "{{ item.item.name }}"
      when: (item.json.count | default(0) | int) < 1

    - name: Check projects exist and last-synced successfully
      ansible.builtin.uri:
        url: "{{ aap_hostname }}/api/controller/v2/projects/?name={{ item.name | urlencode }}"
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: smoke_projects
      loop: "{{ demo_projects }}"
      loop_control:
        label: "{{ item.name }}"

    - name: Record missing or unsynced projects
      ansible.builtin.set_fact:
        smoke_failures: >-
          {{ smoke_failures + ['project missing or not successfully synced: '
             ~ item.item.name ~ ' (status='
             ~ (item.json.results[0].status | default('absent')) ~ ')'] }}
      loop: "{{ smoke_projects.results }}"
      loop_control:
        label: "{{ item.item.name }}"
      when: >-
        (item.json.count | default(0) | int) < 1
        or (item.json.results[0].status | default('')) != 'successful'

    - name: Check job templates exist
      ansible.builtin.uri:
        url: "{{ aap_hostname }}/api/controller/v2/job_templates/?name={{ item.name | urlencode }}"
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: smoke_templates
      loop: "{{ demo_job_templates }}"
      loop_control:
        label: "{{ item.name }}"

    - name: Record missing job templates
      ansible.builtin.set_fact:
        smoke_failures: "{{ smoke_failures + ['job template missing: ' ~ item.item.name] }}"
      loop: "{{ smoke_templates.results }}"
      loop_control:
        label: "{{ item.item.name }}"
      when: (item.json.count | default(0) | int) < 1

    - name: Check each seeded template has at least one successful run
      ansible.builtin.uri:
        url: >-
          {{ aap_hostname }}/api/controller/v2/jobs/?name={{ item.name | urlencode
          }}&status=successful&page_size=1
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: smoke_job_history
      loop: "{{ demo_job_templates }}"
      loop_control:
        label: "{{ item.name }}"

    - name: Record templates without successful history
      ansible.builtin.set_fact:
        smoke_failures: "{{ smoke_failures + ['no successful run recorded: ' ~ item.item.name] }}"
      loop: "{{ smoke_job_history.results }}"
      loop_control:
        label: "{{ item.item.name }}"
      when: (item.json.count | default(0) | int) < 1

    - name: Check the controlled-outcome template has a failed run
      ansible.builtin.uri:
        url: >-
          {{ aap_hostname }}/api/controller/v2/jobs/?name={{
          'Demo 05 - Controlled outcome' | urlencode }}&status=failed&page_size=1
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: smoke_failed_history

    - name: Record missing intentional-failure history
      ansible.builtin.set_fact:
        smoke_failures: >-
          {{ smoke_failures + ['no failed run recorded for Demo 05 - Controlled outcome'] }}
      when: (smoke_failed_history.json.count | default(0) | int) < 1

    - name: Ensure report directory exists
      ansible.builtin.file:
        path: "{{ verify_report_dir }}"
        state: directory
        mode: "0755"

    - name: Write smoke report
      ansible.builtin.copy:
        dest: "{{ verify_report_dir }}/smoke-{{ smoke_timestamp }}.md"
        mode: "0644"
        content: |
          # Smoke verification report

          - Target: {{ aap_hostname }}
          - Timestamp: {{ smoke_timestamp }}
          - Checks failed: {{ smoke_failures | length }}

          {% if smoke_failures %}
          ## Failures
          {% for f in smoke_failures %}
          - {{ f }}
          {% endfor %}
          {% else %}
          All checks passed.
          {% endif %}

          RESULT: {{ 'FAIL' if smoke_failures else 'PASS' }}

    - name: Fail when any smoke check failed
      ansible.builtin.assert:
        that: smoke_failures | length == 0
        fail_msg: "Smoke verification failed: {{ smoke_failures }}"
```

- [ ] **Step 2: Syntax check**

Run: `tests/syntax_check.sh verify_smoke.yml`
Expected: `SYNTAX OK: verify_smoke.yml`

- [ ] **Step 3: Commit**

```bash
git add verify_smoke.yml
git commit -m "Add smoke verification playbook"
```

### Task 7: `verify_parity.yml` with fixture mode + offline e2e test

**Files:**
- Create: `verify_parity.yml`
- Create: `tests/fixtures/parity/source_projects.json`, `tests/fixtures/parity/target_projects.json`, `tests/fixtures/parity/source_organizations.json`, `tests/fixtures/parity/target_organizations.json`
- Create: `tests/parity_offline.sh`

**Interfaces:**
- Consumes: `parity_types`, `parity_fail_on`, `parity_max_pages`, `verify_report_dir` from `config/verify.yml`; `normalize_objects`/`parity_diff`/`parity_report` filters; `tasks/paginated_get.yml`.
- Produces: `reports/parity-<ts>.md` and `reports/parity-<ts>.json`. Var `parity_fixture_dir` switches API reads to `<dir>/source_<type>.json` / `<dir>/target_<type>.json` (types without fixture files are skipped in fixture mode).

- [ ] **Step 1: Write `verify_parity.yml`**

```yaml
---
- name: Compare source (RPM) and target (OCP) AAP content
  hosts: localhost
  connection: local
  gather_facts: false

  vars_files:
    - config/verify.yml

  vars:
    source_hostname: >-
      {{ lookup('ansible.builtin.env', 'SOURCE_AAP_HOSTNAME') | regex_replace('/+$', '') }}
    source_username: "{{ lookup('ansible.builtin.env', 'SOURCE_AAP_USERNAME') }}"
    source_password: "{{ lookup('ansible.builtin.env', 'SOURCE_AAP_PASSWORD') }}"
    source_validate_certs: >-
      {{ (lookup('ansible.builtin.env', 'SOURCE_AAP_VALIDATE_CERTS') or 'true') | bool }}
    target_hostname: >-
      {{ lookup('ansible.builtin.env', 'AAP_HOSTNAME') | regex_replace('/+$', '') }}
    target_username: "{{ lookup('ansible.builtin.env', 'AAP_USERNAME') }}"
    target_password: "{{ lookup('ansible.builtin.env', 'AAP_PASSWORD') }}"
    target_validate_certs: >-
      {{ (lookup('ansible.builtin.env', 'AAP_VALIDATE_CERTS') or 'true') | bool }}
    parity_results: {}
    parity_timestamp: "{{ lookup('ansible.builtin.pipe', 'date -u +%Y%m%dT%H%M%SZ') }}"

  pre_tasks:
    - name: Validate required inputs
      ansible.builtin.assert:
        that:
          - parity_fixture_dir is defined or
            (source_hostname | length > 0 and source_username | length > 0
             and source_password | length > 0)
          - parity_fixture_dir is defined or
            (target_hostname | length > 0 and target_username | length > 0
             and target_password | length > 0)
        fail_msg: >-
          Export SOURCE_AAP_HOSTNAME/SOURCE_AAP_USERNAME/SOURCE_AAP_PASSWORD
          (RPM source) and AAP_HOSTNAME/AAP_USERNAME/AAP_PASSWORD (OCP
          target), or set -e parity_fixture_dir=<dir> for offline mode.

  tasks:
    - name: Compare each enabled object type
      ansible.builtin.include_tasks: tasks/parity_type.yml
      loop: "{{ parity_types | dict2items | selectattr('value.enabled', 'defaultattr', true) | list }}"
      loop_control:
        loop_var: parity_item
        label: "{{ parity_item.key }}"

    - name: Ensure report directory exists
      ansible.builtin.file:
        path: "{{ verify_report_dir }}"
        state: directory
        mode: "0755"

    - name: Write parity reports
      ansible.builtin.copy:
        dest: "{{ verify_report_dir }}/parity-{{ parity_timestamp }}.{{ item.ext }}"
        mode: "0644"
        content: "{{ item.content }}"
      loop:
        - ext: json
          content: "{{ parity_results | to_nice_json }}"
        - ext: md
          content: >-
            {{ parity_results | parity_report({'source': source_hostname
               | default('fixtures'), 'target': target_hostname
               | default('fixtures'), 'timestamp': parity_timestamp,
               'fail_on': parity_fail_on}) }}
      loop_control:
        label: "parity-{{ parity_timestamp }}.{{ item.ext }}"

    - name: Fail when parity is broken
      ansible.builtin.assert:
        that: >-
          parity_fail_on != 'missing'
          or (parity_results.values()
              | selectattr('missing_on_target', 'truthy') | list | length == 0
              and parity_results.values()
              | selectattr('field_mismatches', 'truthy') | list | length == 0)
        fail_msg: >-
          Content parity failed; see
          {{ verify_report_dir }}/parity-{{ parity_timestamp }}.md
```

Note: `selectattr('value.enabled', 'defaultattr', true)` is not a real test — implement the loop expression as:
`{{ parity_types | dict2items | rejectattr('value.enabled', 'defined') | list + parity_types | dict2items | selectattr('value.enabled', 'defined') | selectattr('value.enabled') | list }}`
or simpler and preferred: require `enabled` on every entry in `config/verify.yml` (it is set on all) and use
`{{ parity_types | dict2items | selectattr('value.enabled') | list }}`.

- [ ] **Step 2: Write `tasks/parity_type.yml`**

```yaml
---
# Compare one object type. parity_item = {key: type_name, value: spec}
- name: "{{ parity_item.key }}: load fixture rows"
  ansible.builtin.set_fact:
    parity_source_rows: >-
      {{ lookup('ansible.builtin.file', parity_fixture_dir ~ '/source_'
         ~ parity_item.key ~ '.json') | from_json }}
    parity_target_rows: >-
      {{ lookup('ansible.builtin.file', parity_fixture_dir ~ '/target_'
         ~ parity_item.key ~ '.json') | from_json }}
  when:
    - parity_fixture_dir is defined
    - (parity_fixture_dir ~ '/source_' ~ parity_item.key ~ '.json') is file

- name: "{{ parity_item.key }}: skip type without fixtures in fixture mode"
  ansible.builtin.meta: noop
  when: false

- name: "{{ parity_item.key }}: fetch source rows"
  when: parity_fixture_dir is not defined
  block:
    - name: "{{ parity_item.key }}: reset pagination (source)"
      ansible.builtin.set_fact:
        pg_results: []
        pg_next: "{{ parity_item.value.source_path }}"
        pg_pages: 0

    - name: "{{ parity_item.key }}: page through source"
      ansible.builtin.include_tasks: paginated_get.yml
      vars:
        pg_host: "{{ source_hostname }}"
        pg_user: "{{ source_username }}"
        pg_password: "{{ source_password }}"
        pg_validate_certs: "{{ source_validate_certs }}"

    - name: "{{ parity_item.key }}: capture source rows"
      ansible.builtin.set_fact:
        parity_source_rows: "{{ pg_results }}"

    - name: "{{ parity_item.key }}: reset pagination (target)"
      ansible.builtin.set_fact:
        pg_results: []
        pg_next: "{{ parity_item.value.target_path }}"
        pg_pages: 0

    - name: "{{ parity_item.key }}: page through target"
      ansible.builtin.include_tasks: paginated_get.yml
      vars:
        pg_host: "{{ target_hostname }}"
        pg_user: "{{ target_username }}"
        pg_password: "{{ target_password }}"
        pg_validate_certs: "{{ target_validate_certs }}"

    - name: "{{ parity_item.key }}: capture target rows"
      ansible.builtin.set_fact:
        parity_target_rows: "{{ pg_results }}"

- name: "{{ parity_item.key }}: diff"
  ansible.builtin.set_fact:
    parity_results: >-
      {{ parity_results | combine({parity_item.key:
         (parity_source_rows | normalize_objects(parity_item.value.key,
            parity_item.value.fields | default({}),
            parity_item.value.exclude | default({})))
         | parity_diff(parity_target_rows
           | normalize_objects(parity_item.value.key,
             parity_item.value.fields | default({}),
             parity_item.value.exclude | default({})))}) }}
  when: parity_source_rows is defined and parity_target_rows is defined

- name: "{{ parity_item.key }}: clear per-type row facts"
  ansible.builtin.set_fact:
    parity_source_rows: !!null
    parity_target_rows: !!null
```

(Drop the dead `meta: noop` stub — shown here only to flag the skip case; final file must simply guard the diff with `when: parity_source_rows is defined`. In fixture mode, a type without fixture files is silently skipped.)

Clearing facts with `!!null` sets them to None, which fails the `is defined` guard? No — None is defined. Use `parity_source_rows: "{{ omit }}"`? Also stays defined. Correct approach: guard the diff on fixture-mode file existence OR non-fixture mode, and set both row facts unconditionally at the start of each include:

```yaml
- name: "{{ parity_item.key }}: reset row facts"
  ansible.builtin.set_fact:
    parity_source_rows: null
    parity_target_rows: null
```

then guard diff with `when: parity_source_rows is not none` (implementers: use exactly this pattern).

- [ ] **Step 3: Write fixtures**

`tests/fixtures/parity/source_organizations.json`:

```json
[{"name": "Org A"}, {"name": "Org B"}]
```

`tests/fixtures/parity/target_organizations.json`:

```json
[{"name": "Org A"}, {"name": "Org B"}]
```

`tests/fixtures/parity/source_projects.json`:

```json
[
  {"name": "P Kept", "scm_type": "git",
   "scm_url": "https://git.example/kept.git", "scm_branch": "main"},
  {"name": "P Lost", "scm_type": "git",
   "scm_url": "https://git.example/lost.git", "scm_branch": "main"},
  {"name": "P Drift", "scm_type": "git",
   "scm_url": "https://git.example/drift.git", "scm_branch": "main"}
]
```

`tests/fixtures/parity/target_projects.json`:

```json
[
  {"name": "P Kept", "scm_type": "git",
   "scm_url": "https://git.example/kept.git", "scm_branch": "main"},
  {"name": "P Drift", "scm_type": "git",
   "scm_url": "https://git.example/drift.git", "scm_branch": "develop"},
  {"name": "P New", "scm_type": "git",
   "scm_url": "https://git.example/new.git", "scm_branch": "main"}
]
```

- [ ] **Step 4: Write `tests/parity_offline.sh`**

```bash
#!/usr/bin/env bash
# Offline end-to-end test of the parity pipeline using fixtures.
# Expects: run fails (P Lost missing, P Drift branch mismatch), report
# says FAIL, and the second report-only run passes.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf .tmp/parity-reports && mkdir -p .tmp/parity-reports
if ansible-playbook verify_parity.yml \
    -e parity_fixture_dir=tests/fixtures/parity \
    -e verify_report_dir=.tmp/parity-reports; then
  echo "ERROR: expected parity failure" >&2; exit 1
fi
report=$(ls .tmp/parity-reports/parity-*.md)
grep -q 'RESULT: FAIL' "$report"
grep -q 'P Lost' "$report"
grep -q 'P Drift' "$report"
ansible-playbook verify_parity.yml \
  -e parity_fixture_dir=tests/fixtures/parity \
  -e verify_report_dir=.tmp/parity-reports \
  -e parity_fail_on=none
echo "PARITY OFFLINE E2E OK"
```

- [ ] **Step 5: Run the offline e2e until green**

Run: `chmod +x tests/parity_offline.sh && tests/parity_offline.sh`
Expected: first run fails with the parity assert, report contains `RESULT: FAIL`, `P Lost`, `P Drift`; second run (fail_on=none) passes; final line `PARITY OFFLINE E2E OK`.

- [ ] **Step 6: Syntax check + full pytest**

Run: `tests/syntax_check.sh verify_parity.yml && python3 -m pytest tests/ -v`
Expected: syntax OK, all pytest green.

- [ ] **Step 7: Commit**

```bash
git add verify_parity.yml tasks/parity_type.yml tests/fixtures tests/parity_offline.sh
git commit -m "Add content parity verification with offline fixture mode"
```

### Task 8: `verify_functional.yml`

**Files:**
- Create: `verify_functional.yml`
- Create: `tasks/functional_check.yml`
- Create: `tests/functional_offline.sh`

**Interfaces:**
- Consumes: `functional_checks`, `verify_report_dir` from `config/verify.yml`; `AAP_*` env vars; `module_defaults` bridge.
- Produces: `reports/functional-<ts>.md`; rc 0 when all configured checks pass or none configured.

- [ ] **Step 1: Write `verify_functional.yml`**

```yaml
---
- name: Functionally verify migrated content on the AAP 2.5 target
  hosts: localhost
  connection: local
  gather_facts: false

  vars_files:
    - config/verify.yml

  vars:
    aap_hostname: >-
      {{ lookup('ansible.builtin.env', 'AAP_HOSTNAME') | regex_replace('/+$', '') }}
    aap_username: "{{ lookup('ansible.builtin.env', 'AAP_USERNAME') }}"
    aap_password: "{{ lookup('ansible.builtin.env', 'AAP_PASSWORD') }}"
    aap_validate_certs: >-
      {{ (lookup('ansible.builtin.env', 'AAP_VALIDATE_CERTS') or 'true') | bool }}
    functional_failures: []
    functional_passed: []
    functional_timestamp: "{{ lookup('ansible.builtin.pipe', 'date -u +%Y%m%dT%H%M%SZ') }}"

  module_defaults:
    group/ansible.controller.controller:
      controller_host: "{{ aap_hostname }}"
      controller_username: "{{ aap_username }}"
      controller_password: "{{ aap_password }}"
      validate_certs: "{{ aap_validate_certs }}"

  tasks:
    - name: Note when no functional checks are configured
      ansible.builtin.debug:
        msg: >-
          functional_checks is empty; configure per-migration checks in
          config/verify.yml. Writing report and exiting successfully.
      when: functional_checks | length == 0

    - name: Run configured functional checks
      ansible.builtin.include_tasks: tasks/functional_check.yml
      loop: "{{ functional_checks }}"
      loop_control:
        loop_var: check
        label: "{{ check.type }}: {{ check.name }}"
      when: functional_checks | length > 0

    - name: Check enabled schedules have next_run populated
      ansible.builtin.uri:
        url: "{{ aap_hostname }}/api/controller/v2/schedules/?enabled=true&page_size=200"
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: functional_schedules
      when: functional_checks | length > 0

    - name: Record schedules without next_run
      ansible.builtin.set_fact:
        functional_failures: >-
          {{ functional_failures + ['schedule has no next_run: ' ~ item.name] }}
      loop: "{{ (functional_schedules.json.results | default([]))
                | selectattr('next_run', 'none') | list }}"
      loop_control:
        label: "{{ item.name }}"
      when: functional_checks | length > 0

    - name: Ensure report directory exists
      ansible.builtin.file:
        path: "{{ verify_report_dir }}"
        state: directory
        mode: "0755"

    - name: Write functional report
      ansible.builtin.copy:
        dest: "{{ verify_report_dir }}/functional-{{ functional_timestamp }}.md"
        mode: "0644"
        content: |
          # Functional verification report

          - Target: {{ aap_hostname }}
          - Timestamp: {{ functional_timestamp }}
          - Checks configured: {{ functional_checks | length }}
          - Passed: {{ functional_passed | length }}
          - Failed: {{ functional_failures | length }}

          {% if functional_checks | length == 0 %}
          No functional checks configured (config/verify.yml
          functional_checks). Nothing was launched.
          {% endif %}
          {% for p in functional_passed %}
          - PASS: {{ p }}
          {% endfor %}
          {% for f in functional_failures %}
          - FAIL: {{ f }}
          {% endfor %}

          ## Manual checklist (not automatable)

          - [ ] SSO / LDAP login works against the target gateway
          - [ ] Settings reviewed (jobs, system, authentication)
          - [ ] Instance groups / container groups match the intended topology
          - [ ] Execution / hop node topology reviewed (mesh)

          RESULT: {{ 'FAIL' if functional_failures else 'PASS' }}

    - name: Fail when any functional check failed
      ansible.builtin.assert:
        that: functional_failures | length == 0
        fail_msg: "Functional verification failed: {{ functional_failures }}"
```

- [ ] **Step 2: Write `tasks/functional_check.yml`**

```yaml
---
# Run one functional check. check = one functional_checks entry.
- name: "job_template: {{ check.name }}"
  when: check.type == 'job_template'
  block:
    - name: "Launch {{ check.name }}"
      ansible.controller.job_launch:
        name: "{{ check.name }}"
        organization: "{{ check.organization }}"
        job_type: "{{ check.job_type | default('run') }}"
        limit: "{{ check.limit | default(omit) }}"
        extra_vars: "{{ check.extra_vars | default(omit) }}"
        wait: true
        interval: 5
        timeout: "{{ check.timeout | default(600) }}"
      register: functional_job

    - name: "Record job_template success: {{ check.name }}"
      ansible.builtin.set_fact:
        functional_passed: >-
          {{ functional_passed + ['job_template ' ~ check.name
             ~ ' (job id ' ~ functional_job.id | default('n/a') ~ ')'] }}
  rescue:
    - name: "Record job_template failure: {{ check.name }}"
      ansible.builtin.set_fact:
        functional_failures: >-
          {{ functional_failures + ['job_template ' ~ check.name ~ ' failed'] }}

- name: "project_update: {{ check.name }}"
  when: check.type == 'project_update'
  block:
    - name: "Sync {{ check.name }}"
      ansible.controller.project_update:
        project: "{{ check.name }}"
        organization: "{{ check.organization | default(omit) }}"
        wait: true
        timeout: "{{ check.timeout | default(600) }}"
      register: functional_sync

    - name: "Record project_update success: {{ check.name }}"
      ansible.builtin.set_fact:
        functional_passed: "{{ functional_passed + ['project_update ' ~ check.name] }}"
  rescue:
    - name: "Record project_update failure: {{ check.name }}"
      ansible.builtin.set_fact:
        functional_failures: >-
          {{ functional_failures + ['project_update ' ~ check.name ~ ' failed'] }}

- name: "notification_test: {{ check.name }}"
  when: check.type == 'notification_test'
  block:
    - name: "Look up notification template {{ check.name }}"
      ansible.builtin.uri:
        url: >-
          {{ aap_hostname }}/api/controller/v2/notification_templates/?name={{
          check.name | urlencode }}
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: functional_nt

    - name: "Fire test notification for {{ check.name }}"
      ansible.builtin.uri:
        url: >-
          {{ aap_hostname }}/api/controller/v2/notification_templates/{{
          functional_nt.json.results[0].id }}/test/
        method: POST
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        status_code: [202]
        return_content: true
      register: functional_nt_fire

    - name: "Wait for test notification result for {{ check.name }}"
      ansible.builtin.uri:
        url: >-
          {{ aap_hostname }}/api/controller/v2/notifications/{{
          functional_nt_fire.json.id }}/
        url_username: "{{ aap_username }}"
        url_password: "{{ aap_password }}"
        force_basic_auth: true
        validate_certs: "{{ aap_validate_certs }}"
        return_content: true
      register: functional_nt_result
      until: functional_nt_result.json.status in ['successful', 'failed']
      retries: 30
      delay: 2
      failed_when: functional_nt_result.json.status != 'successful'

    - name: "Record notification success: {{ check.name }}"
      ansible.builtin.set_fact:
        functional_passed: "{{ functional_passed + ['notification_test ' ~ check.name] }}"
  rescue:
    - name: "Record notification failure: {{ check.name }}"
      ansible.builtin.set_fact:
        functional_failures: >-
          {{ functional_failures + ['notification_test ' ~ check.name ~ ' failed'] }}

- name: "Unknown check type: {{ check.type }}"
  ansible.builtin.set_fact:
    functional_failures: >-
      {{ functional_failures + ['unknown check type: ' ~ check.type
         ~ ' (' ~ check.name | default('unnamed') ~ ')'] }}
  when: check.type not in ['job_template', 'project_update', 'notification_test']
```

- [ ] **Step 3: Write `tests/functional_offline.sh`**

```bash
#!/usr/bin/env bash
# Offline test: with functional_checks empty the playbook must succeed
# without any network access and write a report.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf .tmp/functional-reports && mkdir -p .tmp/functional-reports
AAP_HOSTNAME=https://unreachable.invalid AAP_USERNAME=x AAP_PASSWORD=x \
ANSIBLE_COLLECTIONS_PATH=.tmp/collections \
ansible-playbook verify_functional.yml -e verify_report_dir=.tmp/functional-reports
report=$(ls .tmp/functional-reports/functional-*.md)
grep -q 'RESULT: PASS' "$report"
grep -q 'No functional checks configured' "$report"
echo "FUNCTIONAL OFFLINE OK"
```

- [ ] **Step 4: Run offline test and syntax check**

Run: `chmod +x tests/functional_offline.sh && tests/syntax_check.sh verify_functional.yml && tests/functional_offline.sh`
Expected: syntax OK; `FUNCTIONAL OFFLINE OK`.

- [ ] **Step 5: Commit**

```bash
git add verify_functional.yml tasks/functional_check.yml tests/functional_offline.sh
git commit -m "Add functional verification playbook"
```

### Task 9: Documentation

**Files:**
- Modify: `README.md` (new "Migration verification" section after section 6)
- Modify: `AGENTS.md` (layout + conventions)

**Interfaces:** none (docs).

- [ ] **Step 1: README section**

Append after "## 6. Post-bootstrap checks" (before "## Security and lifecycle notes"):

```markdown
## 7. Migration verification (RPM -> OpenShift)

Three independent, pipeline-gateable playbooks support verifying an AAP
migration from an RPM environment to AAP 2.5 on OpenShift. Each writes a
Markdown report to `reports/` (gitignored) and exits non-zero on failure.

### Layer 1 - target smoke gate

Run `bootstrap.yml` against the OCP target, then:

```bash
ansible-playbook verify_smoke.yml     # asserts demo objects, sync and history
ansible-playbook teardown.yml         # removes all demo content afterwards
```

This proves gateway auth, RBAC, resource sync, SCM project sync, execution
and job history end-to-end before real content arrives. Job history rows of
deleted demo templates remain in the controller; that is controller
behavior, not an error.

### Layer 2 - content parity

```bash
export SOURCE_AAP_HOSTNAME='https://rpm-controller.example.com'
export SOURCE_AAP_USERNAME='admin'
export SOURCE_AAP_PASSWORD='REDACTED'
ansible-playbook verify_parity.yml
```

Compares organizations, users, teams, credentials (existence), projects,
inventories, hosts, job templates, workflow job templates, schedules,
notification templates, execution environments and labels between the RPM
source (`/api/v2`) and the OCP target (gateway + controller APIs). Object
types and compared fields are configured in `config/verify.yml`
(`parity_types`); `parity_fail_on: none` turns the run report-only. Smart
and constructed inventories are excluded from host comparison. Credential
*secrets* cannot be compared through any API; a migrated `SECRET_KEY` is
proven by Layer 3 instead.

### Layer 3 - functional equivalence

Curate `functional_checks` in `config/verify.yml` (job template launches,
project syncs, notification tests), then:

```bash
ansible-playbook verify_functional.yml
```

A launched job template that uses a migrated credential is the
`SECRET_KEY` decrypt proof: with a wrong key the credential exists but the
job fails at decryption. With no checks configured the playbook writes a
report and exits 0, so it is safe in pipelines before curation. The report
ends with a manual checklist (SSO/LDAP login, settings, instance groups,
mesh topology) for what cannot be automated responsibly.
```

- [ ] **Step 2: AGENTS.md updates**

Add to Layout:

```markdown
- `teardown.yml` — removes everything bootstrap.yml created (reverse order).
- `verify_smoke.yml` / `verify_parity.yml` / `verify_functional.yml` —
  three-layer migration verification (see README section 7); config in
  `config/verify.yml`, shared pagination in `tasks/`, diff logic in
  `filter_plugins/parity.py` (pytest-covered in `tests/`).
```

Add to Conventions:

```markdown
- Verification playbooks are read-only against the source
  (`SOURCE_AAP_*` env vars) and collect all failures before failing once at
  the end. Reports go to `reports/` (gitignored).
- `filter_plugins/parity.py` stays free of Ansible imports so
  `python3 -m pytest tests/` runs without ansible installed.
- Offline test entry points: `tests/syntax_check.sh`,
  `tests/parity_offline.sh`, `tests/functional_offline.sh`,
  `python3 -m pytest tests/`.
```

- [ ] **Step 3: Commit**

```bash
git add README.md AGENTS.md
git commit -m "Document migration verification layers"
```

### Task 10: Full verification and ship

- [ ] **Step 1: Run everything**

```bash
python3 -m pytest tests/ -v
tests/syntax_check.sh
tests/parity_offline.sh
tests/functional_offline.sh
```

Expected: all green.

- [ ] **Step 2: Push and open draft PR** (no attribution footers) summarizing layers, tests run, and the honest caveat that live-AAP acceptance runs were not possible in this environment.

## Self-review notes

- Spec coverage: teardown (T5), smoke (T6), parity incl. fixture mode (T1,2,3,4,7), functional incl. schedules + manual checklist (T8), docs (T9). Prefix parametrization and SSO automation intentionally out (spec YAGNI cuts).
- Type consistency: `normalize_objects(rows, key, fields, exclude)` positional filter usage in `parity_type.yml` matches the Python signature; `parity_report(results, meta)` matches.
- Known implementation flags called out inline: the `selectattr('value.enabled')` loop expression (enabled explicit on every type), and the row-fact reset pattern (`null` + `is not none` guard) in `tasks/parity_type.yml`.
