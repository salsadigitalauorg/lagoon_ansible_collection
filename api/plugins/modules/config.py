#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: config
short_description: Manage updates to the .lagoon.yml file.
description:
    - Manage updates to the .lagoon.yml file.
options:
    config_file:
        description:
            - The path to the lagoon config file.
            - Usually .lagoon.yml at the project root.
        required: true
        type: str
    crons:
        description:
            - A dictionary of environment => [cronjobs] to add to the config file.
        type: dict
    routes: (TODO)
        description:
            - A dictionary of environment => [routes] to add to the config file.
        type: dict
    monitoring_urls: (TODO)
        description:
            - A dictionary of environment => [monitoring_urls] to add to the config file.
        type: dict
    state:
        description:
            - Whether the config should exist or not, taking action if the state is different from what is stated.
        type: str
        default: present
        choices: [ absent, present ]
'''

EXAMPLES = r'''
- name: Add a cronjob to a Lagoon project
  lagoon.api.config:
    config_file: /path/to/project/.lagoon.yml
    crons:
      master:
        - name: "Custom cron"
          schedule: "M * * * *"
          command: "echo 'hello world'"

- name: Remove a cronjob from a Lagoon project
  lagoon.api.config:
    config_file: /path/to/project/.lagoon.yml
    crons:
      master:
        - name: "Custom cron"
    state: absent
'''
