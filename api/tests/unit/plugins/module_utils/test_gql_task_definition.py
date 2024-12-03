import unittest

from ....common import dsl_exes_to_str, get_mock_gql_client
from .....plugins.module_utils.gqlTaskDefinition import TaskDefinition
from gql.dsl import DSLFragment, DSLQuery

import sys
sys.modules['ansible.utils.display'] = unittest.mock.Mock()
sys.modules['gql.client.Client'] = unittest.mock.Mock()


class GqlTaskDefinitionTester(unittest.TestCase):

    def test_get(self):
        client = get_mock_gql_client()
        lagoonTaskDefinition = TaskDefinition(client)
        lagoonTaskDefinition.get_definitions()
        query_args = client.execute_query_dynamic.call_args.args

        assert len(query_args) == 3
        assert isinstance(query_args[0], DSLFragment)
        assert isinstance(query_args[1], DSLFragment)
        assert isinstance(query_args[2], DSLQuery)

        assert "\n" + dsl_exes_to_str(*query_args) == """
fragment Image on AdvancedTaskDefinitionImage {
  id
  type
  permission
  project
  environment
  name
  description
  service
  confirmationText
  groupName
  advancedTaskDefinitionArguments {
    id
    name
    displayName
    type
    range
  }
  deployTokenInjection
  projectKeyInjection
  systemWide
  image
}

fragment Command on AdvancedTaskDefinitionCommand {
  id
  type
  permission
  project
  environment
  name
  description
  service
  confirmationText
  groupName
  advancedTaskDefinitionArguments {
    id
    name
    displayName
    type
    range
  }
  deployTokenInjection
  projectKeyInjection
  systemWide
  command
}

{
  allAdvancedTaskDefinitions {
    ...Image
    ...Command
  }
}"""

    def test_get_with_fields(self):
        client = get_mock_gql_client()
        lagoonTaskDefinition = TaskDefinition(client)
        lagoonTaskDefinition.get_definitions(fields=["id"])
        query_args = client.execute_query_dynamic.call_args.args
        assert "\n" + dsl_exes_to_str(*query_args) == """
fragment Image on AdvancedTaskDefinitionImage {
  id
  image
}

fragment Command on AdvancedTaskDefinitionCommand {
  id
  command
}

{
  allAdvancedTaskDefinitions {
    ...Image
    ...Command
  }
}"""

        lagoonTaskDefinition.get_definitions(
            fields=["id", "advancedTaskDefinitionArguments"])
        query_args = client.execute_query_dynamic.call_args.args
        assert "\n" + dsl_exes_to_str(*query_args) == """
fragment Image on AdvancedTaskDefinitionImage {
  id
  advancedTaskDefinitionArguments {
    id
    name
    displayName
    type
    range
  }
  image
}

fragment Command on AdvancedTaskDefinitionCommand {
  id
  advancedTaskDefinitionArguments {
    id
    name
    displayName
    type
    range
  }
  command
}

{
  allAdvancedTaskDefinitions {
    ...Image
    ...Command
  }
}"""
