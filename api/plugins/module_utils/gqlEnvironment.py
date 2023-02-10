from .gqlResourceBase import CLUSTER_FIELDS, DEFAULT_BATCH_SIZE, DEPLOYMENTS_FIELDS, ENVIRONMENTS_FIELDS, PROJECT_FIELDS, ResourceBase, VARIABLES_FIELDS
from .gql import GqlClient
from .gqlProject import Project

from ansible.errors import AnsibleError
from gql.dsl import DSLQuery
from gql.transport.exceptions import TransportQueryError
from time import sleep
from typing import List
from typing_extensions import Self


class Environment(ResourceBase):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)
        self.environments = []

    def all(self, fields: List[str] = None) -> Self:
        """
        Get a list of all environments, but only top level fields.

        This method first tries using the allEnvironments query, and if it fails
        due to lack of permissions, it fetches all projects instead.
        """

        if not fields:
            fields = ENVIRONMENTS_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    allEnvironments {{
        { joined_fields }
    }}
}}"""

        try:
            res = self.client.execute_query(query)
            self.environments.extend(res['allEnvironments'])
        except TransportQueryError as e:
            self.v(f"{e.errors}")
            if e.errors[0]['message'] == 'Unauthorized: You don\'t have permission to "viewAll" on "environment": {}':
                return self.allThroughProjects(fields)
            elif isinstance(e.data['allEnvironments'], list):
                self.environments.extend(e.data['allEnvironments'])
                self.errors.extend(e.errors)
            else:
                raise
        except Exception:
            raise

        return self

    def allThroughProjects(self, fields: List[str] = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Self:
        """
        Get a list of all environments, but going through projects first.
        """

        projects = Project(self.client, self.options).all(
            ).withEnvironments(fields, batch_size).projects

        for p in projects:
            self.environments.extend(p['environments'])

        return self

    def byNs(self, ns: str, fields: List[str] = None) -> Self:
        """
        Get the top-level information for an environment by k8s namespace.
        """

        if not fields:
            fields = ENVIRONMENTS_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    environmentByKubernetesNamespaceName (kubernetesNamespaceName: "{ ns }") {{
        { joined_fields }
    }}
}}"""

        try:
            res = self.client.execute_query(query)
            if res['environmentByKubernetesNamespaceName'] != None:
                self.environments.append(
                    res['environmentByKubernetesNamespaceName'])
        except TransportQueryError as e:
            if isinstance(e.data['environmentByKubernetesNamespaceName'], list):
                self.environments.append(e.data['environmentByKubernetesNamespaceName'])
                self.errors.extend(e.errors)
            else:
                raise
        except Exception:
            raise

        return self

    def byId(self, id: int, fields: List[str] = None) -> Self:
        """
        Get the top-level information for an environment by id.
        """

        if not fields:
            fields = ENVIRONMENTS_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    environmentById (id: "{ id }") {{
        { joined_fields }
    }}
}}"""

        try:
            res = self.client.execute_query(query)
            if res['environmentById'] != None:
                self.environments.append(res['environmentById'])
        except TransportQueryError as e:
            if isinstance(e.data['environmentById'], list):
                self.environments.append(e.data['environmentById'])
                self.errors.extend(e.errors)
            else:
                raise
        except Exception:
            raise

        return self

    def withCluster(self, fields: List[str] = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Self:
        """
        Retrieve cluster information for the environments.
        """

        if not len(self.environments):
            return self

        env_names = [e['kubernetesNamespaceName'] for e in self.environments]

        batches = []
        for i in range(0, len(env_names), batch_size):
            batches.append(env_names[i:i+batch_size])

        clusters = {}
        for i, b in enumerate(batches):
            self.v(f"Fetching cluster for batch {i+1}/{len(batches)}")
            clusters.update(self.getCluster(b, fields))
            self.raiseExceptionIfRequired("Error fetching environment cluster")

        for environment in self.environments:
            ns = environment['kubernetesNamespaceName']
            environment['kubernetes'] = clusters.get(ns)
            environment['openshift'] = clusters.get(ns)

        return self

    def withVariables(self, fields: List[str] = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Self:
        """
        Retrieve the environments' variables.
        """

        if not len(self.environments):
            return self

        env_names = [e['kubernetesNamespaceName'] for e in self.environments]

        batches = []
        for i in range(0, len(env_names), batch_size):
            batches.append(env_names[i:i+batch_size])

        environmentVars = {}
        for i, b in enumerate(batches):
            self.v(
                f"Fetching variables for batch {i+1}/{len(batches)}")
            environmentVars.update(self.getVariables(b, fields))
            self.raiseExceptionIfRequired("Error fetching environment variables")

        for environment in self.environments:
            environment['envVariables'] = environmentVars.get(
                environment['kubernetesNamespaceName'])

        return self

    def withProject(self, fields: List[str] = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Self:
        """
        Retrieve the environments' project.
        """

        if not len(self.environments):
            return self

        env_names = [e['kubernetesNamespaceName'] for e in self.environments]

        batches = []
        for i in range(0, len(env_names), batch_size):
            batches.append(env_names[i:i+batch_size])

        envProject = {}
        for i, b in enumerate(batches):
            self.v(
                f"Fetching project for batch {i+1}/{len(batches)}")
            envProject.update(self.getProject(b, fields))
            self.raiseExceptionIfRequired(
                "Error fetching environment project")

        for environment in self.environments:
            environment['project'] = envProject.get(
                environment['kubernetesNamespaceName'])

        return self

    def withDeployments(self, fields: List[str] = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Self:
        """
        Retrieve the environments' deployments.
        """

        if not len(self.environments):
            return self

        env_names = [e['kubernetesNamespaceName'] for e in self.environments]

        batches = []
        for i in range(0, len(env_names), batch_size):
            batches.append(env_names[i:i+batch_size])

        envDeployments = {}
        for i, b in enumerate(batches):
            self.v(
                f"Fetching deployments for batch {i+1}/{len(batches)}")
            envDeployments.update(self.getDeployments(b, fields))
            self.raiseExceptionIfRequired("Error fetching deployments")

        for environment in self.environments:
            environment['deployments'] = envDeployments.get(
                environment['kubernetesNamespaceName'])

        return self

    def getCluster(self, env_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = CLUSTER_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            cluster_fields = ds.Environment.kubernetes.select(
                getattr(ds.Kubernetes, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    cluster_fields.select(getattr(ds.Kubernetes, f))

            field_queries = []
            for eName in env_names:
                # Build the main query.
                field_query = ds.Query.environmentByKubernetesNamespaceName.args(
                    kubernetesNamespaceName=eName).alias(
                        self.sanitiseForQueryAlias(eName))
                field_query.select(cluster_fields)
                field_queries.append(field_query)

            resources = self.queryResources(DSLQuery(*field_queries))

        for eName in env_names:
            try:
                res[eName] = resources.get(
                    self.sanitiseForQueryAlias(eName))['kubernetes']
            except:
                res[eName] = None

        return res

    def getVariables(self, env_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = VARIABLES_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            var_fields = ds.Environment.envVariables.select(
                getattr(ds.EnvKeyValue, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    var_fields.select(getattr(ds.EnvKeyValue, f))

            field_queries = []
            for eName in env_names:
                # Build the main query.
                field_query = ds.Query.environmentByKubernetesNamespaceName.args(
                    kubernetesNamespaceName=eName).alias(
                        self.sanitiseForQueryAlias(eName))
                field_query.select(var_fields)
                field_queries.append(field_query)

            resources = self.queryResources(DSLQuery(*field_queries))

        for eName in env_names:
            try:
                res[eName] = resources.get(
                    self.sanitiseForQueryAlias(eName))['envVariables']
            except:
                res[eName] = None

        return res

    def getProject(self, env_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = PROJECT_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            project_fields = ds.Environment.project.select(
                getattr(ds.Project, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    project_fields.select(getattr(ds.Project, f))

            field_queries = []
            for eName in env_names:
                # Build the main query.
                field_query = ds.Query.environmentByKubernetesNamespaceName.args(
                    kubernetesNamespaceName=eName).alias(
                        self.sanitiseForQueryAlias(eName))
                field_query.select(project_fields)
                field_queries.append(field_query)

            resources = self.queryResources(DSLQuery(*field_queries))

        for eName in env_names:
            try:
                res[eName] = resources.get(
                    self.sanitiseForQueryAlias(eName))['project']
            except:
                res[eName] = None

        return res

    def getDeployments(self, env_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = DEPLOYMENTS_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            deployment_fields = ds.Environment.deployments.select(
                getattr(ds.Deployment, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    deployment_fields.select(getattr(ds.Deployment, f))

            field_queries = []
            for eName in env_names:
                # Build the main query.
                field_query = ds.Query.environmentByKubernetesNamespaceName.args(
                    kubernetesNamespaceName=eName).alias(
                        self.sanitiseForQueryAlias(eName))
                field_query.select(deployment_fields)
                field_queries.append(field_query)

            resources = self.queryResources(DSLQuery(*field_queries))

        for eName in env_names:
            try:
                res[eName] = resources.get(
                    self.sanitiseForQueryAlias(eName))['deployments']
            except:
                res[eName] = None

        return res

    def deployBranch(self, project: str, branch: str, wait: bool=False, delay: int=60, retries: int=30) -> str:
        mutation = """
        mutation deploy($project: String!, $branch: String!) {
            deployEnvironmentBranch (input: {
                project: { name: $project },
                branchName: $branch
            })
        }"""

        mutation_vars = {
            "project": project,
            "branch": branch,
        }

        res = self.client.execute_query(mutation, mutation_vars)
        if 'errors' in res:
            raise AnsibleError("Unable to deploy branch.", res['errors'])

        if not wait:
            return res['deployEnvironmentBranch']

        env_ns = self.sanitisedName(f"{project}-{branch}")
        return self.checkDeployStatus(env_ns, wait, delay, retries)

    def checkDeployStatus(self, env_ns: str, wait: bool=False, delay: int=60, retries: int=30, current_try: int=1):
        sleep(delay)

        deployments = self.getDeployments([env_ns])[env_ns]

        if (not wait or (len(deployments) and
            'status' in deployments[0] and
            deployments[0]['status'] in ['complete', 'failed', 'new', 'cancelled'])):
            return deployments[0]['status']

        if retries - current_try == 0:
            raise AnsibleError(
                'Maximium number of retries reached; view deployment logs for more information.')

        self.display(
            f"\033[30;1mRETRYING: Wait for deployment completion for {env_ns} ({retries - current_try} retries left).\033[0m")
        return self.checkDeployStatus(env_ns, wait, delay, retries, current_try + 1)

    def bulkDeploy(self, build_vars: list, name: str, envs: list) -> str:
        mutation = """
        mutation bulkDeployEnvironment(
            $build_vars:[EnvKeyValueInput]
            $envs: [DeployEnvironmentLatestInput!]!
            $name: String
        ) {
            bulkDeployEnvironmentLatest(input: {
                name: $name
                buildVariables: $build_vars
                environments: $envs
            })
        }"""

        mutation_vars = {
            "build_vars": build_vars,
            "name": name,
            "envs": envs,
        }

        res = self.client.execute_query(mutation, mutation_vars)
        if 'errors' in res:
            raise AnsibleError("Unable to create bulk deployment.", res['errors'])
        return res['bulkDeployEnvironmentLatest']
