#!/usr/bin/python

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
---
module: deploy_target_config

short_description: Manage deploy target configs for a project.

version_added: "1.0.1"

description:
    - Allows creating, updating, replacing and deleting deploy target configs.

options:
    project:
        description: The name of the project.
        required: true
        type: str
    configs:
        description:
            - List of config values.
        required: false
        type: list
        elements: dict
    state:
        description:
        - Determines if the configs should be created, updated, or deleted. When set to C(present), the configs will be
        created, if they do not already exist. If set to C(absent), existing configs will be deleted. If set to
        C(present), existing configs will be updated, if its attributes differ from those specified using
        I(configs). If I(replace) is C(true), existing values are deleted and new values are created for the provided
        configs.
        type: str
        default: present
        choices: [ absent, present ]
    replace:
        description:
        - If set to C(true), and I(state) is C(present), existing configs will be deleted and new ones created.
        type: bool
        default: False

extends_documentation_fragment:
  - lagoon.api.auth_options

author:
    - Yusuf Hasan Miyan (@yusufhm)

seealso:
    # TODO: Update to official link from docs when available.
    - name: Lagoon deploy target configs docs
      link: https://github.com/uselagoon/lagoon/blob/main/docs/using-lagoon-advanced/deploytarget_configs.md
'''

EXAMPLES = r'''
- name: Add Lagoon deploy target configs.
  lagoon.api.deploy_target_config:
    project: '{{ project.name }}'
    configs:
      - branches: 'master'
        pullrequests: 'false'
        deployTarget: 1
        weight: 1
      - branches: '^feature/|^(dev|test|develop)$'
        pullrequests: 'true'
        deployTarget: 2
        weight: 1

- name: Delete Lagoon deploy target configs.
  lagoon.api.deploy_target_config:
    project: '{{ project.name }}'
    state: absent

- name: Replace Lagoon deploy target configs (delete & recreate).
  lagoon.api.deploy_target_config:
    project: '{{ project.name }}'
    configs:
      - branches: 'master'
        pullrequests: 'false'
        deployTarget: 1
        weight: 1
      - branches: '^feature/|^(dev|test|develop)$'
        pullrequests: 'true'
        deployTarget: 2
        weight: 1
    replace: true
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient

def run_module():
    module_args = dict(
        lagoon_api_endpoint=dict(type='str', required=True),
        lagoon_api_token=dict(type='str', required=True, no_log=True),
        headers=dict(type='dict', required=False, default={}),
        project=dict(type='str', required=True),
        configs=dict(type='list', elements='dict', required=False, default=[]),
        state=dict(type='str', required=False, default='present'),
        replace=dict(type='bool', required=False, default=False),
    )

    result = dict(changed=False, result={})

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    if module.check_mode:
        module.exit_json(**result)

    lagoon = ApiClient(
        module.params['lagoon_api_endpoint'],
        module.params['lagoon_api_token'],
        {'headers': module.params['headers']}
    )

    project = lagoon.project(module.params['project'])
    existing_configs = project['deployTargetConfigs']

    if module.params['state'] == 'present':
        add_or_update(lagoon, project, module.params['replace'],
                           existing_configs, module.params['configs'], result)
    elif module.params['state'] == 'absent':
        delete_existing(lagoon, project, existing_configs, result)

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    # result['original_message'] = module.params['name']
    # result['message'] = 'goodbye'

    # use whatever logic you need to determine whether or not this module
    # made any modifications to your target
    # if module.params['new']:
    #     result['changed'] = True

    # during the execution of the module, if there is an exception or a
    # conditional state that effectively causes a failure, run
    # AnsibleModule.fail_json() to pass in the message and the result
    # if module.params['name'] == 'fail me':
    #     module.fail_json(msg='You requested this to fail', **result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)

def add_or_update(lagoon, project, replace, existing_configs, desired_configs, result):
    if not existing_configs:
        updates_required = desired_configs
    elif not replace:
        updates_required = determine_required_updates(
            existing_configs, desired_configs)
    elif replace:
        delete_ids = [ec['id'] for ec in existing_configs]
        lagoon.deploy_target_config_delete(project['id'], delete_ids)
        updates_required = desired_configs

    if not updates_required:
        result['result'] = project['deployTargetConfigs']
        return

    result['result'] = lagoon.deploy_target_config_add(
        project['id'], updates_required)
    result['changed'] = True

def delete_existing(lagoon, project, existing_configs, result):
    if not existing_configs:
        return
    else:
        delete_ids = [ec['id'] for ec in existing_configs]
        result['result'] = lagoon.deploy_target_config_delete(
            project['id'], delete_ids)
        result['changed'] = True

def determine_required_updates(existing_configs, desired_configs):
    updates_required = []
    for config in desired_configs:
        found = False
        uptodate = True
        for existing_config in existing_configs:
            if existing_config['branches'] != config['branches']:
                continue
            else:
                found = True

            if (existing_config['pullrequests'] != config['pullrequests'] or
                    str(existing_config['deployTarget']['id']) != str(config['deployTarget']) or
                    str(existing_config['weight']) != str(config['weight'])):
                uptodate = False
                break

            if found:
                break

        if not found or not uptodate:
            updates_required.append(config)

    return updates_required

def main():
    run_module()

if __name__ == '__main__':
    main()
