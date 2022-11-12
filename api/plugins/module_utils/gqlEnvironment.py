from ansible_collections.lagoon.api.plugins.module_utils import gqlResourceBase
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible_collections.lagoon.api.plugins.module_utils.gqlProject import Project
from gql.dsl import DSLQuery, dsl_gql
from gql.transport.exceptions import TransportQueryError
from graphql import print_ast
from typing import List
from typing_extensions import Self


class Environment(gqlResourceBase.ResourceBase):

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
            fields = gqlResourceBase.ENVIRONMENTS_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    allEnvironments {{
        { joined_fields }
    }}
}}"""

        self.display.vvvv(f"{ query }")

        try:
            res = self.client.execute_query(query)
            self.environments.extend(res['allEnvironments'])
        except TransportQueryError as e:
            self.display.v(f"{e.errors}")
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

    def allThroughProjects(self, fields: List[str] = None) -> Self:
        """
        Get a list of all environments, but going through projects first.
        """

        projects = Project(self.client, self.options).all(
            ).withEnvironments(fields).projects

        for p in projects:
            self.environments.extend(p['environments'])

        return self

    def byNs(self, ns: str, fields: List[str] = None) -> Self:
        """
        Get the top-level information for an environment by k8s namespace.
        """

        if not fields:
            fields = gqlResourceBase.ENVIRONMENTS_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    environmentByKubernetesNamespaceName (kubernetesNamespaceName: "{ ns }") {{
        { joined_fields }
    }}
}}"""

        self.display.vvvv(f"{ query }")

        try:
            res = self.client.execute_query(query)
            self.environments.append(res['environmentByKubernetesNamespaceName'])
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
            fields = gqlResourceBase.ENVIRONMENTS_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    environmentById (id: "{ id }") {{
        { joined_fields }
    }}
}}"""

        self.display.vvvv(f"{ query }")

        try:
            res = self.client.execute_query(query)
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

    def withCluster(self, fields: List[str] = None) -> Self:
        """
        Retrieve cluster information for the environments.
        """

        if not len(self.environments):
            return self

        env_names = [e['kubernetesNamespaceName'] for e in self.environments]

        batches = []
        for i in range(0, len(env_names), self.batch_size):
            batches.append(env_names[i:i+self.batch_size])

        clusters = {}
        for i, b in enumerate(batches):
            self.display.v(f"Fetching cluster for batch {i+1}/{len(batches)}")
            clusters.update(self.getCluster(b, fields))

        for environment in self.environments:
            ns = environment['kubernetesNamespaceName']
            environment['kubernetes'] = clusters.get(ns)
            environment['openshift'] = clusters.get(ns)

        return self

    def withVariables(self, fields: List[str] = None) -> Self:
        """
        Retrieve the environments' variables.
        """

        if not len(self.environments):
            return self

        env_names = [e['kubernetesNamespaceName'] for e in self.environments]

        batches = []
        for i in range(0, len(env_names), self.batch_size):
            batches.append(env_names[i:i+self.batch_size])

        environmentVars = {}
        for i, b in enumerate(batches):
            self.display.v(
                f"Fetching variables for batch {i+1}/{len(batches)}")
            environmentVars.update(self.getVariables(b, fields))

        for environment in self.environments:
            environment['envVariables'] = environmentVars.get(
                environment['kubernetesNamespaceName'])

        return self

    def withProject(self, fields: List[str] = None) -> Self:
        """
        Retrieve the environments' project.
        """

        if not len(self.environments):
            return self

        env_names = [e['kubernetesNamespaceName'] for e in self.environments]

        batches = []
        for i in range(0, len(env_names), self.batch_size):
            batches.append(env_names[i:i+self.batch_size])

        envProject = {}
        for i, b in enumerate(batches):
            self.display.v(
                f"Fetching project for batch {i+1}/{len(batches)}")
            envProject.update(self.getProject(b, fields))

        for environment in self.environments:
            environment['project'] = envProject.get(
                environment['kubernetesNamespaceName'])

        return self

    def withDeployments(self, fields: List[str] = None) -> Self:
        """
        Retrieve the environments' deployments.
        """

        if not len(self.environments):
            return self

        env_names = [e['kubernetesNamespaceName'] for e in self.environments]

        batches = []
        for i in range(0, len(env_names), self.batch_size):
            batches.append(env_names[i:i+self.batch_size])

        envDeployments = {}
        for i, b in enumerate(batches):
            self.display.v(
                f"Fetching deployments for batch {i+1}/{len(batches)}")
            envDeployments.update(self.getDeployments(b, fields))

        for environment in self.environments:
            environment['deployments'] = envDeployments.get(
                environment['kubernetesNamespaceName'])

        return self

    def getCluster(self, env_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = gqlResourceBase.CLUSTER_FIELDS

        clusters = {}
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

            query = dsl_gql(DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")

            try:
                clusters = self.client.client.session.execute(query)
            except TransportQueryError as e:
                if isinstance(e.data, dict):
                    clusters = e.data
                    self.errors.extend(e.errors)
                else:
                    raise
            except Exception:
                raise

        for eName in env_names:
            try:
                res[eName] = clusters.get(
                    self.sanitiseForQueryAlias(eName))['kubernetes']
            except:
                res[eName] = None

        return res

    def getVariables(self, env_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = gqlResourceBase.VARIABLES_FIELDS

        variables = {}
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

            query = dsl_gql(DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")

            try:
                variables = self.client.client.session.execute(query)
            except TransportQueryError as e:
                if isinstance(e.data, dict):
                    variables = e.data
                    self.errors.extend(e.errors)
                else:
                    raise
            except Exception:
                raise

        for eName in env_names:
            try:
                res[eName] = variables.get(
                    self.sanitiseForQueryAlias(eName))['envVariables']
            except:
                res[eName] = None

        return res

    def getProject(self, env_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = gqlResourceBase.PROJECT_FIELDS

        projects = {}
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

            query = dsl_gql(DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")

            try:
                projects = self.client.client.session.execute(query)
            except TransportQueryError as e:
                if isinstance(e.data, dict):
                    projects = e.data
                    self.errors.extend(e.errors)
                else:
                    raise
            except Exception:
                raise

        for eName in env_names:
            try:
                res[eName] = projects.get(
                    self.sanitiseForQueryAlias(eName))['project']
            except:
                res[eName] = None

        return res

    def getDeployments(self, env_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = gqlResourceBase.DEPLOYMENTS_FIELDS

        deployments = {}
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

            query = dsl_gql(DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")

            try:
                deployments = self.client.client.session.execute(query)
            except TransportQueryError as e:
                if isinstance(e.data, dict):
                    deployments = e.data
                    self.errors.extend(e.errors)
                else:
                    raise
            except Exception:
                raise

        for eName in env_names:
            try:
                res[eName] = deployments.get(
                    self.sanitiseForQueryAlias(eName))['deployments']
            except:
                res[eName] = None

        return res
