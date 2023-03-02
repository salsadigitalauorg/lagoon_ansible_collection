# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: environment_update
short_description: Update a project environment's values
description:
    - Updates a project environment's values.
options:
  environment:
    description:
      - The project environment name.
      - Required if environment_id not provided.
    type: str
  environment_id:
    description:
      - The project environment ID.
      - Required if environment not provided.
    type: int
  values:
    description:
      - The environment values.
    type: dict
    default: None
'''

EXAMPLES = r'''
- name: Set environment deployment cluster.
  lagoon.api.environment_update:
    environment: test-project-master
    values:
      kubernetes: 10
'''
