from __future__ import annotations

import datetime
try:
    import json
except ImportError:
    import simplejson as json
import socket
import traceback

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

            easy_types = (str, bool, float, int, type(None))

            extra_data = self._task.args.get("extra_data", None)
            if extra_data and isinstance(extra_data, dict):
                for key, value in extra_data.items():
                    # Do not override existing keys.
                    if key not in data:
                        if isinstance(value, easy_types):
                            data[key] = value
                        else:
                            data[key] = repr(value)

            # Lagoon log dispatcher (Fluent) only accepts JSON payload for UDP.
            # See https://github.com/uselagoon/lagoon-charts/blob/main/charts/lagoon-logging/templates/logs-dispatcher.service.yaml#L28
            # See https://github.com/uselagoon/lagoon-charts/blob/main/charts/lagoon-logging/templates/logs-dispatcher.fluent-conf.configmap.yaml#L43
            # To test from CLI:
            # echo '{"message":"Test lagoon_log message"}' | nc -u -v -w3 application-logs.lagoon.svc 5140
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

