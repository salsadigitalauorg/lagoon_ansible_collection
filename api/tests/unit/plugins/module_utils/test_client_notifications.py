import unittest
from unittest.mock import MagicMock

from .....plugins.module_utils.client import LagoonClient

ENDPOINT = "https://api.example.com/graphql"


def client(data=None) -> LagoonClient:
    lagoon = LagoonClient(ENDPOINT)
    lagoon.execute = MagicMock(return_value=data)
    return lagoon


def document(lagoon) -> str:
    return lagoon.execute.call_args.args[0]


def variables(lagoon) -> dict:
    return lagoon.execute.call_args.args[1]


class UpdateProjectTester(unittest.TestCase):
    def test_document_and_variables(self):
        lagoon = client({"updateProject": {"id": 1}})

        lagoon.updateProject(1, {"autoIdle": 0})

        assert document(lagoon) == (
            "mutation updateProject($input: UpdateProjectInput!) "
            "{ updateProject(input: $input) { id name autoIdle branches gitUrl "
            "metadata openshift { id name } kubernetes { id name } "
            "environments { name } } }"
        )
        assert variables(lagoon) == {"input": {"id": 1, "patch": {"autoIdle": 0}}}


class AddProjectNotificationTester(unittest.TestCase):
    def test_document_and_variables(self):
        lagoon = client({"addNotificationToProject": {"id": 1, "name": "chan"}})

        lagoon.addProjectNotification("p1", "chan")

        assert document(lagoon) == (
            "mutation addNotificationToProject"
            "($input: AddNotificationToProjectInput!) "
            "{ addNotificationToProject(input: $input) { id name } }"
        )
        assert variables(lagoon) == {
            "input": {
                "project": "p1",
                "notificationType": "SLACK",
                "notificationName": "chan",
            }
        }

    def test_a_duplicate_error_lands_on_errors_rather_than_raising(self):
        lagoon = LagoonClient(ENDPOINT)
        lagoon.post = MagicMock()
        lagoon.post.return_value.json.return_value = {
            "errors": [{"message": "Duplicate notification"}],
            "data": {"addNotificationToProject": None},
        }
        lagoon.post.return_value.status_code = 200

        result = lagoon.addProjectNotification("p1", "chan", raise_on_error=False)

        assert result is None
        assert any("Duplicate" in str(e) for e in lagoon.errors)


class RemoveProjectNotificationTester(unittest.TestCase):
    def test_document_and_variables(self):
        lagoon = client({"removeNotificationFromProject": {"id": 1}})

        lagoon.removeProjectNotification("p1", "chan", "EMAIL")

        assert document(lagoon) == (
            "mutation removeNotificationFromProject"
            "($input: RemoveNotificationFromProjectInput!) "
            "{ removeNotificationFromProject(input: $input) { id } }"
        )
        assert variables(lagoon) == {
            "input": {
                "project": "p1",
                "notificationType": "EMAIL",
                "notificationName": "chan",
            }
        }

    def test_removing_an_unattached_notification_returns_none_not_found(self):
        """execute() collapses an all-"not found" error list to null data,
        so detaching a notification that is not attached returns None rather
        than raising."""

        lagoon = LagoonClient(ENDPOINT)
        lagoon.post = MagicMock()
        lagoon.post.return_value.json.return_value = {
            "errors": [{"message": "Notification not found"}],
        }
        lagoon.post.return_value.status_code = 200

        result = lagoon.removeProjectNotification("p1", "chan", raise_on_error=False)

        assert result is None
        assert lagoon.errors == []


if __name__ == "__main__":
    unittest.main()
