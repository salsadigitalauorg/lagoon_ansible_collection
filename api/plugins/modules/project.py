# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: project
short_description: Manage a project
options:
  name:
    description:
      - The project's name.
    required: true
    type: str
  git_url:
    description:
      - Git URL, needs to be SSH Git URL in one of these two formats
      -   - git@172.17.0.1/project1.git
      -   - ssh://git@172.17.0.1:2222/project1.git.
    required: true
    type: str
  subfolder:
    description:
      - Set if the .lagoon.yml should be found in a subfolder.
      - Useful if you have multiple Lagoon projects per Git Repository.
    type: str
  branches:
    description:
      - Which branches should be deployed, can be one of:
      -   - true - all branches are deployed
      -   - false - no branches are deployed
      -   - REGEX - regex of all branches that should be deployed, example: ^(main|staging)$
    type: str
  pullrequests:
    description:
      - Which Pull Requests should be deployed, can be one of:
      -   - true - all pull requests are deployed
      -   - false - no pull requests are deployed
      -   - REGEX - regex of all Pull Request titles that should be deployed, example: [BUILD]
    type: str
  production_environment:
    description:
      - Which environment(the name) should be marked as the production environment.
      - Important: If you change this, you need to deploy both environments
      - (the current and previous one) that are affected in order for the
      - change to propagate correctly.
    type: str
  standby_production_environment:
    description:
      - Which environment(the name) should be marked as the production
      - standby environment.
      - Important: This is used to determine which environment should be marked
      - as the standby production environment
    type: str
  auto_idle:
    description:
      - Should this project have auto idling enabled?
    type: bool
    default: true
  development_environments_limit:
    description:
      - How many environments can be deployed at one time.
    type: int
  problems_ui:
    description:
      - Should the Problems UI be available for this Project?
    type: bool
    default: false
  facts_ui:
    description:
      - Should the Facts UI be available for this Project?
    type: bool
    default: false
  state:
    description:
      - Message to display to users before shutdown.
    type: str
    default: present
    choices: [ absent, present ]
'''

EXAMPLES = r'''
- name: Create a project
  lagoon.api.project:
    state: present
    name: my-test-project
    git_url: https://github.com/org/repo.git
    development_environments_limit: 5
    auto_idle: 1
    production_environment: master
    openshift: 1
'''
