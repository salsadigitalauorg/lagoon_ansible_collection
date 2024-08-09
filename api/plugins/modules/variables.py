#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: variables
description: Get variables for a project or environment.
short_description: Get variables for a project or environment.
options:
  type:
    description:
      - The resource type.
    default: project
    type: str
    choices: [ project, environment ]
  name:
    description:
      - The project name or enviroment namespace.
    type: str
    required: true
'''

EXAMPLES = r'''
- name: Fetch environment vars.
  lagoon.api.variables:
    type: environment
    name: '{{ environment_ns }}'
  register: environment_vars_res

- name: Fetch project vars.
  lagoon.api.variables:
    type: project
    name: '{{ project_name }}'
  register: project_vars_res
'''
