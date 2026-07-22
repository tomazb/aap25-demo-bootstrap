#!/usr/bin/python
# OFFLINE TEST STUB — not a real module. Records a sanitized invocation marker
# and returns deterministic results so customer functional checks can be tested
# without contacting a real controller. Never writes secrets or extra_vars.
import os
from ansible.module_utils.basic import AnsibleModule


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type='str'),
            organization=dict(type='str'),
            project=dict(type='str'),
            inventory=dict(type='str'),
            limit=dict(type='str'),
            extra_vars=dict(type='dict', no_log=True),
            wait=dict(type='bool'),
            interval=dict(type='int'),
            timeout=dict(type='raw'),
            job_type=dict(type='str'),
            controller_host=dict(type='str'),
            controller_username=dict(type='str'),
            controller_password=dict(type='str', no_log=True),
            validate_certs=dict(type='bool'),
            request_timeout=dict(type='raw'),
        ),
        supports_check_mode=True,
    )
    modname = os.path.splitext(os.path.basename(__file__))[0]
    p = module.params
    # The target is the first non-empty identifying field across module types.
    target = p.get('name') or p.get('project') or p.get('inventory') or ''
    limit = p.get('limit')
    marker = os.environ.get('STUB_MARKER')
    if marker:
        # Only module, target and limit — never credentials or extra_vars.
        with open(marker, 'a') as fh:
            fh.write('%s target=%s limit=%s\n' % (modname, target, limit))
    fail_names = [n for n in os.environ.get('STUB_FAIL_NAMES', '').split(',') if n]
    if target in fail_names:
        module.fail_json(msg='stub failure for %s' % target)
    module.exit_json(changed=True, id=777,
                     status=os.environ.get('STUB_STATUS', 'successful'))


if __name__ == '__main__':
    main()
