#!/usr/bin/python
# -*- coding: utf-8 -*-

from ..module_utils.args import lagoon_argument_spec

DOCUMENTATION = r"""
module: project_update
short_description: Update the values for a project
description:
    - Updates the values for a project.
options:
  project:
    description:
      - The project's name.
    required: true
    type: str
  values:
    description:
      - The project values to patch.
    required: true
    type: dict
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
- name: Update project environment limit.
  lagoon.api.project_update:
    project: test-project
    values:
        developmentEnvironmentsLimit: 10
"""

RETURN = r"""
update:
  description: The project after the update, or its current state if no update was needed.
  type: dict
  returned: always
changed:
  description: Whether the project was updated.
  type: bool
  returned: always
"""

ARGUMENT_SPEC = lagoon_argument_spec(
    project=dict(type="str", required=True),
    values=dict(type="dict", required=True),
)
