#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: info
short_description: Fetches Lagoon resource information
description:
    - Fetches information for a Lagoon resource.
options:
  resource:
    description:
      - The resource type.
    type: str
    default: environment
    choices: [ project, environment ]
  name:
    description:
      - The resource name.
    type: str
    required: true
'''

EXAMPLES = r'''
- name: Get a project.
  lagoon.api.info:
    resource: project
    name: test
  register: project_info
- name: Get an environment.
  lagoon.api.info:
    resource: environment
    name: test-environment
  register: env_info
'''
