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
    choices: [ environment ]
  name:
    description:
      - The resource name.
    type: str
    required: true
'''

EXAMPLES = r'''
- name: Get an environment.
  lagoon.api.info:
    resource: environment
    name: test-environment
  register: env_info
'''
