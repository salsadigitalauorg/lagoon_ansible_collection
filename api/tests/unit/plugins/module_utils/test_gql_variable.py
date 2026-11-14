import unittest

from ....common import load_schema
from .....plugins.module_utils.gql import GqlClient
from .....plugins.module_utils.gqlVariable import Variable
from gql.dsl import DSLQuery, DSLSchema
from unittest.mock import MagicMock, patch

SENTINEL = "sup3r-s3cret-sentinel"


def verbose_client():
    """A client at -vvv with its underlying display captured."""
    client = GqlClient("foo", "bar")
    client.display = MagicMock()
    client.display.verbosity = 3
    return client


def emitted(client):
    return "\n".join(
        str(c)
        for c in client.display.verbose.call_args_list
        + client.display.display.call_args_list
    )


import sys

sys.modules["ansible.utils.display"] = unittest.mock.Mock()


class GqlVariableTester(unittest.TestCase):
    def test_variable_addOrUpdateByName(self):
        client = GqlClient("foo", "bar")
        client.execute_query = MagicMock()

        lagoonVariable = Variable(client)
        lagoonVariable.addOrUpdateByName(
            "projectname", "environmentname", "SOME_VAR", "foo", "RUNTIME"
        )
        _, query_args = client.execute_query.call_args.args

        assert isinstance(query_args["project"], str)
        assert query_args["project"] == "projectname"
        assert isinstance(query_args["environment"], str)
        assert query_args["environment"] == "environmentname"
        assert isinstance(query_args["scope"], str)
        assert query_args["scope"] == "RUNTIME"
        assert isinstance(query_args["name"], str)
        assert query_args["name"] == "SOME_VAR"
        assert isinstance(query_args["value"], str)
        assert query_args["value"] == "foo"

    def test_add_value_cast_to_string(self):
        client = GqlClient("foo", "bar")
        client.execute_query = MagicMock()

        lagoonVariable = Variable(client)

        lagoonVariable.addOrUpdateByName(
            "projectname", "environmentname", "SOME_VAR", True, "RUNTIME"
        )
        _, query_args = client.execute_query.call_args.args
        assert isinstance(query_args["value"], str)
        assert query_args["value"] == "True"

        lagoonVariable.addOrUpdateByName(
            "projectname", "environmentname", "SOME_VAR2", 50, "RUNTIME"
        )
        _, query_args = client.execute_query.call_args.args
        assert isinstance(query_args["value"], str)
        assert query_args["value"] == "50"

    def test_getForProjects_does_not_emit_values(self):
        # The result holds every variable for the project, so an unmuted
        # query log leaks all of them, not just the one being managed.
        client = verbose_client()
        ds = DSLSchema(load_schema())
        client.client = MagicMock()
        client.client.session.execute.return_value = {
            "projectname": {
                "envVariables": [{"id": 1, "name": "SOME_VAR", "value": SENTINEL}]
            }
        }

        with (
            patch.object(GqlClient, "__enter__", return_value=(MagicMock(), ds)),
            patch.object(GqlClient, "__exit__", return_value=False),
        ):
            res = Variable(client).getForProjects(["projectname"])

        assert SENTINEL not in emitted(client)
        # The caller still receives the real values.
        assert res["projectname"][0]["value"] == SENTINEL

        # Guard against a vacuous pass: the same call unmuted does emit, so
        # the display mock and verbosity above are genuinely live.
        query = ds.Query.projectByName.args(name="projectname").select(
            ds.Project.envVariables.select(ds.EnvKeyValue.value)
        )
        client.execute_query_dynamic(DSLQuery(query))
        assert SENTINEL in emitted(client)

    def test_addOrUpdateByName_does_not_emit_value(self):
        client = verbose_client()
        client.client = MagicMock()
        client.client.execute.return_value = {"addOrUpdateEnvVariableByName": {"id": 1}}

        Variable(client).addOrUpdateByName(
            "projectname", "environmentname", "SOME_VAR", SENTINEL, "RUNTIME"
        )

        assert SENTINEL not in emitted(client)
        # The real value still reached the API.
        sent = client.client.execute.call_args.kwargs["variable_values"]
        assert sent["value"] == SENTINEL
