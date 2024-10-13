#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: lagoon.api.cmdb_diff
short_description: Compare local and remote Lagoon configuration states
description:
  - This module compares local configuration states (head) against the remote states tracked in Lagoon (base).
  - It helps maintain configuration integrity by detecting discrepancies and suggesting necessary updates or removals.
  - The module supports 'strict' and 'key' comparison modes to allow for detailed or general comparisons as needed.
options:
  head:
    description:
      - A list representing the expected local state of configuration variables.
    required: true
    type: list
    elements: dict
  base:
    description:
      - A list representing the remote state of configuration variables as tracked in Lagoon.
    required: true
    type: list
    elements: dict
  ignore:
    description:
      - A list of variable names to ignore during the comparison, preventing unnecessary updates.
    required: false
    type: list
    elements: str
  mode:
    description:
      - Specifies the mode of comparison. Options are 'strict' for complete equality checks, or 'key' for targeted attribute comparisons.
    required: false
    type: str
    choices: ['strict', 'key']
  keys:
    description:
      - Required when mode is 'key'. A list of keys to focus the comparison on, improving specificity and relevance of the diff output.
    required: false
    type: list
    elements: str
'''

EXAMPLES = r'''
# Example of using lagoon.api.cmdb_diff in strict mode to ensure complete configuration alignment
- name: Ensure complete parity between local and Lagoon configurations
  lagoon.api.cmdb_diff:
    head: "{{ local_config }}"
    base: "{{ remote_config }}"
    mode: "strict"

# Example of using lagoon.api.cmdb_diff in key mode to focus on specific configuration attributes
- name: Compare specific attributes in local and Lagoon configurations
  lagoon.api.cmdb_diff:
    head: "{{ local_config }}"
    base: "{{ remote_config }}"
    mode: "key"
    keys: ["name", "value"]
'''