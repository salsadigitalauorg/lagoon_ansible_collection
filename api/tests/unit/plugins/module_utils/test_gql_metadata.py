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

    def test_get_string(self):
        """
        Older versions of the Lagoon API returned metadata as a string.
        """
        client = get_mock_gql_client(query_return_value={
            "allProjects": [
                {
                    "id": 999,
                    "name": "test",
                    "metadata": "{\"type\":\"saas\",\"version\":\"9\"}"
                }
            ]
        })
        lagoonMetadata = Metadata(client)
        res = lagoonMetadata.get()

        assert isinstance(res, dict), f"expected dict, got {type(res)}"
        assert res == {'test': {'type': 'saas', 'version': '9'}}, f"got {res}"

    def test_get_object(self):
        """
        Newer versions of the Lagoon API return metadata as an object.
        """
        client = get_mock_gql_client(query_return_value={
            "allProjects": [
                {
                    "id": 999,
                    "name": "test",
                    "metadata": { "type": "saas", "version": "9" }
                }
            ]
        })
        lagoonMetadata = Metadata(client)
        res = lagoonMetadata.get()

        assert isinstance(res, dict), f"expected dict, got {type(res)}"
        assert res == {'test': {'type': 'saas', 'version': '9'}}, f"got {res}"

    def test_update_string(self):
        """
        Older versions of the Lagoon API returned metadata as a string.
        """
        client = get_mock_gql_client(query_return_value={
            "updateProjectMetadata": {
                "metadata": "{\"type\": \"paas\",\"version\": \"9\"}"
            }
        })
        lagoonMetadata = Metadata(client)
        res = lagoonMetadata.update(111, "type", "paas")

        assert isinstance(res, str), f"expected str, got {type(res)}"
        assert res == "type:paas", f"got {res}"

    def test_update_object(self):
        """
        Newer versions of the Lagoon API return metadata as an object.
        """
        client = get_mock_gql_client(query_return_value={
            "updateProjectMetadata": {
                "metadata": { "type": "paas", "version": "9" }
            }
        })
        lagoonMetadata = Metadata(client)
        res = lagoonMetadata.update(111, "type", "paas")

        assert isinstance(res, str), f"expected str, got {type(res)}"
        assert res == "type:paas", f"got {res}"
