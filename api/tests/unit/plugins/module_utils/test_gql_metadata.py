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

    def test_update_value(self):
        client = get_mock_gql_client(query_return_value={
            "updateProjectMetadata": {
                "metadata": {"type": "paas", "version": "9"}
            }
        })
        lagoonMetadata = Metadata(client)

        # Scalar.
        lagoonMetadata.update(111, "groups", "foogroup")
        query_args = client.execute_query.call_args.args
        assert len(query_args) == 2, f"expected 2, got {len(query_args)}"
        assert isinstance(
            query_args[0], str), f"expected str, got {type(query_args[0])}"
        assert isinstance(
            query_args[1], dict), f"expected dict, got {type(query_args[1])}"

        assert query_args[1] == {
            "id": 111,
            "key": "groups",
            "value": "foogroup"
        }, f"got {query_args[1]}"

        # List.
        lagoonMetadata.update(111, "groups", ["foogroup1", "foogroup2"])
        query_args = client.execute_query.call_args.args
        assert len(query_args) == 2, f"expected 2, got {len(query_args)}"
        assert isinstance(
            query_args[0], str), f"expected str, got {type(query_args[0])}"
        assert isinstance(
            query_args[1], dict), f"expected dict, got {type(query_args[1])}"

        assert query_args[1] == {
            "id": 111,
            "key": "groups",
            "value": '["foogroup1", "foogroup2"]'
        }, f"got {query_args[1]}"

        # Dict.
        lagoonMetadata.update(111, "groups", {"group1": "foo", "group2": "bar"})
        query_args = client.execute_query.call_args.args
        assert len(query_args) == 2, f"expected 2, got {len(query_args)}"
        assert isinstance(
            query_args[0], str), f"expected str, got {type(query_args[0])}"
        assert isinstance(
            query_args[1], dict), f"expected dict, got {type(query_args[1])}"

        assert query_args[1] == {
            "id": 111,
            "key": "groups",
            "value": '{"group1": "foo", "group2": "bar"}'
        }, f"got {query_args[1]}"

    def test_update_result_string(self):
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

    def test_update_result_object(self):
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

    def test_unpack(self):
        lagoonMetadata = Metadata(None)

        data_scalar = {"key1": "item1", "key2": "item2"}
        lagoonMetadata.unpack(data_scalar)
        assert data_scalar == {"key1": "item1", "key2": "item2"}

        data_list = {
            "key1": "item1",
            "list1": '["list1-item1", "list1-item2"]',
            "list2": ["list2-item1", "list2-item2"],
        }
        lagoonMetadata.unpack(data_list)
        assert data_list == {
            "key1": "item1",
            "list1": ["list1-item1", "list1-item2"],
            "list2": ["list2-item1", "list2-item2"],
        }

        data_dict = {
            "key1": "item1",
            "dict1": '{"dict1-key1":"dict1-item1", "dict1-key2":"dict1-item2"}',
            "dict2": {"dict2-key1": "dict2-item1", "dict2-key2": "dict2-item2"},
        }
        lagoonMetadata.unpack(data_dict)
        assert data_dict == {
            "key1": "item1",
            "dict1": {"dict1-key1":"dict1-item1", "dict1-key2":"dict1-item2"},
            "dict2": {"dict2-key1": "dict2-item1", "dict2-key2": "dict2-item2"},
        }

