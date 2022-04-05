from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.errors import AnsibleError
from gql.transport.requests import RequestsHTTPTransport
from gql import Client
from gql.dsl import DSLField, DSLSchema, DSLQuery, dsl_gql

from typing import Any, Dict

class GqlClient:
    """ This client aims to facilitate the usage of the gql package, based on
    the docs at https://gql.readthedocs.io/en/latest/advanced/dsl_module.html.
    The goal is to allow developers to run queries and mutations using the awesome
    package while reducing boilerplate code. """

    def __init__(self, endpoint: str, token: str, headers: dict={}) -> None:
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

    def execute_query(self, field_query: DSLField) -> Dict[str, Any]:
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
        return self.client.session.execute(full_query)
