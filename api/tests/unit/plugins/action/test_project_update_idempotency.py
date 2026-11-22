import unittest
from unittest.mock import MagicMock

from ansible.errors import AnsibleError

from .....plugins.action.project_update import ActionModule, comparison_fields


def module():
    return ActionModule.__new__(ActionModule)


class ComparisonFieldsTester(unittest.TestCase):
    def test_selects_exactly_the_patched_keys(self):
        fields = comparison_fields({"productionEnvironment": "main", "autoIdle": 1})
        assert fields == ["productionEnvironment", "autoIdle"]

    def test_openshift_and_kubernetes_are_selected_as_id(self):
        fields = comparison_fields({"openshift": 2, "kubernetes": 3})
        assert fields == [{"openshift": ["id"]}, {"kubernetes": ["id"]}]

    def test_privatekey_is_never_selected(self):
        fields = comparison_fields({"privateKey": "x", "autoIdle": 1})
        assert fields == ["autoIdle"]


class IdempotencyTester(unittest.TestCase):
    def test_a_26_field_key_matching_the_current_value_reports_no_change(self):
        """The bug in the previous client compared against a fixed 7-field
        selection, so a patch of any other key always reported changed."""

        lagoon = MagicMock()
        lagoon.getProject.return_value = {"id": 1, "productionEnvironment": "main"}

        action = module()
        result = {}
        action.execute(
            {"project": "p1", "values": {"productionEnvironment": "main"}},
            lagoon,
            result,
        )

        assert result["changed"] is False
        lagoon.updateProject.assert_not_called()
        lagoon.getProject.assert_called_once_with(
            "p1", fields=["id", "productionEnvironment"]
        )

    def test_a_differing_value_updates(self):
        lagoon = MagicMock()
        lagoon.getProject.return_value = {"id": 1, "productionEnvironment": "main"}
        lagoon.updateProject.return_value = {"id": 1}

        action = module()
        result = {}
        action.execute(
            {"project": "p1", "values": {"productionEnvironment": "dev"}},
            lagoon,
            result,
        )

        assert result["changed"] is True
        lagoon.updateProject.assert_called_once_with(
            1, {"productionEnvironment": "dev"}
        )

    def test_openshift_and_kubernetes_are_compared_against_the_id(self):
        lagoon = MagicMock()
        lagoon.getProject.return_value = {
            "id": 1,
            "kubernetes": {"id": 5, "name": "cluster"},
        }

        action = module()
        result = {}
        action.execute({"project": "p1", "values": {"kubernetes": 5}}, lagoon, result)

        assert result["changed"] is False
        lagoon.updateProject.assert_not_called()

    def test_a_patch_containing_privatekey_neither_selects_nor_returns_it(self):
        lagoon = MagicMock()
        lagoon.getProject.return_value = {"id": 1}
        lagoon.updateProject.return_value = {"id": 1}

        action = module()
        result = {}
        action.execute(
            {"project": "p1", "values": {"privateKey": "secret-material"}},
            lagoon,
            result,
        )

        assert result["changed"] is True
        fields = lagoon.getProject.call_args.kwargs["fields"]
        assert "privateKey" not in fields
        assert "secret-material" not in str(result)

    def test_a_missing_project_raises(self):
        lagoon = MagicMock()
        lagoon.getProject.return_value = None

        action = module()
        with self.assertRaises(AnsibleError):
            action.execute({"project": "nope", "values": {"autoIdle": 1}}, lagoon, {})


if __name__ == "__main__":
    unittest.main()
