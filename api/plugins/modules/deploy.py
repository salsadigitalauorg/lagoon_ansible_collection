# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: deploy
short_description: Deploy a project's branch
description:
    - Deploys a project's branch.
options:
  project:
    description:
      - The project name.
    required: true
    type: str
  branch:
    description:
      - The project branch to deploy.
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
  lagoon.api.deploy:
    project: test-project
    branch: master
    stagger: 5
    retries: 60
    wait: true
'''
