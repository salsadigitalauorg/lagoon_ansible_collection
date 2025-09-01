from __future__ import annotations

import datetime
try:
    import json
except ImportError:
    import simplejson as json
import socket
import traceback

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase

class ActionModule(ActionBase):
    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)

        server = self._task.args.get("server", "application-logs.lagoon.svc")
        port = self._task.args.get("port", 5140)
        self.lagoon_log_endpoint = (server, port)

        self.hostname = socket.gethostname()
        self.base_data = {
            '@timestamp': self.format_current_timestamp(),
            'logger_name': "lagoon_ansible_collection",
            'host': self.hostname
        }

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        try:
            data = self.base_data.copy()
            data['message'] = self._task.args.get("message")
            data['level'] = self._task.args.get("level", "info").upper().strip()
            data['host'] = self._task.args.get("host", self.hostname)

            has_context = False
            context_data = self._task.args.get("context", None)
            if context_data and isinstance(context_data, dict):
                data['context'] = context_data
                has_context = True

            has_extra = False
            extra_data = self._task.args.get("extra", None)
            if extra_data and isinstance(extra_data, dict):
                data['extra'] = extra_data
                has_extra = True

            log_type = self._task.args.get("namespace", None)
            if log_type:
                if isinstance(log_type, str):
                    data['type'] = log_type
                else:
                    raise AnsibleError("Namespace must be a string")
            elif has_context or has_extra:
                raise AnsibleError("Namespace is required when context or extra data is set")

            # Lagoon log dispatcher (Fluent) only accepts JSON payload for UDP.
            # See https://github.com/uselagoon/lagoon-charts/blob/main/charts/lagoon-logging/templates/logs-dispatcher.service.yaml#L28
            # See https://github.com/uselagoon/lagoon-charts/blob/main/charts/lagoon-logging/templates/logs-dispatcher.fluent-conf.configmap.yaml#L43
            # To test from CLI:
            # echo '{"message":"Test lagoon_log message"}' | nc -u -v -w3 application-logs.lagoon.svc 5140
            # echo '{"message":"Test lagoon_log message", "type": "lagoon-logging", "extra": {"project": "testing"}}' > /dev/udp/application-logs.lagoon.svc/5140
            log_message = json.dumps(data)
            self._display.v("Log message: %s" % log_message)

            # Send the JSON payload via UDP socket.
            log_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            log_socket.sendto(bytes(log_message, "utf-8") + b"\n", self.lagoon_log_endpoint)
        except Exception:
            self._display.warning("Unable to send a log message to Lagoon Logs.")
            self._display.v(traceback.format_exc())

        return result

    @classmethod
    def format_current_timestamp(cls):
        tstamp = datetime.datetime.now(datetime.timezone.utc)
        return tstamp.strftime("%Y-%m-%dT%H:%M:%S") + ".%03d" % (tstamp.microsecond / 1000) + "Z"

