import time

from ansible.plugins.action import ActionBase

from ..module_utils.auth import LagoonAuthError, LagoonCredentials


class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        grant = self._task.args.get("grant", False)

        ssh_host = self._templar.template(task_vars.get("lagoon_ssh_host"))
        ssh_port = self._templar.template(task_vars.get("lagoon_ssh_port"))
        ssh_options = self._task.args.get("ssh_options") or task_vars.get(
            "lagoon_ssh_options"
        )
        self._display.vvvv(
            f"lagoon_ssh_private_key_file: {task_vars.get('lagoon_ssh_private_key_file')}"
        )
        self._display.vvvv(f"lagoon ssh host/port: {ssh_host}:{ssh_port}")

        try:
            credentials = LagoonCredentials(
                ssh_private_key=task_vars.get("lagoon_ssh_private_key"),
                ssh_private_key_file=task_vars.get("lagoon_ssh_private_key_file"),
                ssh_host=ssh_host,
                ssh_port=ssh_port,
                ssh_options=ssh_options,
            )
            grant_token = credentials.grant()
        except LagoonAuthError as e:
            result["failed"] = True
            result["rc"] = e.rc
            result["error"] = e.diagnostic or str(e)
            result["msg"] = str(e)
            return result

        result["rc"] = 0
        if grant:
            grant_token["expiry_time"] = time.time() + grant_token["expires_in"]
            result["token"] = grant_token
        else:
            result["token"] = grant_token["access_token"]

        return result
