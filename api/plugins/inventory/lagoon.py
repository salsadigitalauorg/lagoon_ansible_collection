from __future__ import absolute_import, division, print_function
from ansible.utils.display import Display
import re
import ast
import json
from ansible.errors import AnsibleError
from ansible.plugins import inventory
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient

__metaclass__ = type

DOCUMENTATION = """
    name: lagoon
    plugin_type: inventory
    options:
      plugin:
         description: token that ensures this is a source file for the 'k8s' plugin.
         required: True
         choices: ['lagoon.api.lagoon', 'lagoon']
      lagoons:
          description:
          - Optional list of Lagoon connection settings and project information
          suboptions:
            name:
                description:
                - Name for this Lagoon endpoint
            lagoon_api_endpoint:
            lagoon_api_token:
            fields:
            environments:
            environment_fields:
            groups:
                description:
                - List of groups to filter projects by
    requirements:
    - "python >= 3"
    - "PyYAML >= 3.11"
"""

EXAMPLES = """
# File must be named lagoon.yaml or lagoon.yml

# Fetch all projects and environments from a specific Lagoon
plugin: lagoon.api.lagoon
connections:
  - lagoon_api_endpoint: ''
    lagoon_api_token: ''
"""

display = Display()

class InventoryModule(BaseInventoryPlugin):
    NAME = 'lagoon.api.lagoon'

    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)
        config = self._read_config_data(path)
        self.fetch_objects(self.get_option('lagoons'))

    def fetch_objects(self, lagoons):

        if lagoons:
            if not isinstance(lagoons, list):
                raise AnsibleError (
                    "Expecting lagoons to be a list."
                )

            for lagoon in lagoons:

                if 'transport' not in lagoon:
                    lagoon['transport'] = 'ssh'
                elif lagoon['transport'] != 'ssh':
                    # @TODO kubectl support.
                    raise AnsibleError(
                        "Only ssh transport is supported."
                    )

                # Set default connections details to public Lagoon.
                if 'ssh_host' not in lagoon:
                    lagoon['ssh_host'] = ''
                if 'ssh_port' not in lagoon:
                    lagoon['ssh_port'] = ''

                if not isinstance(lagoon, dict):
                    raise AnsibleError(
                        "Expection lagoon to be a dictionary."
                    )

                if not {'lagoon_api_endpoint', 'lagoon_api_token'} <= set(lagoon):
                    raise AnsibleError(
                        "Expecting lagoon_api_endpoint and lagoon_api_token."
                    )

                lagoon_api = ApiClient(
                    lagoon['lagoon_api_endpoint'],
                    lagoon['lagoon_api_token'],
                    {
                        'headers': lagoon['headers'] if 'headers' in lagoon else {}
                    }
                )

                project_list = []
                seen = []

                if 'groups' in lagoon:
                    for group in lagoon['groups']:
                        for project in lagoon_api.projects_in_group(group):
                            if project['name'] not in seen:
                                project_list.append(project)
                                seen.append(project['name'])

                else:
                    project_list = lagoon_api.projects_all()

                for project in project_list:
                    project_group = re.sub(r'[\W-]+', '_', project['name'])
                    self.inventory.add_group(project_group)

                    project['variables'] = lagoon_api.project_get_variables(
                        project['name']
                    )

                    # Secondary lookup as group queries validate permissions
                    # on each trip and results in query timeouts if these
                    # were returned with the project list.
                    project['groups'] = lagoon_api.project_get_groups(project['name'])

                    for environment in project['environments']:
                        try:
                            environment['variables'] = lagoon_api.environment_get_variables(
                                "%s-%s" % (project['name'], environment['name'])
                            )
                        except:
                            environment['variables'] = []

                        self.add_environment(project, environment, lagoon)

    # Add the environment to the inventory set.
    def add_environment(self, project, environment, lagoon):
        project_group = re.sub(r'[\W-]+', '_', project['name'])
        namespace = "%s-%s" % (project['name'], environment['name'])

        self.inventory.add_group(environment['name'])
        self.inventory.add_child(project_group, environment['name'])

        self.inventory.add_host(namespace)
        self.inventory.add_child(environment['name'], namespace)

        # Add hostvars
        self.inventory.set_variable(
            namespace, 'name', namespace
        )
        self.inventory.set_variable(
            namespace, 'project_id', project['id']
        )
        self.inventory.set_variable(
            namespace, 'project_name', project['name']
        )
        self.inventory.set_variable(
            namespace, 'environment_id', environment['id']
        )
        self.inventory.set_variable(
            namespace, 'environment_name', environment['name']
        )
        self.inventory.set_variable(
            namespace, 'lagoon_groups', project['groups']
        )

        # Transport details for Ansible to use to connect to the
        # remote host.
        # @TODO: Support kubectl as a transport mode.
        self.inventory.set_variable(
            namespace, 'ansible_user', namespace
        )
        self.inventory.set_variable(
            namespace, 'ansible_ssh_user', namespace
        )
        self.inventory.set_variable(
            namespace, 'ansible_host', lagoon['ssh_host'])

        self.inventory.set_variable(
            namespace, 'ansible_port', lagoon['ssh_port']
        )
        self.inventory.set_variable(
            namespace, 'ansible_connection', lagoon['transport']
        )

        self.inventory.set_variable(
            namespace,
            'ansible_ssh_common_args',
            '-T -o "UserKnownHostsFile=/dev/null" -o "StrictHostKeyChecking=no"'
        )

        # Unpack metadata.
        if 'metadata' in project:
            lagoon_meta = json.loads(project['metadata'])
            inventory_meta = {}

            for key, value in lagoon_meta.items():
                try:
                    value = ast.literal_eval(value)
                except Exception as e:  # noqa F841
                    pass

                inventory_meta[key] = value

            self.inventory.set_variable(namespace, 'metadata', inventory_meta)
