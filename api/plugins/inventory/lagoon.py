from __future__ import absolute_import, division, print_function
from ansible.utils.display import Display
import re
import ast
import json
from ansible.errors import AnsibleError, AnsibleParserError
from ansible.module_utils._text import to_native
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient
from ansible_collections.lagoon.api.plugins.module_utils.create_token import CreateToken

__metaclass__ = type

DOCUMENTATION = """
    name: lagoon
    plugin_type: inventory
    extends_documentation_fragment:
        - constructed
    options:
      plugin:
         description: token that ensures this is a source file for the 'lagoon' plugin.
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
                description:
                - The lagoon API endpoint
            headers:
              description: HTTP request headers
              type: dictionary
              default: {}
            lagoon_groups:
                description: List of Lagoon groups to filter projects by
                type: list
                default: []
    requirements:
    - "python >= 3"
    - "PyYAML >= 3.11"
"""

EXAMPLES = """
# File must be named lagoon.yaml or lagoon.yml

# Fetch all projects and environments from a specific Lagoon
plugin: lagoon.api.lagoon
strict: false
lagoons:
  -
    lagoon_api_endpoint: 'http://localhost:4000'
    lagoon_api_token: ''
    transport: 'ssh'
    ssh_host: 'localhost'
    ssh_port: '22'
    headers: {}
    lagoon_groups:
      - my-group
groups:
  development: type == 'development'
  production: type == 'production'
leading_separator: false
keyed_groups:
  - key: lagoon_groups|map(attribute='name')
  - key: project_name

"""

display = Display()

class InventoryModule(BaseInventoryPlugin, Constructable):
    NAME = 'lagoon.api.lagoon'

    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)
        config = self._read_config_data(path)

        # Fetch and process projects from Lagoon.
        self.fetch_objects(self.get_option('lagoons'))

        strict = self.get_option('strict')

        try:
            for host in inventory.hosts:
              hostvars = inventory.hosts[host].get_vars()
              # Create composed groups.
              self._add_host_to_composed_groups(self.get_option('groups'), hostvars, host, strict=strict)
              # Create keyed groups.
              self._add_host_to_keyed_groups(self.get_option('keyed_groups'), hostvars, host, strict=strict)
        except Exception as e:
            raise AnsibleParserError("failed to parse %s: %s " % (to_native(path), to_native(e)), orig_exc=e)

    def fetch_objects(self, lagoons):

        if lagoons:
            if not isinstance(lagoons, list):
                raise AnsibleError (
                    "Expecting lagoons to be a list."
                )

            for lagoon in lagoons:

                if not isinstance(lagoon, dict):
                    raise AnsibleError(
                        "Lagoon must be a dictionary."
                    )

                if 'transport' not in lagoon:
                    lagoon['transport'] = 'ssh'
                elif lagoon['transport'] != 'ssh':
                    # @TODO kubectl support.
                    raise AnsibleError(
                        "Only ssh transport is supported."
                    )

                # Set default connections details to public Lagoon.
                if 'ssh_host' not in lagoon:
                    raise AnsibleError(
                        "Expecting SSH host."
                    )

                if 'ssh_port' not in lagoon:
                    raise AnsibleError(
                        "Expecting SSH port."
                    )

                if 'ssh_username' not in lagoon:
                    # If ssh_username is not defined in configuration file, 
                    # use lagoon as default user.
                    lagoon['ssh_username'] = 'lagoon'

                if 'lagoon_api_endpoint' not in lagoon:
                    raise AnsibleError(
                        "Expecting lagoon_api_endpoint."
                    )

                token = CreateToken(lagoon['ssh_host'], lagoon['ssh_port'], lagoon['ssh_username'])

                lagoon_api = ApiClient(
                    lagoon['lagoon_api_endpoint'],
                    token.get_token(),
                    {
                        'headers': lagoon['headers'] if 'headers' in lagoon else {}
                    }
                )

                project_list = []
                seen = []

                if 'lagoon_groups' in lagoon and lagoon['lagoon_groups']:
                    for group in lagoon['lagoon_groups']:
                        for project in lagoon_api.projects_in_group(group):
                            if project['name'] not in seen:
                                project_list.append(project)
                                seen.append(project['name'])

                else:
                    project_list = lagoon_api.projects_all()

                for project in project_list:
                    project_group = re.sub(r'[\W-]+', '_', project['name'])

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
        namespace = "%s-%s" % (project['name'], environment['name'])

        # Replace "\" or "." in environment names with "-".
        namespace = re.sub(r'[\/|.]+', '-', namespace)

        # Add host to the inventory.
        self.inventory.add_host(namespace)

        # Collect and set host variables.
        try:
          hostvars = self.collect_host_vars(namespace, environment, project, lagoon)
          for key,value in hostvars.items():
              self.inventory.set_variable(namespace, key, value)  
        except Exception as e:
            raise AnsibleParserError("failed to parse: %s " % (to_native(e)), orig_exc=e)

    def collect_host_vars(self, namespace, environment, project, lagoon):

      host_vars = {
          'name': namespace,
          'project_id': project['id'],
          'project_name': project['name'],
          'env_id': environment['id'],
          'env_name': environment['name'],
          'type': environment['environmentType'],
          'git_url': project['gitUrl'],

          # Complex values.
          'project_variables': project['variables'],
          'env_variables': environment['variables'],
          'lagoon_groups': project['groups'],

          # This adds all information returned from the Lagoon query to the host variable
          # list, this will by dynamic and keys are not guaranteed.
          'lagoon_project': project,
          'lagoon_environment': environment,

          # Ansible specific host variables these define how ansible
          # will connect to the remote host when the host is selected
          # for provisioning the play.
          'ansible_user': namespace,
          'ansible_ssh_user': namespace,
          'ansible_host': lagoon['ssh_host'],
          'ansible_port': lagoon['ssh_port'],
          'ansible_connection': 'local',
          'ansible_ssh_common_args': '-T -o "UserKnownHostsFile=/dev/null" -o "StrictHostKeyChecking=no"'
      }

      if 'metadata' in project:
          lagoon_meta = json.loads(project['metadata'])
          inventory_meta = {}
          for key, value in lagoon_meta.items():
              try:
                  # Metadata can be inserted as valid JSON, the lagoon interpreter
                  # will convert this to a JSON string and will escape with single quotes.
                  value = ast.literal_eval(value)
              except Exception as e: # noqa F841
                  # We ignore an invalid decode - this will be a standard string value.
                  pass

              inventory_meta[key] = value

          host_vars['metadata'] = inventory_meta

      return host_vars
