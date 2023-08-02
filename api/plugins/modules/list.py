#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: list
short_description: List Lagoon resources
description:
    - Returns a list of Lagoon resources of the specified type.
options:
  resource:
    description:
      - The resource type.
    type: str
    default: project
    choices: [ project, environment, task_definition ]
  name:
    description:
      - The resource name.
    type: str
    required: true
'''

EXAMPLES = r'''
- name: List projects.
  lagoon.api.list:
    type: project
  register: projects
- name: List environments.
  lagoon.api.list:
    resource: environment
  register: environments
'''
