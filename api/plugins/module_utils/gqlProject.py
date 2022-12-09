from ansible_collections.lagoon.api.plugins.module_utils.gqlResourceBase import CLUSTER_FIELDS, DEFAULT_BATCH_SIZE, ENVIRONMENTS_FIELDS, PROJECT_FIELDS, ResourceBase, VARIABLES_FIELDS
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from gql.dsl import DSLQuery, dsl_gql
from gql.transport.exceptions import TransportQueryError
from graphql import print_ast
from typing import List
from typing_extensions import Self

PROJECT_DEPLOY_TARGET_CONFIGS_FIELDS = [
    'id',
    'weight',
    'branches',
    'pullrequests',
    'deployTarget',
]

PROJECT_GROUPS_FIELDS = [
    'id',
    'name',
    'type',
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
            fields = PROJECT_FIELDS

        return self.queryTopLevelFields(
            self.projects, 'allProjects', 'Project', fields=fields)

    def allInGroup(self, group: str, fields: List[str] = None) -> Self:
        """
        Get a list of all projects in a group.
        """

        if not fields:
            fields = PROJECT_FIELDS

        args = {"input": {"name": group}}
        return self.queryTopLevelFields(
            self.projects, 'allProjectsInGroup', 'Project', args, fields)

    def byName(self, name: str, fields: List[str] = None) -> Self:
        """
        Get the top-level information for a project.
        """

        if not fields:
            fields = PROJECT_FIELDS

        args = {"name": name}
        return self.queryTopLevelFields(
            self.projects, 'projectByName', 'Project', args, fields)

    def withCluster(self, fields: List[str] = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Self:
        """
        Retrieve cluster information for the projects.
        """

        if not len(self.projects):
            return self

        project_names = [p['name'] for p in self.projects]

        batches = []
        for i in range(0, len(project_names), batch_size):
            batches.append(project_names[i:i+batch_size])

        clusters = {}
        for i, b in enumerate(batches):
            self.display.v(f"Fetching cluster for batch {i+1}/{len(batches)}")
            clusters.update(self.getCluster(b, fields))

        for project in self.projects:
            project['kubernetes'] = clusters.get(project['name'])
            project['openshift'] = clusters.get(project['name'])

        return self

    def withEnvironments(self, fields: List[str] = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Self:
        """
        Retrieve the projects' environments.
        """

        if not len(self.projects):
            return self

        project_names = [p['name'] for p in self.projects]

        batches = []
        for i in range(0, len(project_names), batch_size):
            batches.append(project_names[i:i+batch_size])

        environments = {}
        for i, b in enumerate(batches):
            self.display.v(f"Fetching environments for batch {i+1}/{len(batches)}")
            environments.update(self.getEnvironments(b, fields))

        for project in self.projects:
            project['environments'] = environments.get(project['name'])

        return self

    def withDeployTargetConfigs(self, fields: List[str] = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Self:
        """
        Retrieve the projects' deploy target configs.
        """

        if not len(self.projects):
            return self

        project_names = [p['name'] for p in self.projects]

        batches = []
        for i in range(0, len(project_names), batch_size):
            batches.append(project_names[i:i+batch_size])

        dtcs = {}
        for i, b in enumerate(batches):
            self.display.v(f"Fetching deploy target configs for batch {i+1}/{len(batches)}")
            dtcs.update(self.getDeployTargetConfigs(b, fields))

        for project in self.projects:
            project['deployTargetConfigs'] = dtcs.get(project['name'])

        return self

    def withVariables(self, fields: List[str] = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Self:
        """
        Retrieve the projects' variables.
        """

        if not len(self.projects):
            return self

        project_names = [p['name'] for p in self.projects]

        batches = []
        for i in range(0, len(project_names), batch_size):
            batches.append(project_names[i:i+batch_size])

        projectVars = {}
        for i, b in enumerate(batches):
            self.display.v(f"Fetching variables for batch {i+1}/{len(batches)}")
            projectVars.update(self.getVariables(b, fields))

        for project in self.projects:
            project['envVariables'] = projectVars.get(project['name'])

        return self

    def withGroups(self, fields: List[str] = None, batch_size: int = DEFAULT_BATCH_SIZE) -> Self:
        """
        Retrieve the projects' groups.
        """

        if not len(self.projects):
            return self

        project_names = [p['name'] for p in self.projects]

        batches = []
        for i in range(0, len(project_names), batch_size):
            batches.append(project_names[i:i+batch_size])

        groups = {}
        for i, b in enumerate(batches):
            self.display.v(f"Fetching groups for batch {i+1}/{len(batches)}")
            groups.update(self.getGroups(b, fields))

        for project in self.projects:
            project['groups'] = groups.get(project['name'])

        return self

    def getCluster(self, project_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = CLUSTER_FIELDS

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
                if isinstance(e.data, dict):
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

    def getEnvironments(self, project_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = ENVIRONMENTS_FIELDS

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
                if isinstance(e.data, dict):
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

    def getDeployTargetConfigs(self, project_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = PROJECT_DEPLOY_TARGET_CONFIGS_FIELDS

        dtcs = {}
        with self.client as (_, ds):
            # Build the fragment.
            dtc_fields = ds.Project.deployTargetConfigs.select(
                getattr(ds.DeployTargetConfig, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    if f == 'deployTarget':
                        continue
                    dtc_fields.select(getattr(ds.DeployTargetConfig, f))

                if 'deployTarget' in fields:
                    dtc_fields.select(ds.DeployTargetConfig.deployTarget.select(
                        ds.Kubernetes.id,
                        ds.Kubernetes.name,
                    ))

            field_queries = []
            for pName in project_names:
                # Build the main query.
                field_query = ds.Query.projectByName.args(
                    name=pName).alias(self.sanitiseForQueryAlias(pName))
                field_query.select(dtc_fields)
                field_queries.append(field_query)

            query = dsl_gql(DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")

            try:
                dtcs = self.client.client.session.execute(query)
            except TransportQueryError as e:
                if isinstance(e.data, dict):
                    dtcs = e.data
                    self.errors.extend(e.errors)
                else:
                    raise
            except Exception:
                raise

        for pName in project_names:
            try:
                res[pName] = dtcs.get(
                    self.sanitiseForQueryAlias(pName))['deployTargetConfigs']
            except:
                res[pName] = None

        return res

    def getVariables(self, project_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = VARIABLES_FIELDS

        variables = {}
        with self.client as (_, ds):
            # Build the fragment.
            var_fields = ds.Project.envVariables.select(
                getattr(ds.EnvKeyValue, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    var_fields.select(getattr(ds.EnvKeyValue, f))

            field_queries = []
            for pName in project_names:
                # Build the main query.
                field_query = ds.Query.projectByName.args(
                    name=pName).alias(self.sanitiseForQueryAlias(pName))
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

        for pName in project_names:
            try:
                res[pName] = variables.get(
                    self.sanitiseForQueryAlias(pName))['envVariables']
            except:
                res[pName] = None

        return res

    def getGroups(self, project_names: List[str], fields: List[str] = None) -> List[dict]:
        res = {}

        if not fields or not len(fields):
            fields = PROJECT_GROUPS_FIELDS

        groups = {}
        with self.client as (_, ds):
            # Build the fragment.
            groups_fields = ds.Project.groups.select(
                getattr(ds.GroupInterface, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    groups_fields.select(getattr(ds.GroupInterface, f))

            field_queries = []
            for pName in project_names:
                # Build the main query.
                field_query = ds.Query.projectByName.args(
                    name=pName).alias(self.sanitiseForQueryAlias(pName))
                field_query.select(groups_fields)
                field_queries.append(field_query)

            query = dsl_gql(DSLQuery(*field_queries))
            self.display.vvvv(f"Built query: \n{print_ast(query)}")

            try:
                groups = self.client.client.session.execute(query)
            except TransportQueryError as e:
                if isinstance(e.data, dict):
                    groups = e.data
                    self.errors.extend(e.errors)
                else:
                    raise
            except Exception:
                raise

        for pName in project_names:
            try:
                res[pName] = groups.get(
                    self.sanitiseForQueryAlias(pName))['groups']
            except:
                res[pName] = None

        return res
