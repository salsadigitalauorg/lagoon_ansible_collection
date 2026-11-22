import unittest
from unittest.mock import MagicMock

from ansible.errors import AnsibleError

from .....plugins.action.project_notification import ActionModule


def action():
    return ActionModule.__new__(ActionModule)


class AddNotificationTester(unittest.TestCase):
    def test_a_duplicate_error_reports_no_change(self):
        lagoon = MagicMock()
        lagoon.errors = ["Duplicate notification name 'chan'"]

        result = {}
        action().execute(
            {
                "project": "p1",
                "notification": "chan",
                "type": "SLACK",
                "state": "present",
            },
            lagoon,
            result,
        )

        assert result["changed"] is False

    def test_any_other_error_raises(self):
        lagoon = MagicMock()
        lagoon.errors = ["Some other failure"]

        with self.assertRaises(AnsibleError):
            action().execute(
                {
                    "project": "p1",
                    "notification": "chan",
                    "type": "SLACK",
                    "state": "present",
                },
                lagoon,
                {},
            )

    def test_success_reports_changed(self):
        lagoon = MagicMock()
        lagoon.errors = []

        result = {}
        action().execute(
            {
                "project": "p1",
                "notification": "chan",
                "type": "SLACK",
                "state": "present",
            },
            lagoon,
            result,
        )

        assert result["changed"] is True


class RemoveNotificationTester(unittest.TestCase):
    def test_absent_on_an_unattached_notification_reports_no_change(self):
        lagoon = MagicMock()
        lagoon.errors = []
        lagoon.removeProjectNotification.return_value = None

        result = {}
        action().execute(
            {
                "project": "p1",
                "notification": "chan",
                "type": "SLACK",
                "state": "absent",
            },
            lagoon,
            result,
        )

        assert result["changed"] is False

    def test_absent_on_an_attached_notification_reports_changed(self):
        lagoon = MagicMock()
        lagoon.errors = []
        lagoon.removeProjectNotification.return_value = {"id": 1}

        result = {}
        action().execute(
            {
                "project": "p1",
                "notification": "chan",
                "type": "SLACK",
                "state": "absent",
            },
            lagoon,
            result,
        )

        assert result["changed"] is True

    def test_an_error_on_remove_raises(self):
        lagoon = MagicMock()
        lagoon.errors = ["Some other failure"]

        with self.assertRaises(AnsibleError):
            action().execute(
                {
                    "project": "p1",
                    "notification": "chan",
                    "type": "SLACK",
                    "state": "absent",
                },
                lagoon,
                {},
            )


if __name__ == "__main__":
    unittest.main()
