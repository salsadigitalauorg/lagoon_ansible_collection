import unittest


from ....common import dsl_exes_to_str, get_mock_gql_client
from .....plugins.module_utils.gqlMetadata import Metadata
from gql.dsl import DSLQuery

import sys
sys.modules['ansible.utils.display'] = unittest.mock.Mock()
sys.modules['gql.client.Client'] = unittest.mock.Mock()


class GqlMetadataTester(unittest.TestCase):

    def test_get(self):
        client = get_mock_gql_client()
        lagoonMetadata = Metadata(client)
        lagoonMetadata.get()
        query_args = client.execute_query.call_args.args

        assert len(query_args) == 1, f"expected 1, got {len(query_args)}"
        assert isinstance(
            query_args[0], str), f"expected str, got {type(query_args[0])}"

        assert query_args[0] == """
                query {
                    allProjects {
                        id
                        name
                        metadata
                    }
                }""", f"got {query_args[0]}"

    def test_get_with_fields(self):
        client = get_mock_gql_client()
        lagoonMetadata = Metadata(client)
        lagoonMetadata.get(project_names=["project-test-1", "project2"])
        query_args = client.execute_query_dynamic.call_args.args

        assert len(query_args) == 1, f"expected 1, got {len(query_args)}"
        assert isinstance(
            query_args[0], DSLQuery), f"expected DSLQuery, got {type(query_args[0])}"

        resulting_query = "\n" + dsl_exes_to_str(*query_args)
        assert resulting_query == """
{
  project_test_1: projectByName(name: "project-test-1") {
    metadata
  }
  project2: projectByName(name: "project2") {
    metadata
  }
}""", f"got {resulting_query}"

