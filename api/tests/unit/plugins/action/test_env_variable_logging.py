import unittest

from ....common import load_schema
from ansible.plugins.action import ActionBase
from gql.dsl import DSLSchema
from unittest.mock import MagicMock, patch

import sys

sys.modules["ansible.utils.display"] = unittest.mock.Mock()
from .....plugins.action.env_variable import ActionModule
from .....plugins.module_utils.gql import GqlClient
from .....plugins.module_utils.gqlEnvironment import Environment

SENTINEL = "sup3r-s3cret-sentinel"
NEW_SENTINEL = "rep1acement-s3cret"

TASK_ARGS = {
    "name": "SOME_VAR",
    "type": "PROJECT",
    "type_name": "test-project",
    "state": "present",
    "scope": "RUNTIME",
}


def make_module(args, existing_value=SENTINEL):
    """An ActionModule wired to mocks, with display output captured."""

    module = ActionModule.__new__(ActionModule)
    module._task = MagicMock()
    module._task.args = args
    module._task.check_mode = False
    module._display = MagicMock()
    module.createClient = MagicMock()
    module.client = MagicMock()

    project = MagicMock()
    project.projects = [
        {
            "id": 1,
            "name": "test-project",
            "envVariables": [
                {
                    "id": 9,
                    "name": "SOME_VAR",
                    "value": existing_value,
                    "scope": "RUNTIME",
                },
                {
                    "id": 10,
                    "name": "OTHER_VAR",
                    "value": "other-" + SENTINEL,
                    "scope": "BUILD",
                },
            ],
        }
    ]

    variable = MagicMock()
    variable.addOrUpdateByName.return_value = {"id": 9}

    return module, project, variable


def emitted(module):
    return "\n".join(str(c) for c in module._display.v.call_args_list)


def make_environment_module(args, existing_value=SENTINEL):
    """As make_module, but for the ENVIRONMENT branch."""

    module, project, variable = make_module(args)

    environment = MagicMock()
    environment.environments = [
        {
            "id": 7,
            "name": "master",
            "kubernetesNamespaceName": "test-project-master",
            "project": {"id": 1, "name": "test-project"},
            "envVariables": [
                {
                    "id": 9,
                    "name": "SOME_VAR",
                    "value": existing_value,
                    "scope": "RUNTIME",
                },
                {
                    "id": 10,
                    "name": "OTHER_VAR",
                    "value": "other-" + SENTINEL,
                    "scope": "BUILD",
                },
            ],
        }
    ]

    return module, environment, variable


def run_module(module, project, variable, task_vars=None, environment=None):
    with (
        patch.object(ActionBase, "run", return_value={}),
        patch(
            "ansible_collections.lagoon.api.plugins.action.env_variable.Project",
            return_value=project,
        ),
        patch(
            "ansible_collections.lagoon.api.plugins.action.env_variable.Environment",
            return_value=environment or MagicMock(),
        ),
        patch(
            "ansible_collections.lagoon.api.plugins.action.env_variable.Variable",
            return_value=variable,
        ),
    ):
        return module.run(task_vars=task_vars or {})


class EnvVariableLoggingTester(unittest.TestCase):
    """Variable values must never reach verbose output."""

    def test_no_change_path_does_not_emit_values(self):
        args = dict(TASK_ARGS, value=SENTINEL)
        module, project, variable = make_module(args)

        result = run_module(module, project, variable)

        output = emitted(module)
        # The submitted value, the stored value, and every other variable's
        # value must all stay out of the output.
        assert SENTINEL not in output
        assert "other-" + SENTINEL not in output
        # Names and scopes are not secret and remain useful for debugging.
        assert "SOME_VAR" in output
        assert "OTHER_VAR" in output
        assert "test-project" in output
        # The real values were still compared, so this is a no-op.
        assert result["id"] == 9
        assert not result.get("changed")

    def test_replace_existing_path_does_not_emit_values(self):
        args = dict(TASK_ARGS, value=NEW_SENTINEL, replace_existing=True)
        module, project, variable = make_module(args)

        result = run_module(module, project, variable)

        output = emitted(module)
        assert NEW_SENTINEL not in output
        assert SENTINEL not in output
        # The real value still reached the API call.
        variable.addOrUpdateByName.assert_called_once_with(
            "test-project", None, "SOME_VAR", NEW_SENTINEL, "RUNTIME"
        )
        assert result["changed"] is True

    def test_task_args_masked_once_by_base_class(self):
        # LagoonActionBase.run logs task args for every action plugin, so the
        # subclass must declare the value argument sensitive. The plugin no
        # longer logs them a second time itself.
        assert ActionModule._sensitive_task_args == ["value"]

        args = dict(TASK_ARGS, value=SENTINEL)
        module, project, variable = make_module(args)

        run_module(module, project, variable)

        task_arg_lines = [
            str(c) for c in module._display.v.call_args_list if "Task args" in str(c)
        ]
        assert len(task_arg_lines) == 1
        assert SENTINEL not in task_arg_lines[0]
        assert "VALUE_REDACTED" in task_arg_lines[0]
        # Non-sensitive args stay visible.
        assert "SOME_VAR" in task_arg_lines[0]

    def test_input_structures_not_mutated_by_logging(self):
        # The no-change check and the verify_value loop both re-read the real
        # values after logging, so logging must not write back into them.
        args = dict(TASK_ARGS, value=SENTINEL)
        module, project, variable = make_module(args)

        run_module(module, project, variable)

        assert args["value"] == SENTINEL
        assert project.projects[0]["envVariables"][0]["value"] == SENTINEL

    def test_environment_branch_does_not_emit_values(self):
        # The ENVIRONMENT branch has its own identity and variables messages.
        args = dict(
            TASK_ARGS,
            type="ENVIRONMENT",
            type_name="test-project-master",
            value=SENTINEL,
        )
        module, environment, variable = make_environment_module(args)

        result = run_module(module, None, variable, environment=environment)

        output = emitted(module)
        assert SENTINEL not in output
        assert "other-" + SENTINEL not in output
        # Identifying detail stays visible.
        assert "SOME_VAR" in output
        assert "test-project-master" in output
        assert result["id"] == 9

    def test_handles_project_with_no_variables(self):
        # envVariables can come back None; the logging helper must not raise
        # before the existing type check reports the real problem.
        args = dict(TASK_ARGS, value=SENTINEL)
        module, project, variable = make_module(args)
        project.projects[0]["envVariables"] = None

        with self.assertRaises(Exception) as e:
            run_module(module, project, variable)

        assert "Incorrect variable type" in str(e.exception)


class GqlEnvironmentLoggingTester(unittest.TestCase):
    """The environment variable read path must not emit values either.

    This lives in the controller test group rather than alongside the Variable
    tests in tests/unit/plugins/module_utils/, because gqlEnvironment imports
    ansible.errors, which ansible-test does not make importable in the
    target-side module_utils group.
    """

    def test_getVariables_does_not_emit_values(self):
        # Same leak class as Variable.getForProject: one result holds every
        # variable for the environment named.
        client = GqlClient("foo", "bar")
        client.display = MagicMock()
        client.display.verbosity = 3
        ds = DSLSchema(load_schema())
        client.client = MagicMock()
        # Keyed by the query name, not an alias: one root field per request.
        client.client.session.execute.return_value = {
            "environmentByKubernetesNamespaceName": {
                "envVariables": [{"id": 1, "name": "SOME_VAR", "value": SENTINEL}]
            }
        }

        with (
            patch.object(GqlClient, "__enter__", return_value=(MagicMock(), ds)),
            patch.object(GqlClient, "__exit__", return_value=False),
        ):
            res = Environment(client).getVariables("test-project-master")

        output = "\n".join(
            str(c)
            for c in client.display.verbose.call_args_list
            + client.display.display.call_args_list
        )

        assert SENTINEL not in output
        # The caller still receives the real value.
        assert res[0]["value"] == SENTINEL
