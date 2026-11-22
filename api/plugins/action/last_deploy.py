import time

from ansible.errors import AnsibleError

from ..module_utils.display import Display
from ..modules.last_deploy import ARGUMENT_SPEC
from . import LagoonClientActionBase

TERMINAL_STATUSES = {"complete", "failed", "new", "cancelled"}


class ActionModule(LagoonClientActionBase):
    argSpec = ARGUMENT_SPEC

    def execute(self, args, lagoon, result):
        namespace = args["project"] + "-" + self.sanitiseBranch(args["branch"])
        wait = args["wait"]
        retries = args["retries"]

        result["changed"] = False

        for attempt in range(1, retries + 1):
            if wait:
                time.sleep(args["delay"])

            deployments = lagoon.getEnvironmentDeployments(namespace, limit=1)
            if deployments is None:
                raise AnsibleError(
                    f"Unable to get details for environment {namespace}; please "
                    "make sure the environment name is correct"
                )

            if not deployments:
                Display().v(f"Environment {namespace} has no deployments yet")
                deploy_status = None
            else:
                deploy_status = deployments[0].get("status")

            if not wait or deploy_status in TERMINAL_STATUSES:
                result["deploy_status"] = deploy_status
                return

            if attempt == retries:
                raise AnsibleError(
                    "Maximium number of retries reached; view deployment logs "
                    "for more information."
                )

    def sanitiseBranch(self, branch: str) -> str:
        return branch.replace("/", "-").replace("_", "-").replace(".", "-")
