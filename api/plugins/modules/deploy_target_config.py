# -*- coding: utf-8 -*-

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
