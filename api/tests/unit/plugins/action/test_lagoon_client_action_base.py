import unittest
from unittest.mock import MagicMock, patch

from ansible.errors import AnsibleActionFail, AnsibleError
from ansible.plugins.action import ActionBase

from .....plugins.action import LagoonClientActionBase
from .....plugins.module_utils import display as display_module
from .....plugins.module_utils.args import lagoon_argument_spec
from .....plugins.module_utils.auth import LagoonCredentials
from .....plugins.module_utils.client import LagoonClient

ARG_SPEC = lagoon_argument_spec(
    foo=dict(type="list", elements="str"),
    secret=dict(type="str", no_log=True),
)

SENTINEL = "sup3r-s3cret-sentinel"


class StubActionModule(LagoonClientActionBase):
    argSpec = ARG_SPEC

    def execute(self, args, lagoon, result):
        self.seenArgs = args
        self.seenClient = lagoon
        result["ran"] = True


def make_module(task_args, check_mode=False):
    module = StubActionModule.__new__(StubActionModule)
    module._task = MagicMock()
    module._task.args = dict(task_args)
    module._task.check_mode = check_mode
    module._load_name = "stub"
    module._display = MagicMock()
    module._templar = MagicMock()
    module._templar.template.side_effect = lambda v: v
    return module


def run(module, task_vars):
    with patch.object(ActionBase, "run", return_value={}):
        return module.run(task_vars=task_vars)


class ValidationTester(unittest.TestCase):
    def test_a_bad_task_arg_is_rejected_before_any_request(self):
        module = make_module({"foo": {"not": "a list"}, "api_endpoint": "https://e"})

        with self.assertRaises(AnsibleActionFail):
            run(module, {})

    def test_a_missing_endpoint_raises(self):
        module = make_module({})

        with self.assertRaises(AnsibleError):
            run(module, {})

    def test_valid_args_reach_execute(self):
        module = make_module({"foo": "bar", "api_endpoint": "https://e"})

        run(module, {})

        assert module.seenArgs["foo"] == ["bar"]


class CredentialsTester(unittest.TestCase):
    def test_no_api_token_is_not_an_error_and_builds_from_ssh_task_vars(self):
        module = make_module({"api_endpoint": "https://e"})

        run(
            module,
            {
                "lagoon_ssh_private_key": "key-content",
                "lagoon_ssh_host": "ssh.example.com",
                "lagoon_ssh_port": "2222",
            },
        )

        credentials = module.seenClient.credentials
        assert isinstance(credentials, LagoonCredentials)
        assert credentials.explicit_token is None
        assert credentials.ssh_private_key == "key-content"
        assert credentials.ssh_host == "ssh.example.com"
        assert credentials.ssh_port == "2222"

    def test_an_explicit_token_performs_no_ssh_call(self):
        module = make_module({"api_endpoint": "https://e", "api_token": "a-token"})

        with patch.object(LagoonCredentials, "mint") as mint:
            run(module, {})
            assert module.seenClient.credentials.token() == "a-token"
            mint.assert_not_called()

    def test_endpoint_falls_back_to_task_vars(self):
        module = make_module({})

        run(module, {"lagoon_api_endpoint": "https://task-var-endpoint"})

        assert module.seenClient.endpoint == "https://task-var-endpoint"


class CheckModeTester(unittest.TestCase):
    def test_check_mode_reaches_the_client(self):
        module = make_module({"api_endpoint": "https://e"}, check_mode=True)

        run(module, {})

        assert isinstance(module.seenClient, LagoonClient)
        assert module.seenClient.check_mode is True


class RedactionTester(unittest.TestCase):
    def test_a_no_log_argument_does_not_appear_in_verbose_output(self):
        module = make_module(
            {"api_endpoint": "https://e", "secret": SENTINEL, "foo": ["visible"]}
        )

        sink = MagicMock()
        sink.verbosity = 3
        with (
            patch.object(display_module, "OrigDisplay", return_value=sink, create=True),
            patch.object(display_module, "HAS_DISPLAY", True),
        ):
            run(module, {})

        output = "\n".join(str(c) for c in sink.mock_calls)
        assert SENTINEL not in output
        assert "visible" in output


if __name__ == "__main__":
    unittest.main()
