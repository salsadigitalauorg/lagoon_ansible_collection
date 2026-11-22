#!/usr/bin/python
# -*- coding: utf-8 -*-

from ..module_utils.args import lagoon_argument_spec

DOCUMENTATION = r"""
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
  api_endpoint:
    description:
      - The Lagoon API endpoint.
    type: str
    aliases: [ lagoon_api_endpoint, lagoon_endpoint ]
  api_token:
    description:
      - The Lagoon API token.
    type: str
    aliases: [ lagoon_api_token, lagoon_token ]
  headers:
    description:
      - HTTP request headers.
    type: dict
    default: {}
"""

EXAMPLES = r"""
- name: Trigger a deployment
  lagoon.api.last_deploy:
    project: test-project
    branch: master
    stagger: 5
    retries: 60
    wait: true
"""

RETURN = r"""
deploy_status:
  description: The status of the last deployment, or null if it has never deployed.
  type: str
  returned: always
"""

ARGUMENT_SPEC = lagoon_argument_spec(
    project=dict(type="str", required=True),
    branch=dict(type="str", required=True),
    wait=dict(type="bool", default=False),
    delay=dict(type="int", default=60),
    retries=dict(type="int", default=30),
)
