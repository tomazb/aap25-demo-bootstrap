# Runtimes and control-node prerequisites

The [README quickstart](../README.md#quickstart) runs the playbooks with
host-native `ansible-playbook` / `ansible-vault`. This page covers the
control-node requirements behind that path and the alternative
**execution-environment** runtime (run everything inside an AAP 2.5 image with
`ansible-navigator`).

## Control-node prerequisites

ansible-core 2.16 — the AAP 2.5 tooling line — requires Python 3.10–3.12 on the
control node.

### RHEL 8

Stock RHEL 8 `python3` is 3.6, which cannot run ansible-core 2.16. Either:

- install a newer application stream and use it for ansible-core and the
  collections:

  ```bash
  sudo dnf install python3.12
  python3.12 -m pip install --user ansible-core==2.16.14
  ```

- or install `ansible-navigator` on a supported host Python and run the
  playbooks from an AAP execution environment (see below). This route also
  requires Podman or Docker, registry authentication, and a pullable AAP 2.5
  image.

## Collections and version pins

Install the certified collections, using the versions provided by your AAP 2.5
private automation hub whenever possible:

```bash
ansible-galaxy collection install -r requirements.yml
ansible-galaxy collection list | grep -E 'ansible\.(platform|controller)'
```

Expected version families are `ansible.platform 2.5.x` and
`ansible.controller 4.6.x`. Do not silently install 2.6/2.7 collection families
against AAP 2.5.

`requirements.yml` requires `ansible.platform >= 2.5.20250702`: earlier 2.5 GA
builds lack the `object_ids` name-lookup parameter on `role_user_assignment`
that the user role assignments depend on. If your private automation hub only
mirrors an older 2.5 build, sync a newer one before running the bootstrap.

## Execution-environment runtime (ansible-navigator)

Instead of installing ansible-core on the control node, you can run every
playbook inside a pullable AAP 2.5 execution-environment image. Install the
collections into the playbook-adjacent `collections/` directory (gitignored;
Navigator mounts the project directory and Ansible discovers collections
there):

```bash
export AAP_EE_IMAGE='<pullable-AAP-2.5-EE-image>'
ansible-navigator exec --eei "$AAP_EE_IMAGE" -- \
  ansible-galaxy collection install -r requirements.yml -p ./collections
ansible-navigator exec --eei "$AAP_EE_IMAGE" -- \
  ansible-galaxy collection list -p ./collections
```

Define `aap_run` / `aap_vault` wrappers so the quickstart commands work
unchanged inside the image. Re-define them after opening a new shell:

```bash
aap_run() {
  local playbook=$1 name
  local -a pass_env=()
  shift
  for name in \
    AAP_HOSTNAME AAP_USERNAME AAP_PASSWORD AAP_VALIDATE_CERTS \
    SOURCE_AAP_HOSTNAME SOURCE_AAP_USERNAME SOURCE_AAP_PASSWORD \
    SOURCE_AAP_VALIDATE_CERTS RBAC_DEMO_PASSWORD
  do
    [[ -v $name ]] && pass_env+=(--penv "$name")
  done
  ansible-navigator run "$playbook" --mode stdout --enable-prompts \
    --eei "$AAP_EE_IMAGE" "${pass_env[@]}" -- "$@"
}
aap_vault() {
  ansible-navigator exec --exshell false --eei "$AAP_EE_IMAGE" -- \
    ansible-vault "$@"
}
```

Then substitute `aap_run` for `ansible-playbook` and `aap_vault` for
`ansible-vault` in every quickstart command. The wrapper passes only the
environment variables that exist, and `--enable-prompts` allows the Vault
password prompt. The project directory (including `config/secrets.yml`) is
mounted into the container.

## Private certificate authority

For a private CA, install the CA trust on the control node rather than disabling
certificate validation. When using an execution environment, the CA must also be
trusted inside the selected image or mounted into it with navigator
configuration.
