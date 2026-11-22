import unittest
from unittest.mock import MagicMock, patch

from ansible.errors import AnsibleError

from .....plugins.action.last_deploy import ActionModule


def action():
    return ActionModule.__new__(ActionModule)


ARGS = {"project": "p1", "branch": "master", "wait": False, "delay": 60, "retries": 3}


class NoDeploymentsTester(unittest.TestCase):
    def test_no_deployments_returns_cleanly_rather_than_indexerror(self):
        lagoon = MagicMock()
        lagoon.getEnvironmentDeployments.return_value = []

        result = {}
        action().execute(ARGS, lagoon, result)

        assert result["deploy_status"] is None
        assert result["changed"] is False

    def test_a_missing_environment_raises_with_the_existing_message(self):
        lagoon = MagicMock()
        lagoon.getEnvironmentDeployments.return_value = None

        with self.assertRaises(AnsibleError) as caught:
            action().execute(ARGS, lagoon, {})

        assert "p1-master" in str(caught.exception)

    def test_wait_false_performs_no_sleep(self):
        lagoon = MagicMock()
        lagoon.getEnvironmentDeployments.return_value = [{"status": "complete"}]

        with patch("time.sleep") as sleep:
            action().execute(ARGS, lagoon, {})
            sleep.assert_not_called()

    def test_limit_1_is_used(self):
        lagoon = MagicMock()
        lagoon.getEnvironmentDeployments.return_value = [{"status": "complete"}]

        action().execute(ARGS, lagoon, {})

        lagoon.getEnvironmentDeployments.assert_called_once_with("p1-master", limit=1)

    def test_a_terminal_status_returns_immediately(self):
        lagoon = MagicMock()
        lagoon.getEnvironmentDeployments.return_value = [{"status": "complete"}]

        result = {}
        with patch("time.sleep"):
            action().execute({**ARGS, "wait": True}, lagoon, result)

        assert result["deploy_status"] == "complete"

    def test_retries_exhausted_raises(self):
        lagoon = MagicMock()
        lagoon.getEnvironmentDeployments.return_value = [{"status": "running"}]

        with patch("time.sleep"):
            with self.assertRaises(AnsibleError) as caught:
                action().execute({**ARGS, "wait": True, "retries": 2}, lagoon, {})

        assert "Maximium number of retries" in str(caught.exception)


if __name__ == "__main__":
    unittest.main()
