from __future__ import absolute_import, division, print_function
import ast
import json
import re
import ansible_collections.lagoon.api.plugins.module_utils.token as LagoonToken
from ansible.errors import AnsibleError, AnsibleParserError
from ansible.inventory.data import InventoryData
from ansible.module_utils._text import to_native
from ansible.plugins.inventory import BaseInventoryPlugin, Cacheable, Constructable
from ansible.utils import py3compat
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from gql.dsl import DSLFragment, DSLQuery, dsl_gql
from gql.transport.exceptions import TransportQueryError
from graphql import print_ast
from typing import Any, List, Optional

__metaclass__ = type

DOCUMENTATION = """
    name: lagoon
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
            api_batch_group_size:
                description:
                - Create batches of this size when making multiple queries
                  in a single GraphQL query for groups. This allows for more
                  efficient querying while making less calls to the API.
                type: int
                default: 100
                aliases: [ lagoon_api_batch_group_size ]
                env:
                - name: LAGOON_API_BATCH_GROUP_SIZE
            api_batch_environment_size:
                description:
                - Create batches of this size when making multiple queries
                  in a single GraphQL query for environments. This allows for more
                  efficient querying while making less calls to the API.
                type: int
                default: 50
                aliases: [ lagoon_api_batch_environment_size ]
                env:
                - name: LAGOON_API_BATCH_ENVIRONMENT_SIZE
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
    api_batch_group_size: 100
    api_batch_environment_size: 50
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


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    NAME = 'lagoon.api.lagoon'

    def parse(self, inventory: InventoryData, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)

        self._read_config_data(path)
        cache_key = self.get_cache_key(path)

        # cache may be True or False at this point to indicate if the inventory is being refreshed
        # get the user's cache option too to see if we should save the cache if it is changing
        user_cache_setting = self.get_option('cache')

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

        lagoons = self.get_option('lagoons')

        if not attempt_to_read_cache or cache_needs_update:
            # Fetch and process projects from Lagoon.
            self.fetch_objects(lagoons)

        if cache_needs_update:
            self._cache[cache_key] = self.all_objects

        strict = self.get_option('strict')
        self.populate()

        try:
            for host in inventory.hosts:
                hostvars = inventory.hosts[host].get_vars()
                # Create composed groups.
                self._add_host_to_composed_groups(self.get_option(
                    'groups'), hostvars, host, strict=strict)
                # Create keyed groups.
                self._add_host_to_keyed_groups(self.get_option(
                    'keyed_groups'), hostvars, host, strict=strict)
        except Exception as e:
            raise AnsibleParserError("failed to parse %s: %s " % (
                to_native(path), to_native(e)), orig_exc=e)

    def fetch_objects(self, lagoons):

        if lagoons:
            if not isinstance(lagoons, list):
                raise AnsibleError(
                    "Expecting lagoons to be a list."
                )

            for lagoon in lagoons:

                if not isinstance(lagoon, dict):
                    raise AnsibleError(
                        "Expecting lagoon to be a dictionary."
                    )

                if 'transport' not in lagoon:
                    lagoon['transport'] = 'ssh'
                elif lagoon['transport'] != 'ssh':
                    # @TODO kubectl support.
                    raise AnsibleError(
                        "Only ssh transport is supported."
                    )

                # Set default connections details to public Lagoon.
                lagoon['ssh_host'] = self.get_var(lagoon, 'ssh_host', 'ssh.lagoon.amazeeio.cloud')
                lagoon['ssh_port'] = self.get_var(lagoon, 'ssh_port', '32222')

                # Endpoint & token can be provided in the file directly
                # or in --extra-vars. They could also be provided in separate
                # places.
                lagoon_api_endpoint = self.get_var(lagoon, 'api_endpoint')
                lagoon_api_token = self.get_var(lagoon, 'api_token')

                if not lagoon_api_endpoint:
                    raise AnsibleError(
                        "Expecting lagoon_api_endpoint."
                    )

                if not lagoon_api_token:
                    # Try fetching a fresh token.
                    lagoon_api_token = self.fetch_lagoon_api_token(lagoon)

                # Batch sizes should be overridable by environment variables.
                self.api_batch_group_size = self.get_var(lagoon, 'api_batch_group_size', 100)
                if isinstance(self.api_batch_group_size, str):
                    self.api_batch_group_size = int(self.api_batch_group_size)

                self.api_batch_environment_size = self.get_var(lagoon, 'api_batch_environment_size', 50)
                if isinstance(self.api_batch_environment_size, str):
                    self.api_batch_environment_size = int(self.api_batch_environment_size)

                self.lagoon_api = GqlClient(
                    lagoon_api_endpoint,
                    lagoon_api_token,
                    lagoon['headers'] if 'headers' in lagoon else {}
                )

                objects = {
                    'lagoon': lagoon,
                    'project_list': [],
                    'projects_groups_n_vars': {},
                    'environments_clusters': {},
                    'environments_vars': {}
                }

                seen = []
                lagoon_groups = self.get_var(lagoon, 'filter_groups')
                # Backwards-compatibility.
                if not lagoon_groups:
                    lagoon_groups = self.get_var(lagoon, 'groups')
                if isinstance(lagoon_groups, str):
                    lagoon_groups = lagoon_groups.split(",")
                if lagoon_groups:
                    self.display.v(f"Fetching list of projects for these groups: [{', '.join(lagoon_groups)}]")
                    for group in lagoon_groups:
                        for project in self.get_projects_in_group(group):
                            if project['name'] not in seen:
                                objects['project_list'].append(project)
                                seen.append(project['name'])

                else:
                    self.display.v("Fetching list of all projects")
                    objects['project_list'] = self.get_projects()

                project_names = []
                for project in objects['project_list']:
                    project_names.append(project['name'])

                objects['projects_environments'] = self.batch_fetch_projects_environments(project_names)
                environment_names = []
                environment_names_ids = []
                for project, environments in objects['projects_environments'].items():
                    for environment in environments['environments']:
                        environment_names.append(environment['kubernetesNamespaceName'])
                        environment_names_ids.append((environment['kubernetesNamespaceName'], environment['id']))

                # Secondary batch lookup as group queries validate permissions
                # on each trip and results in query timeouts if these
                # were returned with the project list.
                objects['projects_groups_n_vars'] = self.batch_fetch_projects_groups_and_variables(project_names)

                # Do the same for environment clusters.
                objects['environments_clusters'] = self.batch_fetch_environments_cluster(environment_names_ids)

                # Do the same for environment vars.
                objects['environments_vars'] = self.batch_get_env_vars(environment_names)

                self.all_objects.append(objects)

    def get_var(self, lagoon, name: str, default: Optional[Any] = None):
        """
        Determines a variable from the environment, host vars or lagoon.yml
        file, in that order.

        When looking at environment and host variables, the name is prefixed
        with 'LAGOON_' and 'lagoon_' respectively.
        """

        safe_name = f"lagoon_{name}"
        val = py3compat.environ.get(safe_name.upper())
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
            for project in objects['project_list']:
                pgv = objects['projects_groups_n_vars'].get(
                        self.sanitised_for_query_alias(project['name']))
                project['groups'], project['envVariables'] = pgv['groups'], pgv['envVariables']

                penv = objects['projects_environments'].get(self.sanitised_for_query_alias(project['name']))
                project['environments'] = penv['environments']

                for environment in project['environments']:
                    try:
                        environment['kubernetes'] = objects['environments_clusters'].get(
                            self.sanitised_for_query_alias(environment['kubernetesNamespaceName']))['kubernetes']
                    except:
                        environment['kubernetes'] = []
                    try:
                        environment['envVariables'] = objects['environments_vars'].get(
                            self.sanitised_for_query_alias(environment['kubernetesNamespaceName']))['envVariables']
                    except:
                        environment['envVariables'] = []
                    self.add_environment(project, environment, objects['lagoon'])

    # Add the environment to the inventory set.
    def add_environment(self, project, environment, lagoon):
        namespace = environment['kubernetesNamespaceName']

        # Add host to the inventory.
        self.inventory.add_host(namespace)

        # Collect and set host variables.
        try:
            hostvars = self.collect_host_vars(namespace, environment, project, lagoon)
            for key, value in hostvars.items():
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
            'cluster_id': environment['kubernetes']['id'],
            'cluster_name': environment['kubernetes']['name'],

            # Complex values.
            'project_variables': {var['name']: var['value'] for var in project['envVariables']},
            'environment_variables': {var['name']: var['value'] for var in environment['envVariables']},
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

    def get_projects(self) -> dict:
        """Get all projects"""

        res = self.lagoon_api.execute_query(
            """
            query GetProjects {
                allProjects {
                    id
                    name
                    gitUrl
                    metadata
                }
            }
            """
        )
        return res['allProjects']

    def get_projects_in_group(self, group: str):
        """Get projects from specific groups."""

        res = self.lagoon_api.execute_query(
            """
            query ($group: String!) {
                allProjectsInGroup(input: { name: $group }) {
                    id
                    name
                    gitUrl
                    metadata
                }
            }
            """,
            {"group": group}
        )
        return filter(None, res['allProjectsInGroup'])

    def batch_fetch_projects_environments(self, projects: List[str]) -> dict:
        """
        Get the environments for a batch of projects.
        """

        environments = {}

        # Create batches.
        batches = []
        for i in range(0, len(projects), self.api_batch_group_size):
            batches.append(projects[i:i+self.api_batch_group_size])

        for i, b in enumerate(batches):
            self.display.v(f"Fetching environments for batch {i+1}/{len(batches)}")
            environments.update(self.batch_fetch_environments_execute(b))

        return environments

    def batch_fetch_projects_groups_and_variables(self, projects: List[str]) -> dict:
        """
        Get the groups & variables for a batch of projects.
        """

        groups_n_vars = {}

        # Create batches.
        batches = []
        for i in range(0, len(projects), self.api_batch_group_size):
            batches.append(projects[i:i+self.api_batch_group_size])

        for i, b in enumerate(batches):
            self.display.v(f"Fetching groups & vars for batch {i+1}/{len(batches)}")
            groups_n_vars.update(self.batch_fetch_groups_and_vars_execute(b))

        return groups_n_vars

    def batch_fetch_environments_execute(self, batch: List[str]):
        """
        Build the query for a batch of environments.

        The expected built query is as follows:
        query {
            projectByName(name: "project-name") {
                environments { id name kubernetesNamespaceName environmentType routes }
            }
        }
        """
        self.display.vv(f"Fetching environments for [{', '.join(batch)}]")
        with self.lagoon_api as (_, ds):
            # Build the fragment.
            environment_fields = ds.Project.environments.select(
                ds.Environment.id,
                ds.Environment.name,
                ds.Environment.kubernetesNamespaceName,
                ds.Environment.environmentType,
                ds.Environment.routes
            )

            field_queries = []
            for pname in batch:
                # Build the main query.
                field_query = ds.Query.projectByName.args(
                    name=pname).alias(self.sanitised_for_query_alias(pname))
                field_query.select(environment_fields)
                field_queries.append(field_query)

            query = dsl_gql(DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")

            try:
                return self.lagoon_api.client.session.execute(query)
            except TransportQueryError as e:
                if len(e.data):
                    raise AnsibleError(
                        """
The gql query returned incomplete data; this could be due to the batch query
timing out. You could try decreasing the batch size (`lagoon_api_batch_group_size`)
and see if that helps""", None, True, False, e)
                else:
                    raise e
            except Exception as e:
                raise e

    def batch_fetch_groups_and_vars_execute(self, batch: List[str]):
        """
        Build the query for a batch of projects.

        The expected built query is as follows:
        query {
            project1_name: projectByName(name: "project1-name") {
                ...GroupsNVars
            }
            project2_name: projectByName(name: "project2-name") {
                ...GroupsNVars
            }
        }
        fragment GroupsNVars on Project {
            groups { name }
            envVariables { name value }
        }

        """
        self.display.vv(f"Fetching groups & vars for [{', '.join(batch)}]")
        with self.lagoon_api as (_, ds):
            # Build the fragment.
            groupsnvars_fields = DSLFragment("GroupsNVars")
            groupsnvars_fields.on(ds.Project)
            groupsnvars_fields.select(
                ds.Project.groups.select(ds.GroupInterface.name),
                ds.Project.envVariables.select(
                    ds.EnvKeyValue.name,
                    ds.EnvKeyValue.value,
                ),
            )

            field_queries = []
            for pname in batch:
                # Build the main query.
                field_query = ds.Query.projectByName.args(
                    name=pname).alias(self.sanitised_for_query_alias(pname))
                field_query.select(groupsnvars_fields)
                field_queries.append(field_query)

            query = dsl_gql(groupsnvars_fields, DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")
            try:
                return self.lagoon_api.client.session.execute(query)
            except TransportQueryError as e:
                if len(e.data):
                    raise AnsibleError(
                        """
The gql query returned incomplete data; this could be due to the batch query
timing out. You could try decreasing the batch size (`lagoon_api_batch_group_size`)
and see if that helps""", None, True, False, e)
                else:
                    raise e
            except Exception as e:
                raise e

    def batch_fetch_environments_cluster(self, environments: List[tuple]) -> dict:
        """
        Fetch the cluster for environments in batches.
        """

        env_clusters = {}

        # Create batches.
        batches = []
        for i in range(0, len(environments), self.api_batch_environment_size):
            batches.append(environments[i:i+self.api_batch_environment_size])

        for i, b in enumerate(batches):
            self.display.v(
                f"Fetching env clusters for batch {i+1}/{len(batches)}")
            env_clusters.update(
                self.batch_fetch_environments_cluster_execute(b))

        return env_clusters

    def batch_fetch_environments_cluster_execute(self, batch_envs):
        """
        Build the query for a batch of environments' cluster.

        The expected built query is as follows:
        query {
            environmentById(id: envId) {
                kubernetes {
                    id
                    name
                }
            }
        }
        """
        self.display.vv(
            f"Fetching cluster for environments [{', '.join([envName for envName, _ in batch_envs])}]")
        with self.lagoon_api as (_, ds):
            # Build the fragment.
            cluster_fields = ds.Environment.kubernetes.select(
                ds.Kubernetes.id,
                ds.Kubernetes.name
            )

            field_queries = []
            for envName, envId in batch_envs:
                # Build the main query.
                field_query = ds.Query.environmentById.args(
                    id=envId).alias(self.sanitised_for_query_alias(envName))
                field_query.select(cluster_fields)
                field_queries.append(field_query)

            query = dsl_gql(DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")

            try:
                return self.lagoon_api.client.session.execute(query)
            except TransportQueryError as e:
                if len(e.data):
                    raise AnsibleError(
                        """
The gql query returned incomplete data; this could be due to the batch query
timing out. You could try decreasing the batch size (`lagoon_api_batch_group_size`)
and see if that helps""", None, True, False, e)
                else:
                    raise e
            except Exception as e:
                raise e

    def batch_get_env_vars(self, environments: List[str]) -> dict:
        """
        Get the variables for a batch of environments.
        """

        env_vars = {}

        # Create batches.
        batches = []
        for i in range(0, len(environments), self.api_batch_environment_size):
            batches.append(environments[i:i+self.api_batch_environment_size])

        for i, b in enumerate(batches):
            self.display.v(f"Fetching env vars for batch {i+1}/{len(batches)}")
            env_vars.update(self.batch_get_env_vars_execute(b))

        return env_vars

    def batch_get_env_vars_execute(self, batch: List[str]):
        """
        Build the query for a batch of environments

        The expected built query is as follows:
        query {
            project_env_1: environmentByKubernetesNamespaceName(kubernetesNamespaceName: "project-env-1") {
                ...EnvVars
            }
            project_env_2: environmentByKubernetesNamespaceName(kubernetesNamespaceName: "project-env-2") {
                ...EnvVars
            }
        }
        fragment EnvVars on Environment {
            envVariables { name value }
        }
        """

        self.display.vv(f"Fetching env vars for [{', '.join(batch)}]")
        query = "query {"
        for env in batch:
            query += f"""
                      {self.sanitised_for_query_alias(env)}: environmentByKubernetesNamespaceName(kubernetesNamespaceName: "{env}") {{
                          ...EnvVars
                      }}
                      """
        query += """
                }

                fragment EnvVars on Environment {
                    envVariables { name value }
                }
                """

        self.display.vvvv(f"Query: \n{query}")

        try:
            return self.lagoon_api.execute_query(query)
        except TransportQueryError as e:
            if len(e.data):
                raise AnsibleError(
                    """
The gql query returned incomplete data; this could be due to the batch query
timing out. You could try decreasing the batch size (`lagoon_api_batch_environment_size`)
and see if that helps""", None, True, False, e)
            else:
                raise e
        except Exception as e:
            raise e

    def sanitised_name(self, name):
        return re.sub(r'[\W_-]+', '-', name)

    def sanitised_for_query_alias(self, name):
        return re.sub(r'[\W-]+', '_', name)

    def fetch_lagoon_api_token(self, lagoon):
        lagoon_ssh_private_key = self.get_var(lagoon, 'ssh_private_key')
        lagoon_ssh_private_key_file = self.get_var(lagoon, 'ssh_private_key_file')

        if lagoon_ssh_private_key:
            if not lagoon_ssh_private_key_file:
                lagoon_ssh_private_key_file = '/tmp/lagoon_ssh_private_key'
            LagoonToken.write_ssh_key(lagoon_ssh_private_key, lagoon_ssh_private_key_file)

        rc, token, error = LagoonToken.fetch_token(
            lagoon.get('ssh_host'),
            lagoon.get('ssh_port'),
            "-q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no",
            lagoon_ssh_private_key_file
        )

        if rc > 0:
            raise AnsibleError("Failed to fetch Lagoon API token: %s (error code: %s) " % (error, rc))

        return token.decode("utf-8").strip()
