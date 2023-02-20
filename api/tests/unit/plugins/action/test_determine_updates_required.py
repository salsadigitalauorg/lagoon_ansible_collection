import unittest
import sys

sys.modules['ansible.utils.display'] = unittest.mock.Mock()
sys.modules['typing_extensions'] = unittest.mock.Mock()

from .....plugins.action.deploy_target_config import determine_required_updates

class DetermineUpdatesTester(unittest.TestCase):

    def test_update_required(self):
        existing_configs = []
        desired_configs = [
            {
                'branches': '^(main)$',
                'deployTarget': 1,
                'pullrequests': 'false',
            }
        ]
        
        updates_required = determine_required_updates(existing_configs, desired_configs)
        
        assert len(updates_required) == 1
        assert updates_required[0]['branches'] == '^(main)$'
        assert updates_required[0]['deployTarget'] == 1

    def test_update_not_required(self):
        existing_configs = [
            {
                'branches': '^(main)$',
                'deployTarget': {'id': 1, 'name': 'cluster.io'},
                'id': 1,
                'pullrequests': 'false',
                'weight': 1
            }
        ]
        desired_configs = [
            {
                'branches': '^(main)$',
                'deployTarget': 1,
                'pullrequests': 'false',
                'weight': 1
            }
        ]

        updates_required = determine_required_updates(existing_configs, desired_configs)

        assert len(updates_required) == 0

    def test_update_required_weight(self):
        existing_configs = [
            {
                'branches': '^(main)$',
                'deployTarget': {'id': 1, 'name': 'cluster.io'},
                'id': 1,
                'pullrequests': 'false',
                'weight': 1
            }
        ]
        desired_configs = [
            {
                'branches': '^(main)$',
                'deployTarget': 1,
                'pullrequests': 'false',
                'weight': 2
            }
        ]

        updates_required = determine_required_updates(existing_configs, desired_configs)

        assert len(updates_required) == 1
        assert updates_required[0]['weight'] == 2

    def test_update_required_cluster(self):
        existing_configs = [
            {
                'branches': '^(main)$',
                'deployTarget': {'id': 1, 'name': 'cluster.io'},
                'id': 1,
                'pullrequests': 'false',
                'weight': 1
            }
        ]
        desired_configs = [
            {
                'branches': '^(main)$',
                'deployTarget': 2,
                'pullrequests': 'false',
                'weight': 1
            }
        ]

        updates_required = determine_required_updates(existing_configs, desired_configs)

        assert len(updates_required) == 1
        assert updates_required[0]['deployTarget'] == 2

    def test_orphan_existing(self):
        existing_configs = [
            {
                'branches': '^(main)$',
                'deployTarget': {'id': 1, 'name': 'cluster.io'},
                'id': 1,
                'pullrequests': 'false',
                'weight': 1
            },
            {
                'branches': '^(develop)$',
                'deployTarget': {'id': 2, 'name': 'cluster.io'},
                'id': 2,
                'pullrequests': 'true',
                'weight': 1
            }
        ]
        desired_configs = [
            {
                'branches': '^(main)$',
                'deployTarget': 2,
                'pullrequests': 'true',
                'weight': 1
            }
        ] 

        updates_required = determine_required_updates(existing_configs, desired_configs)

        assert len(updates_required) == 1
        assert updates_required[0]['deployTarget'] == 2