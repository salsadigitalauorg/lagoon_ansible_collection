# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: last_deploy
short_description: Check the status of the last deployment
description:
    - Checks the status of the last deployment.
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
  wait:
    description:
      - Wait for deployment completion before returning.
    type: bool
    default: False
  delay:
    description:
      - Delay between checking deployment status when retrying.
    type: int
    default: 60
  retries:
    description:
      - Number of times to check for deployment status before returning.
    type: int
    default: 30
'''

EXAMPLES = r'''
- name: Trigger a deployment
  lagoon.api.last_deploy:
    project: test-project
    branch: master
    stagger: 5
    retries: 60
    wait: true
'''
