#!/usr/bin/env python3
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: lagoon_log
description: Add a log message to Lagoon logs.
short_description: Add a log message to Lagoon logs.
options:
  server:
    description:
      - The address of Lagoon Logs server.
    default: application-logs.lagoon.svc
    type: str
  port:
    description:
      - The port of Lagoon Logs server.
    default: 5140
    type: int
  message:
    description:
      - The log message.
    type: str
    required: true
  level:
    description:
      - The level of the log message.
    default: info
    type: str
    choices: [ info, warning, error, debug, critical ]
  host:
    description:
      - The hostname where the log message belongs to.
    type: str
    required: false
  namespace:
    description:
      - The valid namespace where the log message belongs to.
      - Required when context or extra data is provided.
    type: str
    required: false
  context:
    description:
      - Context data send along the log message.
    type: dict
    required: false
  extra:
    description:
      - Extra data send along the log message.
    type: dict
    required: false
'''

EXAMPLES = r'''
- name: Add Lagoon log message.
  lagoon.api.lagoon_log:
    message: 'A test log message'
    
- name: Add Lagoon log error.
  lagoon.api.lagoon_log:
    level: error
    message: 'A test error message'
    namespace: "{{ project_name }}"
    host: "{{ inventory_hostname }}"
    context: 
      name: "{{ inventory_hostname }}"
    extra:
      project: "{{ project_name }}"
      gitlab: "{{ gitlab_id }}"
'''
