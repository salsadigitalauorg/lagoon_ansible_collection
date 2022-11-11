from jinja2 import environment
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible_collections.lagoon.api.plugins.module_utils.gqlResourceBase import ResourceBase
from gql.dsl import DSLQuery, dsl_gql
from gql.transport.exceptions import TransportQueryError
from graphql import print_ast
from typing import List
from typing_extensions import Self

PROJECT_DEFAULT_FIELDS = [
    'autoIdle',
    'availability',
    'branches',
    'created',
    'deploymentsDisabled',
    'developmentBuildPriority',
    'developmentEnvironmentsLimit',
    'gitUrl',
    'id',
    'metadata',
    'name',
    'openshiftProjectName',
    'openshiftProjectPattern',
    'productionAlias',
    'productionBuildPriority',
    'productionEnvironment',
    'productionRoutes',
    'pullrequests',
    'routerPattern',
    'standbyAlias',
    'standbyProductionEnvironment',
    'standbyRoutes',
]

PROJECT_CLUSTER_FIELDS = [
    'id',
    'name',
]

PROJECT_ENVIRONMENTS_FIELDS = [
    'id',
    'name',
    'kubernetesNamespaceName',
    'environmentType',
    'routes',
]


class Project(ResourceBase):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)
        self.projects = []

    def all(self, fields: List[str] = None) -> Self:
        """
        Get a list of all projects, but only top level fields.

        We avoid making nested queries since that takes a lot longer to
        evaluate on the server side and often results in failed queries.
        """

        if not fields:
            fields = PROJECT_DEFAULT_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    allProjects {{
        { joined_fields }
    }}
}}"""

        self.display.vvvv(f"{ query }")

        try:
            res = self.client.execute_query(query)
            self.projects.extend(res['allProjects'])
        except TransportQueryError as e:
            if len(e.data):
                self.projects.extend(e.data['allProjects'])
                self.errors.extend(e.errors)
            else:
                raise
        except Exception:
            raise

        return self

    def allInGroup(self, group: str, fields: List[str] = None) -> Self:
        """
        Get a list of all projects in a group.
        """

        if not fields:
            fields = PROJECT_DEFAULT_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    allProjectsInGroup (input: {{ name: "{ group }" }}) {{
        { joined_fields }
    }}
}}"""

        self.display.vvvv(f"{ query }")

        try:
            res = self.client.execute_query(query)
            self.projects.extend(res['allProjectsInGroup'])
        except TransportQueryError as e:
            if len(e.data):
                self.projects.extend(e.data['allProjectsInGroup'])
                self.errors.extend(e.errors)
            else:
                raise
        except Exception:
            raise

        return self

    def byName(self, name: str, fields: List[str] = None) -> Self:
        """
        Get the top-level information for a project.
        """

        if not fields:
            fields = PROJECT_DEFAULT_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    projectByName (name: "{ name }") {{
        { joined_fields }
    }}
}}"""

        self.display.vvvv(f"{ query }")

        try:
            res = self.client.execute_query(query)
            self.projects.append(res['projectByName'])
        except TransportQueryError as e:
            if len(e.data):
                self.projects.append(e.data['projectByName'])
                self.errors.extend(e.errors)
            else:
                raise
        except Exception:
            raise

        return self

    def withCluster(self, fields: List[str] = None) -> Self:
        """
        Retrieve cluster information for the projects.
        """

        if not len(self.projects):
            return self

        project_names = [p['name'] for p in self.projects]

        batches = []
        for i in range(0, len(project_names), self.batch_size):
            batches.append(project_names[i:i+self.batch_size])

        clusters = {}
        for i, b in enumerate(batches):
            self.display.v(f"Fetching cluster for batch {i+1}/{len(batches)}")
            clusters.update(self.getClusterForProjects(b, fields))

        for project in self.projects:
            project['kubernetes'] = clusters.get(project['name'])
            project['openshift'] = clusters.get(project['name'])

        return self

    def withEnvironments(self, fields: List[str] = None) -> Self:
        """
        Retrieve the projects' environments.
        """

        if not len(self.projects):
            return self

        project_names = [p['name'] for p in self.projects]

        batches = []
        for i in range(0, len(project_names), self.batch_size):
            batches.append(project_names[i:i+self.batch_size])

        environments = {}
        for i, b in enumerate(batches):
            self.display.v(f"Fetching environments for batch {i+1}/{len(batches)}")
            environments.update(self.getEnvironmentsForProjects(b, fields))

        for project in self.projects:
            project['environments'] = environments.get(project['name'])

        return self

    def getClusterForProjects(self, project_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = PROJECT_CLUSTER_FIELDS

        clusters = {}
        with self.client as (_, ds):
            # Build the fragment.
            cluster_fields = ds.Project.kubernetes.select(
                getattr(ds.Kubernetes, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    cluster_fields.select(getattr(ds.Kubernetes, f))

            field_queries = []
            for pName in project_names:
                # Build the main query.
                field_query = ds.Query.projectByName.args(
                    name=pName).alias(self.sanitiseForQueryAlias(pName))
                field_query.select(cluster_fields)
                field_queries.append(field_query)

            query = dsl_gql(DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")

            try:
                clusters = self.client.client.session.execute(query)
            except TransportQueryError as e:
                if len(e.data):
                    clusters = e.data
                    self.errors.extend(e.errors)
                else:
                    raise
            except Exception:
                raise

        for pName in project_names:
            try:
                res[pName] = clusters.get(
                    self.sanitiseForQueryAlias(pName))['kubernetes']
            except:
                res[pName] = None

        return res

    def getEnvironmentsForProjects(self, project_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = PROJECT_ENVIRONMENTS_FIELDS

        environments = {}
        with self.client as (_, ds):
            # Build the fragment.
            env_fields = ds.Project.environments.select(
                getattr(ds.Environment, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    env_fields.select(getattr(ds.Environment, f))

            field_queries = []
            for pName in project_names:
                # Build the main query.
                field_query = ds.Query.projectByName.args(
                    name=pName).alias(self.sanitiseForQueryAlias(pName))
                field_query.select(env_fields)
                field_queries.append(field_query)

            query = dsl_gql(DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")

            try:
                environments = self.client.client.session.execute(query)
            except TransportQueryError as e:
                if len(e.data):
                    environments = e.data
                    self.errors.extend(e.errors)
                else:
                    raise
            except Exception:
                raise

        for pName in project_names:
            try:
                res[pName] = environments.get(
                    self.sanitiseForQueryAlias(pName))['environments']
            except:
                res[pName] = None

        return res
