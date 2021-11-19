#!/usr/bin/python

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
---
module: environment

short_description: Manage a project's environments.

version_added: "1.0.1"

description:
    - Allows creating, updating, replacing and deleting environments.

options:
    project:
        description: The name of the project.
        required: true
        type: str
    environment:
        description: The name of the environment.
        required: true
        type: str
    definition: (TODO)
        description: Values for the environment creation, as a dict.
        type: dict
        suboptions:
            deployBaseRef:
                type: str
                description: The version control base ref for deployments (e.g., branch name, tag, or commit id).
            deployHeadRef:
                type: str
                description: The version control head ref for deployments (e.g., branch name, tag, or commit id).
            deployType:
                type: str
                description: Which Deployment Type this environment is, can be BRANCH, PULLREQUEST, PROMOTE.
                choices: [ BRANCH, PULLREQUEST, PROMOTE ]
            environmentType:
                type: str
                description: Which Environment Type this environment is, can be PRODUCTION, DEVELOPMENT.
                choices: [ PRODUCTION, DEVELOPMENT ]
            kubernetes:
                type: int
                description: Target cluster for this environment.
                aliases:
                    - openshift
            kubernetesNamespaceName:
                type: str
                description: Name of the Kubernetes Namespace this environment is deployed into.
                aliases:
                    - openshiftProjectName

    state:
        description:
        - Determines if the environment should be created, updated, or deleted. When set to C(present), the environment will be
        created, if it does not already exist. If set to C(absent), an existing environment will be deleted. If set to
        C(present), an existing environment will be updated, if its attributes differ from those specified using
        I(definition).
        type: str
        default: present
        choices: [ absent, present ]

extends_documentation_fragment:
  - lagoon.api.auth_options

author:
    - Yusuf Hasan Miyan (@yusufhm)

'''

EXAMPLES = r'''
- name: Delete Lagoon environment.
  lagoon.api.environment:
    project: 'foobar'
    environment: 'feature/baz'
    state: absent
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient

def run_module():
    module_args = dict(
        lagoon_api_endpoint=dict(type='str', required=True),
        lagoon_api_token=dict(type='str', required=True, no_log=True),
        headers=dict(type='dict', required=False, default={}),
        project=dict(type='str', required=True),
        environment=dict(type='str', required=True),
        state=dict(type='str', required=False, default='present'),
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

    if module.params['state'] == 'absent':
        res = lagoon.environment_delete(
            module.params['project'], module.params['environment'])
        if 'errors' in res:
            if res['errors'][0]['message'] == 'Branch environment does not exist, no need to remove anything.':
                module.exit_json(**result)
            module.fail_json(msg=res['errors'][0]['message'], **result)
        result['result'] = res['data']['deleteEnvironment']
        result['changed'] = True

    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()
