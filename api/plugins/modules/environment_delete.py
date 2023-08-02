#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: environment_delete
short_description: Delete a project environment
description:
    - Deletes a project environment.
options:
  project:
    description:
      - The project name.
    required: true
    type: str
  branch:
    description:
      - The project branch.
    required: true
    type: str
'''

EXAMPLES = r'''
- name: Remove the Lagoon environment.
  lagoon.api.environment_delete:
    project: test-project
    branch: temp-env
'''
