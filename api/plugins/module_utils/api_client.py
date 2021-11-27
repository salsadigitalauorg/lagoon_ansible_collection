from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import re
import time
from ansible.errors import AnsibleError
from ansible.module_utils.urls import open_url, ConnectionError, SSLValidationError
from ansible.module_utils._text import to_native
from ansible.module_utils.six.moves.urllib.error import HTTPError, URLError
from ansible.utils.display import Display

display = Display()

class ApiClient:

    def __init__(self, endpoint, token, options={}) -> None:
        self.options = options

        if 'headers' not in self.options:
            self.options['headers'] = {}
        elif not isinstance(self.options['headers'], dict):
            raise AnsibleError("Expecting client headers to be dictionary.")

        self.options['headers']['Content-Type'] = 'application/json'
        self.options['headers']['Authorization'] = "Bearer %s" % token
        self.options['endpoint'] = endpoint

    def projects_all(self):
        query = {
            'query': """query {
                allProjects {
                    id
                    name
                    gitUrl
                    branches
                    autoIdle
                    pullrequests
                    developmentEnvironmentsLimit
                    activeSystemsTask
                    activeSystemsMisc
                    activeSystemsDeploy
                    activeSystemsRemove
                    productionEnvironment
                    metadata
                    environments { id name environmentType updated created route }
                }
            }"""
        }
        result = self.make_api_call(self.__prepare_graphql_query(query))
        return result['data']['allProjects']

    ###
    # Get projects from specific groups.
    ###
    def projects_in_group(self, group):
        query = {
            'query': """query ($group: String!) {
                allProjectsInGroup(input: { name: $group }) {
                    id
                    name
                    gitUrl
                    branches
                    autoIdle
                    pullrequests
                    developmentEnvironmentsLimit
                    activeSystemsTask
                    activeSystemsMisc
                    activeSystemsDeploy
                    activeSystemsRemove
                    productionEnvironment
                    metadata
                    environments { id name environmentType updated created route }
                }
            }""",
            'variables': """{
                "group": "%s"
            }"""
        }

        result = self.make_api_call(self.__prepare_graphql_query(query) % group)
        return filter(None, result['data']['allProjectsInGroup'])

    def project(self, project):
        query = {
            'query': """query projectInfo($name: String!) {
                projectByName(name: $name) {
                    id
                    name
                    autoIdle
                    branches
                    gitUrl
                    metadata
                    openshift {
                        id
                        name
                    }
                    kubernetes {
                        id
                        name
                    }
                    environments {
                        name
                        openshift {
                            id
                            name
                        }
                        kubernetes {
                            id
                            name
                        }
                    }
                    deployTargetConfigs {
                        id
                        weight
                        branches
                        pullrequests
                        deployTarget {
                            name
                            id
                        }
                        project{
                            name
                        }
                    }
                }
            }""",
            'variables': '{"name": "%s"}'
        }
        result = self.make_api_call(self.__prepare_graphql_query(query) % project)
        if result['data']['projectByName'] == None:
            raise AnsibleError(
                "Unable to get details for project %s; please make sure the project name is correct" % project)
        return result['data']['projectByName']

    def project_from_environment(self, environment):
        query = {
            'query': """query projectInfoFromEnv($name: String!) {
                environmentByKubernetesNamespaceName(kubernetesNamespaceName: $name) {
                    project {
                        id
                        name
                        autoIdle
                        branches
                        gitUrl
                        metadata
                    }
                }
            }""",
            'variables': '{"name": "%s"}'
        }
        result = self.make_api_call(self.__prepare_graphql_query(query) % environment)
        if result['data']['environmentByKubernetesNamespaceName']['project'] == None:
            raise AnsibleError(
                "Unable to get project details for environment %s; please make sure the environment name is correct" % environment)
        return result['data']['environmentByKubernetesNamespaceName']['project']

    def project_get_variables(self, project):
        query = {
            'query': """query projectVars($name: String!) {
                projectByName(name: $name) {
                    envVariables {
                        id
                        name
                        value
                        scope
                    }
                }
            }""",
            'variables': '{"name": "%s"}'
        }
        result = self.make_api_call(self.__prepare_graphql_query(query) % project)
        if result['data']['projectByName'] == None:
            raise AnsibleError(
                "Unable to get variables for %s; please make sure the project name is correct" % project)
        return result['data']['projectByName']['envVariables']

    def project_get_groups(self, project):
        query = {
            'query': """query projectByName($name: String!) {
                projectByName(name: $name) {
                    groups { name }
                }
            }
            """,
            'variables': '{"name": "%s"}'
        }
        result = self.make_api_call(self.__prepare_graphql_query(query) % project)

        if result['data']['projectByName'] == None:
            raise AnsibleError(
                "Unable to get groups for %s; please make sure the project name is correct" % project)

        return result['data']['projectByName']['groups']

    def project_deploy(self, project, branch, wait=False, delay=60, retries=30):
        query = {
            'query': """mutation deploy($govcms_project: String!, $govcms_branch: String!) {
                deployEnvironmentLatest (input: {
                    environment: {
                        project: { name: $govcms_project },
                        name: $govcms_branch
                    }
                })
            }""",
            'variables': '{"govcms_project": "%s", "govcms_branch": "%s"}' %
            (project, branch)
        }
        result = self.make_api_call(self.__prepare_graphql_query(query))
        if not wait:
            return result['data']['deployEnvironmentLatest']

        display.display(
            "\033[30;1mWait for deployment completion for %s(%s) (%s retries left).\033[0m" % (project, branch, retries))
        return self.project_check_deploy_status(project, branch, wait, delay, retries)

    def project_check_deploy_status(self, project, branch, wait=False, delay=60, retries=30, current_try=1):
        time.sleep(delay)
        environment = self.environment(
            project + '-' + branch.replace('/', '-').replace('_', '-').replace('.', '-'))

        if (not wait or (len(environment['deployments']) and
            'status' in environment['deployments'][0] and
            environment['deployments'][0]['status'] in ['complete', 'failed', 'new', 'cancelled'])):
            return environment['deployments'][0]['status']

        if retries - current_try == 0:
            raise AnsibleError(
                'Maximium number of retries reached; view deployment logs for more information.')

        display.display(
            "\033[30;1mRETRYING: Wait for deployment completion for %s(%s) (%s retries left).\033[0m" % (project, branch, retries - current_try))
        return self.project_check_deploy_status(project, branch, wait, delay, retries, current_try + 1)

    def project_update(self, project_id, patch):
        query = {
            'query': """mutation UpdateProjectDeploymentCluster($projectId: Int!) {
                updateProject(input: {id: $projectId, patch: %s}) {
                    id
                    name
                    autoIdle
                    branches
                    gitUrl
                    metadata
                    openshift {
                        id
                        name
                    }
                    kubernetes {
                        id
                        name
                    }
                    environments {
                        name
                    }
                }
            }""" % self.__patch_dict_to_string(patch),
            'variables': '{"projectId": %s}' % project_id
        }
        result = self.make_api_call(self.__prepare_graphql_query(query))
        return result['data']['updateProject']

    def environment(self, environment):
        query = {
            'query': """query environmentInfo($name: String!) {
                environmentByKubernetesNamespaceName(kubernetesNamespaceName: $name) {
                    id
                    name
                    autoIdle
                    route
                    routes
                    deployments {
                        name
                        status
                        started
                        completed
                    }
                    project {
                        id
                    }
                    openshift {
                        id
                        name
                    }
                    kubernetes {
                        id
                        name
                    }
                }
            }""",
            'variables': '{"name": "%s"}' % environment
        }
        result = self.make_api_call(self.__prepare_graphql_query(query))
        if result['data']['environmentByKubernetesNamespaceName'] == None:
            raise AnsibleError(
                "Unable to get details for environment %s; please make sure the environment name is correct" % environment)

        environment = result['data']['environmentByKubernetesNamespaceName']

        if 'routes' in environment and environment['routes']:
            environment['routes'] = environment['routes'].split(',')

        return environment


    def environment_by_id(self, environment_id):
        query = {
            'query': """query environmentInfo($envId: Int!) {
                environmentById(id: $envId) {
                    id
                    name
                    autoIdle
                    deployments {
                        name
                        status
                        started
                        completed
                    }
                    project {
                        id
                    }
                }
            }""",
            'variables': '{"envId": %s}' % environment_id
        }
        result = self.make_api_call(self.__prepare_graphql_query(query))
        if result['data']['environmentById'] == None:
            raise AnsibleError(
                "Unable to get details for environment %s; please make sure the environment id is correct" % environment_id)
        return result['data']['environmentById']

    def environment_get_variables(self, environment):
        query = {
            'query': """query envVars($name: String!) {
                environmentByKubernetesNamespaceName(kubernetesNamespaceName: $name) {
                    envVariables {
                        id
                        name
                        value
                        scope
                    }
                }
            }""",
            'variables': '{"name": "%s"}'
        }
        result = self.make_api_call(self.__prepare_graphql_query(query) % environment)
        if result['data']['environmentByKubernetesNamespaceName'] == None:
            raise AnsibleError(
                "Unable to get variables for %s; please make sure the environment name is correct" % environment)
        return result['data']['environmentByKubernetesNamespaceName']['envVariables']

    def environment_update(self, environment_id, patch):
        query = {
            'query': """mutation updateEnvironment($environmentId: Int!) {
                updateEnvironment(input: {id: $environmentId, patch: %s}) {
                    id
                    name
                    openshift {
                        id
                        name
                    }
                    kubernetes {
                        id
                        name
                    }
                }
            }""" % self.__patch_dict_to_string(patch),
            'variables': '{"environmentId": %s}' % environment_id
        }
        result = self.make_api_call(self.__prepare_graphql_query(query))
        return result['data']['updateEnvironment']

    def environment_delete(self, project_name, environment_name):
        query = {
            'query': """
                mutation DeleteEnvironment($project_name: String!, $environment_name: String!) {
                    deleteEnvironment(input: { project: $project_name, name: $environment_name })
                }
            """,
            'variables': """{
                "project_name": "%s",
                "environment_name": "%s"
            }""" % (project_name, environment_name)
        }
        return self.make_api_call(self.__prepare_graphql_query(query))

    def add_variable(self, type, type_id, name, value, scope):
        query = {
            'query': """mutation AddEnvVar($type: EnvVariableType!, $type_id: Int!, $name: String!, $value: String!, $scope: EnvVariableScope!) {
                addEnvVariable(input: {type: $type, typeId: $type_id, scope: $scope, name: $name, value: $value}) {
                    id
                }
            }""",
            'variables': """{
                "type": "%s",
                "type_id": %s,
                "name": "%s",
                "value": "%s",
                "scope": "%s"
            }"""
        }
        result = self.make_api_call(self.__prepare_graphql_query(query) % (
            type, type_id, name, value, scope))
        return result['data']['addEnvVariable']['id']

    def delete_variable(self, id):
        query = {
            'query': """mutation DeleteVar($id: Int!) {
        deleteEnvVariable(input:  { id: $id }) }""",
            'variables': '{"id": %s}'
        }
        result = self.make_api_call(self.__prepare_graphql_query(query) % id)
        return result['data']['deleteEnvVariable']

    def metadata(self, project_name):
        return json.loads(self.project(project_name)['metadata'])

    def update_metadata(self, id, key, value):
        query = {
            'query': """mutation UpdateMeta($id: Int!, $key: String!, $value: String!) {
                updateProjectMetadata(input: { id: $id, patch: { key: $key, value: $value }}) {
                    id
                }
            }""",
            'variables': """{
                "id": %s,
                "key": "%s",
                "value": "%s"
            }"""
        }
        self.make_api_call(self.__prepare_graphql_query(query) % (id, key, value))
        return '%s:%s' % (key, value)

    def remove_metadata(self, id, key):
        query = {
            'query': """mutation RemoveMeta($id: Int!, $key: String!) {
                removeProjectMetadataByKey(input: { id: $id, key: $key }) {
                    id
                }
            }""",
            'variables': """{
                "id": %s,
                "key": "%s"
            }"""
        }
        self.make_api_call(self.__prepare_graphql_query(query) % (id, key))
        return '%s' % (key)

    def add_project_notification(self, project, notification, type='SLACK'):
        query = {
            'query': """mutation notification(
                $project: String!
                $type: NotificationType!
                $name: String!
            ) {
                addNotificationToProject(input: {
                    project: $project
                    notificationType: $type
                    notificationName: $name
                }) {
                    id
                    name
                }
            }""",
            'variables': """{
                "project": "%s",
                "name": "%s",
                "type": "%s"
            }"""
        }
        return self.make_api_call(self.__prepare_graphql_query(query) % (project, notification, type))

    def remove_project_notification(self, project, notification, type):
        query = {
            'query': """mutation notification(
                $project: String!
                $type: NotificationType!
                $name: String!
            ) {
                removeNotificationFromProject(input: {
                    project: $project
                    notificationType: $type
                    notificationName: $name
                }) {
                    id
                }
            }""",
            'variables': """{
                "project": "%s",
                "name": "%s",
                "type": "%s"
            }"""
        }

        return self.make_api_call(self.__prepare_graphql_query(query) % (project, notification, type))

    def group(self, name):
        query = {
            'query': """query group($name: String!) {
                groupByName(name: $name) {
                    id
                }
            }""",
            'variables': """{
                "name": "%s"
            }"""
        }
        result = self.make_api_call(
            self.__prepare_graphql_query(query) % (name)
        )
        return result['data']['groupByName']

    def group_add(self, name, parent=None):
        query = {
            'query': """mutation group($name: String!) {
                addGroup(input: { name: $name }) {
                    id
                }
            }""",
            'variables': """{
                "name": "%s"
            }"""
        }

        result = self.make_api_call(
            self.__prepare_graphql_query(query) % (name)
        )

        if result['errors']:
            raise AnsibleError("Group '%s' exists" % (name))

        return result['data']['addGroup']

    def group_remove(self, id):
        query = {}

    def user_add_group(self, email, group_name, role):
        query = {
            'query': """mutation group(
                $email: String!
                $group: String!
                $role: GroupRole!
            ) {
                addUserToGroup(input: {
                    user: { email: $email }
                    group: { name: $group }
                    role: $role
                }) {
                    id
                }
            }""",
            'variables': """{
                "email": "%s",
                "group": "%s",
                "role": "%s"
            }"""
        }

        result = self.make_api_call(self.__prepare_graphql_query(query) % (email, group_name, role.upper()))
        return result['data']['addUserToGroup']['id']

    def user_remove_group(self, email, group_name):
        query = {
            'query': """mutation group(
                $email: String!
                $group: String!
            ) {
                removeUserFromGroup(input: {
                    user: { email: $email }
                    group: { name: $group }
                }) {
                    id
                }
            }""",
            'variables': """{
                "email": "%s",
                "group": "%s"
            }"""
        }

        return self.make_api_call(self.__prepare_graphql_query(query) % (email, group_name))

    def deploy_target_config_add(self, project_id, configs):
        query_configs = []
        for idx, config in enumerate(configs):
            query_configs.append("""
                deployTarget%d: addDeployTargetConfig(
                    input: {
                        project: %d
                        branches: "%s"
                        pullrequests: "%s"
                        deployTarget: %d
                        weight: %d
                    }
                ) {
                    id
                    weight
                    branches
                    pullrequests
                    deployTarget {
                        name
                        id
                    }
                    project {
                        name
                    }
                }
            """ % (idx, project_id, config['branches'], config['pullrequests'],
                int(config['deployTarget']), config['weight']))
        query = {
            'query': """mutation addDeployTargetConfigs { %s }""" % self.__join_mutations(query_configs)
        }
        result = self.make_api_call(self.__prepare_graphql_query(query))
        return result['data']

    def deploy_target_config_delete(self, project_id, config_ids):
        query_configs = []
        if isinstance(config_ids, list):
            for config_id in config_ids:
                query_configs.append(self.deploy_target_config_delete_mutation(project_id, config_id))
        else:
            query_configs.append(self.deploy_target_config_delete_mutation(project_id, config_ids))

        query = {
            'query': """mutation deleteDeployTargetConfigs { %s }""" % self.__join_mutations(query_configs)
        }
        result = self.make_api_call(self.__prepare_graphql_query(query))
        return result['data']

    def deploy_target_config_delete_mutation(self, project_id, config_id):
        return """deleteDeployTargetConfig%d: deleteDeployTargetConfig(
		    input: { project: %d, id: %d })""" % (config_id, project_id, config_id)

    def make_api_call(self, payload):
        display.v("API call payload: %s" % payload)
        try:
            response = open_url(self.options.get('endpoint'), data=payload,
                                validate_certs=self.options.get(
                                    'validate_certs', False),
                                headers=self.options.get('headers', {}),
                                timeout=self.options.get('timeout', 30))
        except HTTPError as e:
            raise AnsibleError(
                "Received HTTP error: %s" % (to_native(e)))
        except URLError as e:
            raise AnsibleError(
                "Failed lookup url: %s" % (to_native(e)))
        except SSLValidationError as e:
            raise AnsibleError(
                "Error validating the server's certificate: %s" % (to_native(e)))
        except ConnectionError as e:
            raise AnsibleError("Error connecting: %s" % (to_native(e)))

        result = json.loads(response.read())
        display.v('API call result: %s' % result)
        return result

    def __patch_dict_to_string(self, patch):
        value_list = []
        for key, value in patch.items():
            value_item = key + ': '
            if type(value) is int:
                value_item += str(value)
            else:
                try:
                    value = int(value)
                    value_item += str(value)
                except ValueError:
                    value_item += '"' + value + '"'
            value_list.append(value_item)
        return '{' + ', '.join(value_list) + '}'

    # Remove newlines, tabs & multiple spaces.
    def __prepare_graphql_query(self, query):
        query_str = json.dumps(query)
        query_str = query_str.replace("\\n", "").replace("\\t", "")
        return re.sub(' +', ' ', query_str)

    def __join_mutations(self, mutations):
        return " ".join(mutations)
