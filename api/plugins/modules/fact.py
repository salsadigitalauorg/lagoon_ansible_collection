# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: fact
short_description: Manage facts for an environment.
description:
    - Manages facts for an environment.
options:
  environment_id:
    description:
      - The ID of the environment.
    required: true
    type: int
  name:
    description:
      - The name of the fact.
    required: true
    type: str
  value:
    description:
      - The fact value.
      - Required when state is present.
    type: str
  source:
    description:
      - The source of the fact.
      - Required when state is present.
    type: str
  type:
    description:
      - The type of the fact.
      - Required when state is present.
    type: str
    choices: [ TEXT, SEMVER, URL ]
    required: true
  state:
    description:
      - Message to display to users before shutdown.
    type: str
    default: present
    choices: [ absent, present ]
  description:
    description:
      - A description of the fact.
      - Required when state is present.
    type: str
'''

EXAMPLES = r'''
- name: Add a fact to a Lagoon project
  lagoon.api.fact:
    environment: 1
    name: php_version
    value: 8.1.9
    description: PHP version
    type: SEMVER
    category: fact
    service: php
'''
