from .gqlResourceBase import (
    CLUSTER_FIELDS,
    DEPLOYMENTS_FIELDS,
    ENVIRONMENTS_FIELDS,
    PROJECT_FIELDS,
    ResourceBase,
    VARIABLES_FIELDS,
)
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

    def all(self, fields: List[str] = None, batch_size: int = None) -> Self:
        """
        Get a list of all environments, but only top level fields.

        This method first tries using the allEnvironments query, and if it fails
        due to lack of permissions, it fetches all projects instead.
        """

        self.warnIfBatchSize(batch_size, "environment")

        if not fields:
            fields = ENVIRONMENTS_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    allEnvironments {{
        {joined_fields}
    }}
}}"""

        try:
            res = self.client.execute_query(query)
            self.environments.extend(res["allEnvironments"])
        except TransportQueryError as e:
            self.v(f"{e.errors}")
            if (
                e.errors[0]["message"]
                == 'Unauthorized: You don\'t have permission to "viewAll" on "environment": {}'
            ):
                return self.allThroughProjects(fields)
            elif e.data and isinstance(e.data["allEnvironments"], list):
                self.environments.extend(e.data["allEnvironments"])
                self.errors.extend(e.errors)
            else:
                raise
        except Exception:
            raise

        return self

    def allThroughProjects(
        self, fields: List[str] = None, batch_size: int = None
    ) -> Self:
        """
        Get a list of all environments, but going through projects first.
        """

        self.warnIfBatchSize(batch_size, "environment")

        projects = (
            Project(self.client, self.options).all().withEnvironments(fields).projects
        )

        for p in projects:
            self.environments.extend(p["environments"])

        return self

    def byNs(self, ns: str, fields: List[str] = None) -> Self:
        """
        Get the top-level information for an environment by k8s namespace.
        """

        if not fields:
            fields = ENVIRONMENTS_FIELDS

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    environmentByKubernetesNamespaceName (kubernetesNamespaceName: "{ns}") {{
        {joined_fields}
    }}
}}"""

        try:
            res = self.client.execute_query(query)
            if res["environmentByKubernetesNamespaceName"] != None:
                self.environments.append(res["environmentByKubernetesNamespaceName"])
        except TransportQueryError as e:
            if e.data and isinstance(
                e.data["environmentByKubernetesNamespaceName"], list
            ):
                self.environments.append(e.data["environmentByKubernetesNamespaceName"])
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
    environmentById (id: "{id}") {{
        {joined_fields}
    }}
}}"""

        try:
            res = self.client.execute_query(query)
            if res["environmentById"] != None:
                self.environments.append(res["environmentById"])
        except TransportQueryError as e:
            if e.data and isinstance(e.data["environmentById"], list):
                self.environments.append(e.data["environmentById"])
                self.errors.extend(e.errors)
            else:
                raise
        except Exception:
            raise

        return self

    def withCluster(self, fields: List[str] = None, batch_size: int = None) -> Self:
        """
        Retrieve cluster information for the environments.

        One query per environment - see warnIfBatchSize for why batching was
        removed.
        """

        self.warnIfBatchSize(batch_size, "environment")

        if not len(self.environments):
            return self

        total = len(self.environments)
        self.v(f"Fetching cluster for {total} environments")

        # Hold a single session open for the whole loop so the underlying
        # requests.Session - and therefore the HTTP connection - is reused.
        with self.client:
            for i, environment in enumerate(self.environments):
                ns = environment["kubernetesNamespaceName"]
                self.vv(f"Fetching cluster for {ns} ({i + 1}/{total})")
                cluster = self.getCluster(ns, fields)
                environment["kubernetes"] = cluster
                environment["openshift"] = cluster
                self.raiseExceptionIfRequired("Error fetching environment cluster")

        return self

    def withVariables(self, fields: List[str] = None, batch_size: int = None) -> Self:
        """
        Retrieve the environments' variables.
        """

        self.warnIfBatchSize(batch_size, "environment")

        if not len(self.environments):
            return self

        total = len(self.environments)
        self.v(f"Fetching variables for {total} environments")

        with self.client:
            for i, environment in enumerate(self.environments):
                ns = environment["kubernetesNamespaceName"]
                self.vv(f"Fetching variables for {ns} ({i + 1}/{total})")
                environment["envVariables"] = self.getVariables(ns, fields)
                self.raiseExceptionIfRequired("Error fetching environment variables")

        return self

    def withProject(self, fields: List[str] = None, batch_size: int = None) -> Self:
        """
        Retrieve the environments' project.
        """

        self.warnIfBatchSize(batch_size, "environment")

        if not len(self.environments):
            return self

        total = len(self.environments)
        self.v(f"Fetching project for {total} environments")

        with self.client:
            for i, environment in enumerate(self.environments):
                ns = environment["kubernetesNamespaceName"]
                self.vv(f"Fetching project for {ns} ({i + 1}/{total})")
                environment["project"] = self.getProject(ns, fields)
                self.raiseExceptionIfRequired("Error fetching environment project")

        return self

    def withDeployments(self, fields: List[str] = None, batch_size: int = None) -> Self:
        """
        Retrieve the environments' deployments.
        """

        self.warnIfBatchSize(batch_size, "environment")

        if not len(self.environments):
            return self

        total = len(self.environments)
        self.v(f"Fetching deployments for {total} environments")

        with self.client:
            for i, environment in enumerate(self.environments):
                ns = environment["kubernetesNamespaceName"]
                self.vv(f"Fetching deployments for {ns} ({i + 1}/{total})")
                environment["deployments"] = self.getDeployments(ns, fields)
                self.raiseExceptionIfRequired("Error fetching deployments")

        return self

    def getCluster(self, env_name: str, fields: List[str] = None) -> dict:
        if not fields or not len(fields):
            fields = CLUSTER_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            cluster_fields = ds.Environment.kubernetes.select(
                getattr(ds.Kubernetes, fields[0])
            )
            if len(fields) > 1:
                for f in fields[1:]:
                    cluster_fields.select(getattr(ds.Kubernetes, f))

            # Build the main query. No alias: a single root field per request
            # means the response is keyed by the query name itself.
            field_query = ds.Query.environmentByKubernetesNamespaceName.args(
                kubernetesNamespaceName=env_name
            )
            field_query.select(cluster_fields)

            resources = self.queryResources(DSLQuery(field_query))

        try:
            return resources["environmentByKubernetesNamespaceName"]["kubernetes"]
        except (KeyError, TypeError):
            return None

    def getVariables(self, env_name: str, fields: List[str] = None) -> List[dict]:
        if not fields or not len(fields):
            fields = VARIABLES_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            var_fields = ds.Environment.envVariables.select(
                getattr(ds.EnvKeyValue, fields[0])
            )
            if len(fields) > 1:
                for f in fields[1:]:
                    var_fields.select(getattr(ds.EnvKeyValue, f))

            # Build the main query.
            field_query = ds.Query.environmentByKubernetesNamespaceName.args(
                kubernetesNamespaceName=env_name
            )
            field_query.select(var_fields)

            # Read path: the response holds every variable value for this
            # environment, none of them known in advance, so redacting()
            # cannot mask them - this one has to stay muted. Do not "finish
            # the migration" to redacting() here.
            with self.client.silenced():
                resources = self.queryResources(DSLQuery(field_query))

        try:
            return resources["environmentByKubernetesNamespaceName"]["envVariables"]
        except (KeyError, TypeError):
            return None

    def getProject(self, env_name: str, fields: List[str] = None) -> dict:
        if not fields or not len(fields):
            fields = PROJECT_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            project_fields = ds.Environment.project.select(
                getattr(ds.Project, fields[0])
            )
            if len(fields) > 1:
                for f in fields[1:]:
                    project_fields.select(getattr(ds.Project, f))

            # Build the main query.
            field_query = ds.Query.environmentByKubernetesNamespaceName.args(
                kubernetesNamespaceName=env_name
            )
            field_query.select(project_fields)

            resources = self.queryResources(DSLQuery(field_query))

        try:
            return resources["environmentByKubernetesNamespaceName"]["project"]
        except (KeyError, TypeError):
            return None

    def getDeployments(self, env_name: str, fields: List[str] = None) -> List[dict]:
        if not fields or not len(fields):
            fields = DEPLOYMENTS_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            deployment_fields = ds.Environment.deployments.select(
                getattr(ds.Deployment, fields[0])
            )
            if len(fields) > 1:
                for f in fields[1:]:
                    deployment_fields.select(getattr(ds.Deployment, f))

            # Build the main query.
            field_query = ds.Query.environmentByKubernetesNamespaceName.args(
                kubernetesNamespaceName=env_name
            )
            field_query.select(deployment_fields)

            resources = self.queryResources(DSLQuery(field_query))

        try:
            return resources["environmentByKubernetesNamespaceName"]["deployments"]
        except (KeyError, TypeError):
            return None

    def delete(self, project_name: str, environment_name: str) -> bool:
        res = self.client.execute_query(
            """
            mutation deleteEnvironment($project_name: String!, $environment_name: String!) {
                deleteEnvironment(input: { project: $project_name, name: $environment_name })
            }
        """,
            {"project_name": project_name, "environment_name": environment_name},
        )
        if "errors" in res:
            raise AnsibleError("Unable to delete environment.", res["errors"])

        return res["deleteEnvironment"] == "success"

    def update(self, environment_id: int, patch: dict) -> dict:
        res = self.client.execute_query(
            """
            mutation updateEnvironment($id: Int!, $patch: UpdateEnvironmentPatchInput) {
                updateEnvironment(input: { id: $id, patch: $patch }) {
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
            }
        """,
            {"id": environment_id, "patch": patch},
        )

        return res["updateEnvironment"]

    def deployBranch(
        self,
        project: str,
        branch: str,
        bulkId: str,
        bulkName: str,
        wait: bool = False,
        delay: int = 60,
        retries: int = 30,
    ) -> str:
        mutation = """
        mutation deploy($project: String!, $branch: String!, $bulkId: String, $bulkName: String) {
            deployEnvironmentBranch (input: {
                project: { name: $project },
                branchName: $branch,
                bulkId: $bulkId,
                bulkName: $bulkName,
            })
        }"""

        mutation_vars = {
            "project": project,
            "branch": branch,
            "bulkId": bulkId,
            "bulkName": bulkName,
        }

        res = self.client.execute_query(mutation, mutation_vars)
        if "errors" in res:
            raise AnsibleError("Unable to deploy branch.", res["errors"])

        if not wait:
            return res["deployEnvironmentBranch"]

        env_ns = self.sanitisedName(f"{project}-{branch}")
        return self.checkDeployStatus(env_ns, wait, delay, retries)

    def checkDeployStatus(
        self,
        env_ns: str,
        wait: bool = False,
        delay: int = 60,
        retries: int = 30,
        current_try: int = 1,
    ):
        sleep(delay)

        deployments = self.getDeployments(env_ns)

        if not wait or (
            len(deployments)
            and "status" in deployments[0]
            and deployments[0]["status"] in ["complete", "failed", "new", "cancelled"]
        ):
            return deployments[0]["status"]

        if retries - current_try == 0:
            raise AnsibleError(
                "Maximium number of retries reached; view deployment logs for more information."
            )

        self.info(
            f"\033[30;1mRETRYING: Wait for deployment completion for {env_ns} ({retries - current_try} retries left).\033[0m"
        )
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
        if "errors" in res:
            raise AnsibleError("Unable to create bulk deployment.", res["errors"])
        return res["bulkDeployEnvironmentLatest"]
