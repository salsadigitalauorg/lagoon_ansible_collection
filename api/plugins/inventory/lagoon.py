import ast
import json
import re
import os
from ansible.errors import AnsibleError, AnsibleParserError
from ansible.inventory.data import InventoryData
from ansible.module_utils._text import to_native
from ansible.plugins.inventory import BaseInventoryPlugin, Cacheable, Constructable
from ..module_utils import token as LagoonToken
from ..module_utils.gql import GqlClient
from ..module_utils.gqlEnvironment import Environment
from ..module_utils.gqlProject import Project
from typing import Any, Optional


DOCUMENTATION = """
    name: lagoon
    short_description: Builds an inventory of Lagoon projects and environments.
    description:
    - Builds an inventory of Lagoon projects and environments.
    - The Lagoon GraphQL API degrades sharply on queries that carry many aliased
      root fields, so subresources (environments, groups, variables, clusters)
      are fetched one project or environment at a time. A full refresh therefore
      issues several requests per project and per environment, and on a large
      Lagoon can take many minutes.
    - Enabling C(cache) is strongly recommended for anything beyond a handful of
      projects. See the example below.
    plugin_type: inventory
    extends_documentation_fragment:
        - constructed
        - inventory_cache
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
            api_endpoint:
                description:
                - The lagoon API endpoint
                aliases: [ lagoon_api_endpoint ]
                env:
                - name: LAGOON_API_ENDPOINT
            api_token:
                description:
                - The lagoon API token
                aliases: [ lagoon_api_token ]
                env:
                - name: LAGOON_API_TOKEN
            headers:
              description: HTTP request headers
              type: dictionary
              default: {}
            filter_groups:
                description: List of Lagoon groups to filter projects by
                type: list
                default: []
                aliases: [ lagoon_filter_groups, lagoon_groups ]
                env:
                - name: LAGOON_FILTER_GROUPS
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
    api_endpoint: 'http://localhost:4000'
    api_token: ''
    transport: 'ssh'
    headers: {}
    filter_groups:
      - my-group
    ssh_port: '22'
    ssh_host: 'localhost'
groups:
  development: type == 'development'
  production: type == 'production'
leading_separator: false
keyed_groups:
  - key: lagoon_groups|map(attribute='name')
  - key: project_name
cache: true
cache_plugin: ansible.builtin.jsonfile
cache_timeout: 7200
cache_connection: /tmp/lagoon_inventory
cache_prefix: lagoon
"""


# Batching was removed because the Lagoon GraphQL API degrades sharply on
# queries carrying many aliased root fields. These options are still recognised
# so that existing inventory files keep working, but they have no effect and
# will be removed in a future major version.
DEPRECATED_BATCH_OPTIONS = [
    "api_batch_project_environments_size",
    "api_batch_project_groups_size",
    "api_batch_project_variables_size",
    "api_batch_environment_project_size",
    "api_batch_environment_cluster_size",
    "api_batch_environment_variables_size",
]


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    NAME = "lagoon.api.lagoon"

    def parse(self, inventory: InventoryData, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)

        self._read_config_data(path)
        cache_key = self.get_cache_key(path)

        # cache may be True or False at this point to indicate if the inventory is being refreshed
        # get the user's cache option too to see if we should save the cache if it is changing
        user_cache_setting = self.get_option("cache")

        # read if the user has caching enabled and the cache isn't being refreshed
        attempt_to_read_cache = user_cache_setting and cache
        # update if the user has caching enabled and the cache is being refreshed; update this value to True if the cache has expired below
        cache_needs_update = user_cache_setting and not cache

        self.all_objects = []

        # attempt to read the cache if inventory isn't being refreshed and the user has caching enabled
        if attempt_to_read_cache:
            try:
                self.all_objects = self._cache[cache_key]
            except KeyError:
                # This occurs if the cache_key is not in the cache or if the cache_key expired, so the cache needs to be updated
                cache_needs_update = True

        lagoons = self.get_option("lagoons")

        if not attempt_to_read_cache or cache_needs_update:
            # Fetch and process projects from Lagoon.
            self.fetch_objects(lagoons)

        if cache_needs_update:
            self._cache[cache_key] = self.all_objects

        strict = self.get_option("strict")
        self.populate()

        try:
            for host in inventory.hosts:
                hostvars = inventory.hosts[host].get_vars()
                # Create composed groups.
                self._add_host_to_composed_groups(
                    self.get_option("groups"), hostvars, host, strict=strict
                )
                # Create keyed groups.
                self._add_host_to_keyed_groups(
                    self.get_option("keyed_groups"), hostvars, host, strict=strict
                )
        except Exception as e:
            raise AnsibleParserError(
                "failed to parse %s: %s " % (to_native(path), to_native(e)), orig_exc=e
            )

    def fetch_objects(self, lagoons):

        if lagoons:
            if not isinstance(lagoons, list):
                raise AnsibleError("Expecting lagoons to be a list.")

            for lagoon in lagoons:
                if not isinstance(lagoon, dict):
                    raise AnsibleError("Expecting lagoon to be a dictionary.")

                if "transport" not in lagoon:
                    lagoon["transport"] = "ssh"
                elif lagoon["transport"] != "ssh":
                    # @TODO kubectl support.
                    raise AnsibleError("Only ssh transport is supported.")

                # Set default connections details to public Lagoon.
                lagoon["ssh_host"] = self.get_var(
                    lagoon, "ssh_host", "ssh.lagoon.amazeeio.cloud"
                )
                lagoon["ssh_port"] = self.get_var(lagoon, "ssh_port", "32222")

                # Endpoint & token can be provided in the file directly
                # or in --extra-vars. They could also be provided in separate
                # places.
                lagoon_api_endpoint = self.get_var(lagoon, "api_endpoint")
                lagoon_api_token = self.get_var(lagoon, "api_token")

                if not lagoon_api_endpoint:
                    raise AnsibleError("Expecting lagoon_api_endpoint.")

                if not lagoon_api_token:
                    # Try fetching a fresh token.
                    lagoon_api_token = self.fetch_lagoon_api_token(lagoon)

                # get_var also resolves LAGOON_* environment variables and
                # lagoon_* host vars, so this catches all three config routes.
                stale_options = [
                    o for o in DEPRECATED_BATCH_OPTIONS if self.get_var(lagoon, o)
                ]
                if stale_options:
                    self.display.warning(
                        "[DEPRECATION WARNING] These options are deprecated and "
                        "have no effect; the Lagoon API is now queried one "
                        "project/environment at a time: "
                        f"{', '.join(stale_options)}. Remove them - they will be "
                        "rejected in a future release."
                    )

                self.lagoon_api = GqlClient(
                    lagoon_api_endpoint,
                    lagoon_api_token,
                    lagoon["headers"] if "headers" in lagoon else {},
                    self.display,
                )
                lagoonProject = Project(self.lagoon_api, {"exitOnError": True})
                lagoonEnvironment = Environment(self.lagoon_api, {"exitOnError": True})

                objects = {
                    "lagoon": lagoon,
                    "project_list": [],
                    "project_environments": {},
                }

                lagoon_groups = self.get_var(lagoon, "filter_groups")
                # Backwards-compatibility.
                if not lagoon_groups:
                    lagoon_groups = self.get_var(lagoon, "groups")
                if isinstance(lagoon_groups, str):
                    lagoon_groups = lagoon_groups.split(",")

                if lagoon_groups:
                    self.display.v(
                        f"Fetching list of projects for these groups: [{', '.join(lagoon_groups)}]"
                    )
                    for group in lagoon_groups:
                        lagoonProject.allInGroup(group)
                else:
                    self.display.v("Fetching list of all projects")
                    lagoonProject.all()

                project_names = []
                # Ensure unique.
                for project in lagoonProject.projects:
                    if project["name"] not in project_names:
                        objects["project_list"].append(project)
                        project_names.append(project["name"])
                lagoonProject.projects = objects["project_list"]

                lagoonProject.withEnvironments(
                    [
                        "id",
                        "name",
                        "kubernetesNamespaceName",
                        "environmentType",
                        "route",
                        "routes",
                    ]
                ).withGroups().withVariables()
                if len(lagoonProject.errors):
                    self.display.error(
                        f"Errors while fetching project subresources: {lagoonProject.errors}"
                    )
                    raise AnsibleError(
                        """Encountered errors while fetching project subresources.
                        Each project is queried individually, so the errors above name the
                        projects that failed; re-run with -vvv to see the queries and
                        responses involved.""",
                    )

                for p in lagoonProject.projects:
                    for e in p["environments"]:
                        # If a project does not yet have an environment, `e`
                        # might be None.
                        if not e:
                            continue
                        lagoonEnvironment.environments.append(e)

                lagoonEnvironment.withProject(["name"]).withCluster().withVariables()

                if len(lagoonEnvironment.errors):
                    self.display.error(
                        f"Errors while fetching environment subresources: {lagoonEnvironment.errors}"
                    )
                    raise AnsibleError(
                        """Encountered errors while fetching environment subresources.
                        Each environment is queried individually, so the errors above name
                        the environments that failed; re-run with -vvv to see the queries
                        and responses involved.""",
                    )

                for e in lagoonEnvironment.environments:
                    pname = e["project"]["name"]
                    if not pname in objects["project_environments"]:
                        objects["project_environments"][pname] = []
                    objects["project_environments"][pname].append(e)

                self.all_objects.append(objects)

    def get_var(self, lagoon, name: str, default: Optional[Any] = None):
        """
        Determines a variable from the environment, host vars or lagoon.yml
        file, in that order.

        When looking at environment and host variables, the name is prefixed
        with 'LAGOON_' and 'lagoon_' respectively.
        """

        safe_name = f"lagoon_{name}"
        val = os.environ.get(safe_name.upper())
        if not val and safe_name in self._vars:
            val = self._vars.get(safe_name)
        elif not val and name in lagoon:
            val = lagoon.get(name)
        # Keep backwards compatibility with 'lagoon_' variables in lagoon.yml.
        elif not val and safe_name in lagoon:
            val = lagoon.get(safe_name)
        elif not val and default:
            val = default

        return val

    def populate(self):
        for objects in self.all_objects:
            for project in objects["project_list"]:
                project_envs = objects["project_environments"].get(project["name"])
                if not project_envs:
                    project_envs = []
                for environment in project_envs:
                    self.add_environment(project, environment, objects["lagoon"])

    # Add the environment to the inventory set.
    def add_environment(self, project, environment, lagoon):
        namespace = environment["kubernetesNamespaceName"]

        # Add host to the inventory.
        self.inventory.add_host(namespace)

        # Collect and set host variables.
        try:
            hostvars = self.collect_host_vars(namespace, environment, project, lagoon)
            for key, value in hostvars.items():
                self.inventory.set_variable(namespace, key, value)
        except Exception as e:
            raise AnsibleParserError(
                "failed to parse: %s " % (to_native(e)), orig_exc=e
            )

    def collect_host_vars(self, namespace, environment, project, lagoon):

        host_vars = {
            "name": namespace,
            "project_id": project["id"],
            "project_name": project["name"],
            "env_id": environment["id"],
            "env_name": environment["name"],
            "type": environment["environmentType"],
            "git_url": project["gitUrl"],
            "cluster_id": environment["kubernetes"]["id"],
            "cluster_name": environment["kubernetes"]["name"],
            # Complex values.
            "project_variables": {
                var["name"]: var["value"] for var in project["envVariables"]
            },
            "environment_variables": {
                var["name"]: var["value"] for var in environment["envVariables"]
            },
            "lagoon_groups": project["groups"],
            # This adds all information returned from the Lagoon query to the host variable
            # list, this will by dynamic and keys are not guaranteed.
            "lagoon_project": project,
            "lagoon_environment": environment,
            # Ansible specific host variables these define how ansible
            # will connect to the remote host when the host is selected
            # for provisioning the play.
            "ansible_user": namespace,
            "ansible_ssh_user": namespace,
            "ansible_host": lagoon["ssh_host"],
            "ansible_port": lagoon["ssh_port"],
            "ansible_ssh_common_args": '-T -o "UserKnownHostsFile=/dev/null" -o "StrictHostKeyChecking=no"',
        }

        if "metadata" in project:
            # The Lagoon API sometimes returns a proper json structure as the
            # value - we need to cater for both.
            lagoon_meta = project["metadata"]
            if type(project["metadata"]) is not dict:
                lagoon_meta = json.loads(project["metadata"])
            inventory_meta = {}
            for key, value in lagoon_meta.items():
                try:
                    # Metadata can be inserted as valid JSON, the lagoon interpreter
                    # will convert this to a JSON string and will escape with single quotes.
                    value = ast.literal_eval(value)
                except Exception as e:  # noqa F841
                    # We ignore an invalid decode - this will be a standard string value.
                    pass

                inventory_meta[key] = value

            host_vars["metadata"] = inventory_meta

        return host_vars

    def sanitised_name(self, name):
        return re.sub(r"[\W_-]+", "-", name)

    def fetch_lagoon_api_token(self, lagoon):
        lagoon_ssh_private_key = self.get_var(lagoon, "ssh_private_key")
        lagoon_ssh_private_key_file = self.get_var(lagoon, "ssh_private_key_file")

        if lagoon_ssh_private_key:
            if not lagoon_ssh_private_key_file:
                lagoon_ssh_private_key_file = "/tmp/lagoon_ssh_private_key"
            LagoonToken.write_ssh_key(
                lagoon_ssh_private_key, lagoon_ssh_private_key_file
            )

        rc, token, error = LagoonToken.fetch_token(
            lagoon.get("ssh_host"),
            lagoon.get("ssh_port"),
            "-q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no",
            lagoon_ssh_private_key_file,
        )

        if rc > 0:
            raise AnsibleError(
                "Failed to fetch Lagoon API token: %s (error code: %s) " % (error, rc)
            )

        return token["access_token"].strip()
