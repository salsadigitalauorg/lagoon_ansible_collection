from __future__ import absolute_import, division, print_function
__metaclass__ = type

import re
from ansible.errors import AnsibleFilterError
from functools import reduce

class FilterModule(object):

    def playbook_on_play_start(self, pattern):
        self.playbook = self.play.playbook
        self.inventory = self.playbook.inventory

    def bulkDeployEnvironmentInput(self, hosts, hostvars=None, env_id_key="env_id", env_key="env_name", project_key="project_name"):
        """
        Generate EnvironmentInput from the inventory to use for GraphQL queries.
        Examples:

        - name: Prepare environment input using environment id.
          lagoon.api.bulk_deploy:
            environments: "{{ ansible_play_hosts_all | lagoon.api.bulk_deploy_environment_input(hostvars) }}

        - name: Prepare environment input using default project & environment keys.
          lagoon.api.bulk_deploy:
            environments: "{{ ansible_play_hosts_all | lagoon.api.bulk_deploy_environment_input(hostvars, env_id_key=None) }}

        - name: Prepare environment input using specific project & environment keys.
          lagoon.api.bulk_deploy:
            environments: "{{ ansible_play_hosts_all | lagoon.api.bulk_deploy_environment_input(hostvars, env_id_key=None, env_key='env.name', project_key='project.name') }}
        """
        environments = []

        if hostvars is None:
            raise AnsibleFilterError("'hostvars' not found")

        for item in hosts:
            try:
                hv = hostvars[item]
                if env_id_key and env_id_key in hv:
                    environments.append({"id": hv[env_id_key]})
                else:
                    environments.append({
                        "name": reduce(lambda a, b: a[b], env_key.split("."), hv),
                        "project": {
                            "name": reduce(lambda a, b: a[b], project_key.split("."), hv),
                        },
                    })
            except KeyError as e:
                raise AnsibleFilterError(f"key {e} not found")

        return environments

    def autogenRoute(self, routes, route_pattern):
        """
        Get the Lagoon auto-generated route from the list of routes.
        Examples:
        - name: Get the auto-generated route.
          set_fact:
            autogen_route: "{{ lookup('lagoon.api.environment', inventory_hostname).routes | lagoon.api.autogen_route(route_pattern=route_pattern) }}"
          vars:
            route_pattern: "[a-z0-9-]+\.cluster[1-9]{1}\.amazee\.io"
        """

        routes_list = routes.split(",")
        for r in routes_list:
            matches = re.search(route_pattern, r)
            if matches:
                return r
        return None

    def filters(self):
        return {
            "autogen_route": self.autogenRoute,
            "bulk_deploy_environment_input": self.bulkDeployEnvironmentInput,
            "lagoon_autogen_route": self.autogenRoute, # DEPRECATED
            "lagoon_environment_input": self.bulkDeployEnvironmentInput, # DEPRECATED
        }
