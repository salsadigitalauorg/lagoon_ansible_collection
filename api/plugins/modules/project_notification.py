#!/usr/bin/python
# -*- coding: utf-8 -*-

from ..module_utils.args import lagoon_argument_spec

DOCUMENTATION = r"""
module: project_notification
short_description: Attach or detach a notification from a project
description:
    - Attaches or detaches a notification from a project.
options:
  project:
    description:
      - The project's name.
    required: true
    type: str
  notification:
    description:
      - The notification's name.
    required: true
    type: str
  type:
    description:
      - The notification type.
    type: str
    default: SLACK
    choices: [ SLACK, ROCKETCHAT, MICROSOFTTEAMS, EMAIL, WEBHOOK ]
  state:
    description:
      - Whether the notification should be attached or detached.
    type: str
    default: present
    choices: [ absent, present ]
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
- name: Add a Slack notification to a project
  lagoon.api.project_notification:
    project: test-project
    notification: my-slack-channel

- name: Remove a notification from a project
  lagoon.api.project_notification:
    project: test-project
    notification: my-slack-channel
    state: absent
"""

RETURN = r"""
changed:
  description: Whether the notification was attached or detached.
  type: bool
  returned: always
"""

ARGUMENT_SPEC = lagoon_argument_spec(
    project=dict(type="str", required=True),
    notification=dict(type="str", required=True),
    type=dict(
        type="str",
        default="SLACK",
        choices=["SLACK", "ROCKETCHAT", "MICROSOFTTEAMS", "EMAIL", "WEBHOOK"],
    ),
    state=dict(type="str", default="present", choices=["present", "absent"]),
)
