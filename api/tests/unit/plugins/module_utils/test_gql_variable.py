import unittest

from .....plugins.module_utils.gql import GqlClient
from .....plugins.module_utils.gqlVariable import Variable
from unittest.mock import MagicMock

import sys
sys.modules['ansible.utils.display'] = unittest.mock.Mock()


class GqlVariableTester(unittest.TestCase):

    def test_add(self):
        client = GqlClient('foo', 'bar')
        client.execute_query = MagicMock()

        lagoonVariable = Variable(client)
        lagoonVariable.add('PROJECT', 1, 'SOME_VAR', 'foo', 'RUNTIME')
        _, query_args = client.execute_query.call_args.args

        assert isinstance(query_args['type'], str)
        assert query_args['type'] == 'PROJECT'
        assert isinstance(query_args['type_id'], int)
        assert query_args['type_id'] == 1
        assert isinstance(query_args['scope'], str)
        assert query_args['scope'] == 'RUNTIME'
        assert isinstance(query_args['name'], str)
        assert query_args['name'] == 'SOME_VAR'
        assert isinstance(query_args['value'], str)
        assert query_args['value'] == 'foo'

    def test_add_value_cast_to_string(self):
        client = GqlClient('foo', 'bar')
        client.execute_query = MagicMock()

        lagoonVariable = Variable(client)

        lagoonVariable.add('PROJECT', 1, 'SOME_VAR', True, 'RUNTIME')
        _, query_args = client.execute_query.call_args.args
        assert isinstance(query_args['value'], str)
        assert query_args['value'] == 'True'

        lagoonVariable.add('PROJECT', 1, 'SOME_VAR2', 50, 'RUNTIME')
        _, query_args = client.execute_query.call_args.args
        assert isinstance(query_args['value'], str)
        assert query_args['value'] == '50'

