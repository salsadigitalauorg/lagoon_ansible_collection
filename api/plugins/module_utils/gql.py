from ansible.errors import AnsibleError
from ansible.utils.display import Display
from gql.transport.requests import RequestsHTTPTransport
from gql import Client, gql
from gql.dsl import DSLField, DSLQuery, DSLSchema, DSLType, dsl_gql
from graphql import print_ast
from typing import Any, Dict, List, Optional

class GqlClient:
    """ This client aims to facilitate the usage of the gql package, based on
    the docs at https://gql.readthedocs.io/en/latest/advanced/dsl_module.html.
    The goal is to allow developers to run queries and mutations using the awesome
    package while reducing boilerplate code. """

    def __init__(self, endpoint: str, token: str, headers: dict = {}, display: Display = None) -> None:
        if not isinstance(headers, dict):
            raise AnsibleError("Expecting client headers to be dictionary.")

        headers['Content-Type'] = 'application/json'
        headers['Authorization'] = f"Bearer {token}"

        # There's not much reason to do async requests in the Ansible context,
        # so we're defaulting to RequestsHTTPTransport.
        # See https://gql.readthedocs.io/en/latest/transports/index.html.
        transport = RequestsHTTPTransport(
            url=endpoint,
            headers=headers,
            verify=True,
            retries=3,
        )

        # gql has the ability to fetch the schema directly from the GraphQL
        # server API, so we set the relevant argument.
        self.client = Client(
            transport=transport,
            fetch_schema_from_transport=True
        )

        self.display = display

    def __enter__(self):
        """This method and the next (__exit__) allow the use of the `with`
        statement with the class.
        See https://web.archive.org/web/20100702092526/http://effbot.org/zone/python-with-statement.htm
        for an explanation.
        In this case, we are simply calling the client's corresponding method, but
        also augmenting it with the schema preloaded."""

        self.client.__enter__()
        assert self.client.schema is not None
        self.ds = DSLSchema(self.client.schema)
        return self.client.session, self.ds

    def __exit__(self, *args):
        self.client.__exit__(args)

    def execute_query(self, query: str, variables: Optional[Dict[str, Any]]={}) -> Dict[str, Any]:
        """Executes a query using the graphql string provided.
        """
        query_ast = gql(query)
        self.display.vvvv(f"GraphQL built query: \n{print_ast(query_ast)}")
        res = self.client.execute(query_ast, variable_values=variables)
        self.display.vvvv(f"GraphQL query result: {res}")
        return res

    def build_dynamic_query(self, query: str, mainType: str, args: Optional[Dict[str, Any]] = {}, fields: List[str] = [], subFieldsMap: Optional[Dict[str, List[str]]] = {}) -> DSLField:
        """
        Dynamically build a query against the Lagoon API.

        The query is built from the query name (e.g, projectByName), a list of
        top-level fields (e.g, id, name, branches, ...) and a map of sub-fields
        (e.g, kubernetes { id name } ).

        Taking the following graphql query as an example:
        {
            projectByName(name: "test-project") {
                id
                name
                kubernetes {
                    id
                    name
                }
            }
        }
        query = "projectByName"
        args = {"name": "test-project"}
        mainType = "Project" (since projectByName returns Project)
        fields = ["id", "name"]
        subFieldsMap = {
            "kubernetes": {
                "type": "Kubernetes",
                "fields": ["id", "name"],
            },
        }
        """

        # Build the main query with top-level fields if any.
        queryObj: DSLField = getattr(self.ds.Query, query)
        if len(args):
            queryObj.args(**args)

        mainTypeObj: DSLType = getattr(self.ds, mainType)

        # Top-level fields.
        if len(fields):
            for f in fields:
                queryObj.select(getattr(mainTypeObj, f))

        if not len(subFieldsMap):
            return queryObj

        # Nested fields (one level only).
        for field, subFieldsNType in subFieldsMap.items():
            subFieldSelector: DSLField = getattr(mainTypeObj, field)
            subFieldTypeObj: DSLType = getattr(self.ds, subFieldsNType['type'])
            for f in subFieldsNType['fields']:
                subFieldSelector.select(getattr(subFieldTypeObj, f))
            queryObj.select(subFieldSelector)

        return queryObj


    def execute_query_dynamic(self, field_query: DSLField) -> Dict[str, Any]:
        """Executes a dynamic query with the open session.

        See https://gql.readthedocs.io/en/latest/advanced/dsl_module.html for
        more information on how to execute one and what's available.

        Parameters
        ----------
        field_query : DSLField, required
            A field query on the schema as defined in the docs above.
        """

        # Generate the full query.
        full_query = dsl_gql(DSLQuery(field_query))
        self.display.vvvv(f"GraphQL built query: \n{print_ast(full_query)}")
        res = self.client.session.execute(full_query)
        self.display.vvvv(f"GraphQL query result: {res}")
        return res
