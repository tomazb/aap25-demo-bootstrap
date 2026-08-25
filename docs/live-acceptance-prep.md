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
