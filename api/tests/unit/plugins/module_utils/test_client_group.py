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


class GetGroupTester(unittest.TestCase):
    def test_default_selection_needs_no_inline_fragments(self):
        lagoon = client({"groupByName": {"id": "1", "name": "g", "type": "group"}})

        lagoon.getGroup("g")

        assert document(lagoon) == (
            "query groupByName($name: String!) "
            "{ groupByName(name: $name) { id name type } }"
        )

    def test_a_missing_group_returns_none_with_no_errors(self):
        """groupByName errors rather than returning null for a missing
        group; execute() collapses an all-"not found" error list to null
        data, so this still returns None with nothing on client.errors."""

        lagoon = LagoonClient(ENDPOINT)
        lagoon.post = MagicMock()
        lagoon.post.return_value.json.return_value = {
            "errors": [{"message": "Group not found"}],
        }
        lagoon.post.return_value.status_code = 200

        assert lagoon.getGroup("nope") is None
        assert lagoon.errors == []


if __name__ == "__main__":
    unittest.main()
