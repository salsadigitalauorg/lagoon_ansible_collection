import unittest

from .....plugins.action.project_update import ActionModule
from .....plugins.module_utils.client import LagoonClient

ENDPOINT = "https://api.example.com/graphql"


def action():
    return ActionModule.__new__(ActionModule)


def client_capturing_variables(project):
    lagoon = LagoonClient(ENDPOINT)
    captured = {}

    def execute(document, variables=None, raise_on_error=None):
        captured["variables"] = variables
        if "updateProject" in document:
            return {"updateProject": {"id": project["id"]}}
        return {"projectByName": project}

    lagoon.execute = execute
    return lagoon, captured


class CoercionTester(unittest.TestCase):
    """The patch travels as a declared variable, so it serialises as plain
    JSON rather than through a hand-rolled literal renderer - no more
    bool-to-int or string-to-int coercion."""

    def test_a_bool_reaches_the_transport_as_json_true_not_1(self):
        lagoon, captured = client_capturing_variables(
            {"id": 1, "sharedBaasBucket": False}
        )

        action().execute(
            {"project": "p1", "values": {"sharedBaasBucket": True}}, lagoon, {}
        )

        patch = captured["variables"]["input"]["patch"]
        assert patch["sharedBaasBucket"] is True

    def test_an_enum_is_a_bare_json_string(self):
        lagoon, captured = client_capturing_variables(
            {"id": 1, "availability": "STANDARD"}
        )

        action().execute(
            {"project": "p1", "values": {"availability": "HIGH"}}, lagoon, {}
        )

        patch = captured["variables"]["input"]["patch"]
        assert patch["availability"] == "HIGH"

    def test_a_numeric_looking_string_stays_a_string(self):
        lagoon, captured = client_capturing_variables(
            {"id": 1, "developmentEnvironmentsLimit": 5}
        )

        action().execute(
            {
                "project": "p1",
                "values": {"developmentEnvironmentsLimit": "123"},
            },
            lagoon,
            {},
        )

        patch = captured["variables"]["input"]["patch"]
        assert patch["developmentEnvironmentsLimit"] == "123"
        assert isinstance(patch["developmentEnvironmentsLimit"], str)


if __name__ == "__main__":
    unittest.main()
