#!/usr/bin/python
# OFFLINE TEST STUB — not a real controller import module.
# Captures only deterministic fixture assets and checks the gateway prefix.
import json
import os

from ansible.module_utils.basic import AnsibleModule


def main():
    module = AnsibleModule(
        argument_spec=dict(
            assets=dict(type="dict", required=True),
            controller_host=dict(type="str"),
            controller_username=dict(type="str"),
            controller_password=dict(type="str", no_log=True),
            controller_oauthtoken=dict(type="str", no_log=True),
            validate_certs=dict(type="bool"),
            request_timeout=dict(type="raw"),
        ),
        supports_check_mode=False,
    )

    prefix = os.environ.get("CONTROLLER_OPTIONAL_API_URLPATTERN_PREFIX")
    if prefix != "/api/controller/":
        module.fail_json(msg="stub expected /api/controller/ gateway prefix")

    expected_host = os.environ.get("STUB_EXPECT_CONTROLLER_HOST")
    if expected_host and module.params.get("controller_host") != expected_host:
        module.fail_json(msg="stub received an unexpected controller_host")

    capture = os.environ.get("STUB_IMPORT_CAPTURE")
    if not capture:
        module.fail_json(msg="STUB_IMPORT_CAPTURE is required by the offline stub")

    with open(capture, "w", encoding="utf-8") as stream:
        json.dump(module.params["assets"], stream, sort_keys=True)

    module.exit_json(changed=True)


if __name__ == "__main__":
    main()
