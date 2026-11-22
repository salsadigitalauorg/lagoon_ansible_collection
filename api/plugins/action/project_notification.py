from ansible.errors import AnsibleError

from ..modules.project_notification import ARGUMENT_SPEC
from . import LagoonClientActionBase


class ActionModule(LagoonClientActionBase):
    argSpec = ARGUMENT_SPEC

    def execute(self, args, lagoon, result):
        project = args["project"]
        notification = args["notification"]
        type = args["type"]
        state = args["state"]

        if state == "present":
            lagoon.addProjectNotification(
                project, notification, type, raise_on_error=False
            )
            if any("Duplicate" in str(e) for e in lagoon.errors):
                result["changed"] = False
                return
            if lagoon.errors:
                raise AnsibleError(f"Unable to add notification: {lagoon.errors}")
            result["changed"] = True
            return

        removed = lagoon.removeProjectNotification(
            project, notification, type, raise_on_error=False
        )
        if lagoon.errors:
            raise AnsibleError(f"Unable to remove notification: {lagoon.errors}")
        result["changed"] = removed is not None
