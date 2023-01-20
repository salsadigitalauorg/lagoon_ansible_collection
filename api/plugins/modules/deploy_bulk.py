#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: deploy_bulk
short_description: Start a Lagoon bulk deployment
description:
    - Starts a Lagoon bulk deployment.
options:
  build_vars:
    description:
      - List of build-time variables to set during the deployment.
    type: list
    elements: dict
    default: []
  name:
    description:
      - The bulk deployment name.
    type: str
    default: ""
  environments:
    description:
      - List of environments to deploy.
    type: list
    elements: dict
    required: true
'''

EXAMPLES = r'''
- name: Bulk deployment trigger by environment id.
  lagoon.api.deploy_bulk:
    name: Trigger by Ansible
    environments:
      - id: environment_id
    build_vars:
      - name: build_var_name
        value: build_var_value

- name: Bulk deployment trigger by project & env name.
  lagoon.api.deploy_bulk:
    name: Trigger by Ansible
    environments:
      - name: environment_name
        project:
          name: project_name
    build_vars:
      - name: build_var_name
        value: build_var_value
'''
