from .gqlResourceBase import CLUSTER_FIELDS
from .gqlResourceBase import ENVIRONMENTS_FIELDS
from .gqlResourceBase import PROJECT_FIELDS, ResourceBase
from .gql import GqlClient
from .gqlVariable import Variable
from .gqlGroup import Group

from gql.dsl import DSLQuery
from typing import List
from typing_extensions import Self

PROJECT_DEPLOY_TARGET_CONFIGS_FIELDS = [
    "id",
    "weight",
    "branches",
    "pullrequests",
    "deployTarget",
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
            self.projects, "allProjects", "Project", fields=fields
        )

    def allInGroup(self, group: str, fields: List[str] = None) -> Self:
        """
        Get a list of all projects in a group.
        """

        if not fields:
            fields = PROJECT_FIELDS

        args = {"input": {"name": group}}
        return self.queryTopLevelFields(
            self.projects, "allProjectsInGroup", "Project", args, fields
        )

    def byName(self, name: str, fields: List[str] = None) -> Self:
        """
        Get the top-level information for a project.
        """

        if not fields:
            fields = PROJECT_FIELDS

        args = {"name": name}
        return self.queryTopLevelFields(
            self.projects, "projectByName", "Project", args, fields
        )

    def withCluster(self, fields: List[str] = None, batch_size: int = None) -> Self:
        """
        Retrieve cluster information for the projects.

        One query per project - see warnIfBatchSize for why batching was removed.
        """

        self.warnIfBatchSize(batch_size, "project")

        if not len(self.projects):
            return self

        total = len(self.projects)
        self.v(f"Fetching cluster for {total} projects")

        # Hold a single session open for the whole loop so the underlying
        # requests.Session - and therefore the HTTP connection - is reused.
        with self.client:
            for i, project in enumerate(self.projects):
                name = project["name"]
                self.vv(f"Fetching cluster for {name} ({i + 1}/{total})")
                cluster = self.getCluster(name, fields)
                project["kubernetes"] = cluster
                project["openshift"] = cluster
                self.raiseExceptionIfRequired("Error fetching project cluster")

        return self

    def withEnvironments(
        self, fields: List[str] = None, batch_size: int = None
    ) -> Self:
        """
        Retrieve the projects' environments.
        """

        self.warnIfBatchSize(batch_size, "project")

        if not len(self.projects):
            return self

        total = len(self.projects)
        self.v(f"Fetching environments for {total} projects")

        with self.client:
            for i, project in enumerate(self.projects):
                name = project["name"]
                self.vv(f"Fetching environments for {name} ({i + 1}/{total})")
                project["environments"] = self.getEnvironments(name, fields)
                self.raiseExceptionIfRequired("Error fetching environments")

        return self

    def withDeployTargetConfigs(
        self, fields: List[str] = None, batch_size: int = None
    ) -> Self:
        """
        Retrieve the projects' deploy target configs.
        """

        self.warnIfBatchSize(batch_size, "project")

        if not len(self.projects):
            return self

        total = len(self.projects)
        self.v(f"Fetching deploy target configs for {total} projects")

        with self.client:
            for i, project in enumerate(self.projects):
                name = project["name"]
                self.vv(f"Fetching deploy target configs for {name} ({i + 1}/{total})")
                project["deployTargetConfigs"] = self.getDeployTargetConfigs(
                    name, fields
                )
                self.raiseExceptionIfRequired("Error fetching deploy target configs")

        return self

    def withVariables(self, fields: List[str] = None, batch_size: int = None) -> Self:
        """
        Retrieve the projects' variables.
        """

        self.warnIfBatchSize(batch_size, "project")

        if not len(self.projects):
            return self

        total = len(self.projects)
        self.v(f"Fetching variables for {total} projects")

        variables = Variable(self.client, self.options)
        with self.client:
            for i, project in enumerate(self.projects):
                name = project["name"]
                self.vv(f"Fetching variables for {name} ({i + 1}/{total})")
                project["envVariables"] = variables.getForProject(name, fields)
                # Errors accumulate on the Variable instance, not this one.
                self.errors.extend(variables.errors)
                variables.errors.clear()
                self.raiseExceptionIfRequired("Error fetching project variables")

        return self

    def withGroups(self, fields: List[str] = None, batch_size: int = None) -> Self:
        """
        Retrieve the projects' groups.
        """

        self.warnIfBatchSize(batch_size, "project")

        if not len(self.projects):
            return self

        total = len(self.projects)
        self.v(f"Fetching groups for {total} projects")

        grouper = Group(self.client, self.options)
        with self.client:
            for i, project in enumerate(self.projects):
                name = project["name"]
                self.vv(f"Fetching groups for {name} ({i + 1}/{total})")
                project["groups"] = grouper.get(name, fields)
                # Errors accumulate on the Group instance, not this one.
                self.errors.extend(grouper.errors)
                grouper.errors.clear()
                self.raiseExceptionIfRequired("Error fetching groups")

        return self

    def getCluster(self, project_name: str, fields: List[str] = None) -> dict:
        if not fields or not len(fields):
            fields = CLUSTER_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            cluster_fields = ds.Project.kubernetes.select(
                getattr(ds.Kubernetes, fields[0])
            )
            if len(fields) > 1:
                for f in fields[1:]:
                    cluster_fields.select(getattr(ds.Kubernetes, f))

            # Build the main query. No alias: a single root field per request
            # means the response is keyed by the query name itself.
            field_query = ds.Query.projectByName.args(name=project_name)
            field_query.select(cluster_fields)

            resources = self.queryResources(DSLQuery(field_query))

        try:
            return resources["projectByName"]["kubernetes"]
        except (KeyError, TypeError):
            return None

    def getEnvironments(
        self, project_name: str, fields: List[str] = None
    ) -> List[dict]:
        if not fields or not len(fields):
            fields = ENVIRONMENTS_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            env_fields = ds.Project.environments.select(
                getattr(ds.Environment, fields[0])
            )
            if len(fields) > 1:
                for f in fields[1:]:
                    env_fields.select(getattr(ds.Environment, f))

            # Build the main query.
            field_query = ds.Query.projectByName.args(name=project_name)
            field_query.select(env_fields)

            resources = self.queryResources(DSLQuery(field_query))

        try:
            return resources["projectByName"]["environments"]
        except (KeyError, TypeError):
            return None

    def getDeployTargetConfigs(
        self, project_name: str, fields: List[str] = None
    ) -> List[dict]:
        if not fields or not len(fields):
            fields = PROJECT_DEPLOY_TARGET_CONFIGS_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            dtc_fields = ds.Project.deployTargetConfigs.select(
                getattr(ds.DeployTargetConfig, fields[0])
            )
            if len(fields) > 1:
                for f in fields[1:]:
                    if f == "deployTarget":
                        continue
                    dtc_fields.select(getattr(ds.DeployTargetConfig, f))

                if "deployTarget" in fields:
                    dtc_fields.select(
                        ds.DeployTargetConfig.deployTarget.select(
                            ds.Kubernetes.id,
                            ds.Kubernetes.name,
                        )
                    )

            # Build the main query.
            field_query = ds.Query.projectByName.args(name=project_name)
            field_query.select(dtc_fields)

            resources = self.queryResources(DSLQuery(field_query))

        try:
            return resources["projectByName"]["deployTargetConfigs"]
        except (KeyError, TypeError):
            return None
