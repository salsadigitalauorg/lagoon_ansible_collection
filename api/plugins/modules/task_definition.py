#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: task_definition
short_description: Manage custom task definitions.
description:
    - Manages custom advanced task definitions for projects & environments.
    - Please note that at the time of writing, environment-specific tasks are
    - not supported.
options:
  task_type:
    description:
      - The type of the task.
      - Required when state is present.
    type: str
    choices: [ COMMAND, IMAGE ]
  permission:
    description:
      - The permission for the task.
      - Required when state is present.
    type: str
    choices: [ MAINTAINER, DEVELOPER, GUEST ]
  project:
    description:
      - The name of the project.
      - Required when state is present.
    type: str
  name:
    description:
      - Unique name of the task - appears in the 'Name' column in the Tasks
      - listing page in the Lagoon UI.
    required: true
    type: str
  description:
    description:
      - A description of the task - appears in the drop-down for selecting a
      - task to run.
      - Required when state is present.
    type: str
  service:
    description:
      - The deployment in which the task is run (cli/php/nginx...).
      - Required when state is present.
    type: str
  command:
    description:
      - The command to run.
      - Required when state is present and task_type is COMMAND.
    type: str
  image:
    description:
      - The image to run as the task.
      - Required when state is present and task_type is IMAGE.
    type: str
  arguments:
    description:
      - The arguments for the command - these end up being defined as
      - environment variables when the task is run.
    type: list
    elements: dict
    suboptions:
      name:
        description:
          - Name of the argument, e.g, COMMAND_ARGS - when the task is run,
          - $COMMAND_ARGS will be available as an environment variable with the
          - value set by the user.
        required: true
      displayName:
        description:
          - Label of the form field for the argument in the Lagoon UI when
          - running the task.
        required: true
      type:
        description:
          - Type of the argument.
        choices:
          - NUMERIC
          - STRING
          - ENVIRONMENT_SOURCE_NAME
          - ENVIRONMENT_SOURCE_NAME_EXCLUDE_SELF
  state:
    description:
      - Assert the state of the task definition.
      - Set to present to create or update a task definition.
      - Set to absent to remove a task definition.
    type: str
    default: present
    choices: [ absent, present ]
'''

EXAMPLES = r'''
- name: Add task definition.
  lagoon.api.task_definition:
    name: "AUDIT - Run shipshape"
    project: "test-shipshape"
    task_type: COMMAND
    permission: MAINTAINER
    description: Run the shipshape audit
    service: cli
    command: shipshape

- name: Delete task definition.
  lagoon.api.task_definition:
    name: "AUDIT - Run shipshape"
    project: "test-shipshape"
    state: absent
'''
