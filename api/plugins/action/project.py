from . import LagoonActionBase
from ..module_utils.gql import GqlClient
from ansible.utils.display import Display


display = Display()


def has_project(client: GqlClient, project):

    res = client.execute_query(
        """
        query project($name: String!) {
            projectByName(name: $name) {
                id
            }
        }
        """,
        {
            "name": project
        }
    )

    display.v(f"GraphQL query result: {res}")

    try:
        return res["projectByName"] is not None
    except (KeyError, TypeError):
        return False


def delete_project(client: GqlClient, project):

    res = client.execute_query(
        """
        mutation delete($name: String!) {
            deleteProject(input: {
                project: $name
            })
        }
        """,
        {
            "name": project
        }
    )

    try:
        return res["deleteProject"] == "success"
    except KeyError:
        return False


def add_project(
    client: GqlClient,
    name,
    gitUrl,
    productionEnvironment,
    subfolder=None,
    branches=None,
    pullrequests=None,
    openshift=1,
    standbyProductionEnvironment=None,
    autoIdle=1,
    developmentEnvironmentsLimit=5,
    problemsUi=0,
    factsUi=0
):

    # Excluded inputs:
    # $kubernetes: Int
    # $kubernetesNamespacePattern: String
    # $activeSystemsDeploy: String
    # $activeSystemsPromote: String
    # $activeSystemsRemove: String
    # $activeSystemsTask: String
    # $activeSystemsMisc: String
    # $routerPattern: String
    # $openshift: Int
    # $openshiftProjectPattern: String
    # $productionRoutes: String
    # $productionAlias: String
    # $standbyRoutes: String
    # $standbyAlias: String
    # $availability: ProjectAvailability
    # $privateKey: String
    # $storageCalc: Int
    # $deploymentsDisabled: Int
    # $productionBuildPriority: Int
    # $developmentBuildPriority: Int

    res = client.execute_query(
        """
        mutation addProject(
            $name: String!
            $gitUrl: String!
            $subfolder: String
            $branches: String
            $pullrequests: String
            $openshift: Int!
            $productionEnvironment: String!
            $standbyProductionEnvironment: String
            $autoIdle: Int
            $developmentEnvironmentsLimit: Int
            $problemsUi: Int
            $factsUi: Int
        ) {
            addProject(input: {
                name: $name
                gitUrl: $gitUrl
                subfolder: $subfolder
                branches: $branches
                pullrequests: $pullrequests
                openshift: $openshift
                productionEnvironment: $productionEnvironment
                standbyProductionEnvironment: $standbyProductionEnvironment
                autoIdle: $autoIdle
                developmentEnvironmentsLimit: $developmentEnvironmentsLimit
                problemsUi: $problemsUi
                factsUi: $factsUi
            }) {
                id
            }
        }""",
        {
            "name": name,
            "gitUrl": gitUrl,
            "subfolder": subfolder,
            "branches": branches,
            "pullrequests": pullrequests,
            "openshift": int(openshift),
            "productionEnvironment": productionEnvironment,
            "standbyProductionEnvironment": standbyProductionEnvironment,
            "autoIdle": int(autoIdle),
            "developmentEnvironmentsLimit": int(developmentEnvironmentsLimit),
            "problemsUi": int(problemsUi),
            "factsUi": int(factsUi)
        }
    )

    display.v(f"GraphQL mutation result: {res}")
    return res["addProject"]


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp

        self._display.v("Task args: %s" % self._task.args)

        self.createClient(task_vars)

        # Modifier.
        state = self._task.args.get('state', 'present')

        name = self._task.args.get("name")
        gitUrl = self._task.args.get("git_url")
        subfolder = self._task.args.get("subfolder")
        branches = self._task.args.get("branches")
        pullrequests = self._task.args.get("pullrequests")
        openshift = self._task.args.get("openshift")
        productionEnvironment = self._task.args.get("production_environment")
        standbyProductionEnvironment = self._task.args.get("standby_production_environment")
        autoIdle = self._task.args.get("auto_idle", True)
        developmentEnvironmentsLimit = self._task.args.get("development_environments_limit", 5)
        problemsUi = self._task.args.get("problems_ui", False)
        factsUi = self._task.args.get("facts_ui", False)

        project = has_project(self.client, name)

        if state == "absent" and not project:
            result["changed"] = False
        elif state == "absent" and project:
            result["changed"] = True
            result["result"] = delete_project(self.client, name)
        elif state == "present" and project:
            result["changed"] = False
        else:
            result["changed"] = True
            result["result"] = add_project(
                self.client,
                name,
                gitUrl,
                productionEnvironment,
                subfolder,
                branches,
                pullrequests,
                openshift,
                standbyProductionEnvironment,
                autoIdle,
                developmentEnvironmentsLimit,
                problemsUi,
                factsUi
            )

        return result
