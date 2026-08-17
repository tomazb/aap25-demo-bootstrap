#!/usr/bin/python
# OFFLINE TEST STUB — not a real controller export module.
# Returns deterministic, non-secret assets and checks the gateway prefix.
import json
import os

from ansible.module_utils.basic import AnsibleModule


ASSETS = {
    "organizations": [
        {
            "name": "Demo Linux",
            "description": "offline object-transfer fixture",
        }
    ],
    "inventories": [
        {
            "name": "Demo Linux Inventory",
            "organization": {
                "name": "Demo Linux",
                "type": "organization",
            },
        }
    ],
    "job_templates": [
        {
            "name": "Demo 01 - Linux hello",
            "organization": {
                "name": "Demo Linux",
                "type": "organization",
            },
        }
    ],
}


def main():
    module = AnsibleModule(
        argument_spec=dict(
            all=dict(type="bool", default=False),
            controller_host=dict(type="str"),
            controller_username=dict(type="str"),
            controller_password=dict(type="str", no_log=True),
            controller_oauthtoken=dict(type="str", no_log=True),
            validate_certs=dict(type="bool"),
            request_timeout=dict(type="raw"),
        ),
        supports_check_mode=True,
    )

    prefix = os.environ.get("CONTROLLER_OPTIONAL_API_URLPATTERN_PREFIX")
    if prefix != "/api/controller/":
        module.fail_json(msg="stub expected /api/controller/ gateway prefix")

    expected_host = os.environ.get("STUB_EXPECT_CONTROLLER_HOST")
    if expected_host and module.params.get("controller_host") != expected_host:
        module.fail_json(msg="stub received an unexpected controller_host")

    marker = os.environ.get("STUB_EXPORT_MARKER")
    if marker:
        with open(marker, "w", encoding="utf-8") as stream:
            json.dump(
                {
                    "all": module.params.get("all"),
                    "controller_host": module.params.get("controller_host"),
                    "prefix": prefix,
                },
                stream,
                sort_keys=True,
            )

    module.exit_json(changed=False, assets=ASSETS)


if __name__ == "__main__":
    main()
