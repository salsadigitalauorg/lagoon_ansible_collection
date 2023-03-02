# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: env_variable
short_description: Manage variables for a project or environment
description:
    - Manages variables for a project or environment.
options:
  name:
    description:
      - The name of the variable.
    required: true
    type: str
  type:
    description:
      - The resource for the variable (project or environment).
    required: true
    type: str
    choices: [ PROJECT, ENVIRONMENT ]
  type_name:
    description:
      - The name of the resource for the variable.
      - Name of the project or environment.
    required: true
    type: str
  state:
    description:
      - Message to display to users before shutdown.
    type: str
    default: present
    choices: [ absent, present ]
  value:
    description:
      - The variable value.
      - Required when state is present.
    type: str
  scope:
    description:
      - The variable scope.
      - Required when state is present.
    type: str
    choices: [ BUILD, RUNTIME, GLOBAL, CONTAINER_REGISTRY, INTERNAL_CONTAINER_REGISTRY ]
  replace_existing:
    description:
      - Specify whether to replace existing values.
      - When this is true, an existing value for the variable will be deleted
      - and recreated with the value specified.
    type: bool
    default: False
'''

EXAMPLES = r'''
- name: Update Lagoon variable definition
  lagoon.api.env_variable:
    state: present
    type: ENVIRONMENT
    type_name: test-environment-master
    name: foo
    value: bar
    replace_existing: true
    scope: RUNTIME
'''
