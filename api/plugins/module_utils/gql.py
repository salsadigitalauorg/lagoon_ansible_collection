from .display import Display
from ansible.module_utils.errors import AnsibleValidationError
from gql import Client, gql
from gql.dsl import (
  DSLExecutable,
  DSLField,
  DSLInlineFragment,
  DSLMutation, DSLQuery,
  DSLSchema, DSLType,
  dsl_gql
)
from gql.transport.exceptions import TransportQueryError
from gql.transport.requests import RequestsHTTPTransport
from graphql import print_ast, GraphQLList, GraphQLOutputType, GraphQLUnionType
from graphql.type.definition import (
    is_list_type,
    is_object_type,
    is_scalar_type,
    is_union_type,
)
from random import randint
from typing import Any, Dict, List, Optional, Union, cast

class GqlClient(Display):
    """ This client aims to facilitate the usage of the gql package, based on
    the docs at https://gql.readthedocs.io/en/latest/advanced/dsl_module.html.
    The goal is to allow developers to run queries and mutations using the awesome
    package while reducing boilerplate code. """

    checkMode: bool = False

    def __init__(self, endpoint: str, token: str, headers: dict = {},
                 display: Display = None, checkMode: bool = False) -> None:
        super().__init__()

        if not isinstance(headers, dict):
            raise AnsibleValidationError("Expecting client headers to be dictionary.")

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

        self.checkMode = checkMode

        # This value of display if deprecated - use the Display class instead.
        del display

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
        self.vvvv(f"GraphQL built query: \n{print_ast(query_ast)}")
        self.vvvv(f"GraphQL query variables: \n{variables}")

        if self.checkMode:
            return {'checkMode': True}

        try:
            res = self.client.execute(query_ast, variable_values=variables)
            self.vvvv(f"GraphQL query result: {res}")
            return res
        except TransportQueryError as e:
            self.vvvv(f"GraphQL TransportQueryError: {e}")
            return {'error': e}

    def execute_query_dynamic(self, *operations: DSLExecutable) -> Dict[str, Any]:
        """Executes a dynamic query with the open session.

        See https://gql.readthedocs.io/en/latest/advanced/dsl_module.html for
        more information on how to execute one and what's available.

        Parameters
        ----------
        operations : DSLExecutable, required
            A tuple of DSLQuery and/or DSLFragment.
        """

        # Generate the full query.
        full_query = dsl_gql(*operations)
        self.vvv(f"GraphQL built query: \n{print_ast(full_query)}")

        if self.checkMode and isinstance(operations[0], DSLMutation):
            self.info(f"Check mode enabled, skipping query execution. Query to execute: \n{print_ast(full_query)}")
            opName = operations[0].selection_set.selections[0].name.value
            if opName.startswith('delete'):
                res = {opName: 'success'}
            else:
                res = {opName: {'id': -1 * randint(1, 1000)}}
        else:
            res = self.client.session.execute(full_query)

        self.vvv(f"GraphQL query result: {res}")
        return res

    def build_dynamic_query(self,
                            query: str,
                            mainType: str,
                            args: Optional[Dict[str, Any]] = {},
                            fields: List[str] = [],
                            subFieldsMap: Optional[Dict[str, List[str]]] = {},
                            ) -> DSLField:
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

        if not len(fields) and not len(subFieldsMap):
            raise AnsibleValidationError("One of fields or subFieldsMap is required.")

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

    def build_dynamic_mutation(self,
                               mutation: str,
                               inputArgs: Optional[Dict[str, Any]] = {},
                               returnFields: List[str] = ['id'],
                               ) -> DSLField:
        """
        Dynamically build a mutation against the Lagoon API.

        The mutation is built from the mutation name
        (e.g, deployEnvironmentBranch) and a dict of input arguments
        (e.g, {project: {name: "test"}, branchName: "master"} ).

        Taking the following graphql mutation as an example:
        {
            addFact(
                input: {
                    environment: 243307,
                    name: "test_module",
                    value: "2.0.0",
                    source: "ansible_playbook:test-mutation",
                    description: "The test_module module version",
                    category: "Drupal Module Version"
                }
            ) { id }
        }
        mutation = "addFact"
        inputArgs = {
            environment: 243307,
            name: "test_module",
            value: "2.0.0",
            source: "ansible_playbook:test-mutation",
            description: "The test_module module version",
            category: "Drupal Module Version"
        }
        returnFields = ["id"]
        """

        if not len(inputArgs):
            raise AnsibleValidationError("Input arguments are required for mutations.")

        # Build the main query with top-level fields if any.
        mutationField: DSLField = getattr(self.ds.Mutation, mutation)
        self.augment_mutation_field(
            mutationField,
            mutationField.field.type,
            inputArgs,
            returnFields)

        return mutationField

    def augment_mutation_field(self,
                               mutationField: DSLField,
                               outputType: GraphQLOutputType,
                               inputArgs: Optional[Dict[str, Any]] = {},
                               returnFields: List[str] = ['id']):

        if is_scalar_type(outputType):
            argsIntersect = list(
                set(mutationField.field.args.keys()) &
                set(inputArgs.keys()))
            mutationField.args(**{argsIntersect[0]: inputArgs[argsIntersect[0]]})
        elif is_union_type(outputType):
            mutationField.args(**inputArgs)
            unionType = cast(GraphQLUnionType, outputType)
            for t in unionType.types:
                inlineFragment = DSLInlineFragment()
                inlineFragmentType: DSLType = getattr(self.ds, t.name)
                inlineFragment.on(inlineFragmentType)
                for f in returnFields:
                    if not hasattr(inlineFragmentType, f):
                        continue
                    inlineFragment.select(getattr(inlineFragmentType, f))

                mutationField.select(inlineFragment)
        elif is_list_type(outputType):
            listObj = cast(GraphQLList, outputType)
            self.augment_mutation_field(
                mutationField,
                listObj.of_type,
                inputArgs,
                returnFields)
        elif is_object_type(outputType):
            mutationField.args(**inputArgs)
            selectType: DSLType = getattr(self.ds, outputType.name)
            for f in returnFields:
                if not hasattr(selectType, f):
                    continue
                mutationField.select(getattr(selectType, f))
        else:
            self.vvv('to_kwargs', mutationField.field.to_kwargs())
            self.vvv('type', outputType)
            self.vvv('fieldType', outputType.to_kwargs(), "\n")
            raise Exception("Unsupported field type found when generating mutation field")

globalClient: GqlClient = None
def GetClientInstance(endpoint: str, token: str, headers: dict = {},
                      checkMode: bool = False) -> GqlClient:

    global globalClient
    if not globalClient:
        globalClient = GqlClient(endpoint, token, headers, checkMode=checkMode)
    return globalClient

class ProxyLookup(Display):

    query: str = None

    # Use these fields from the input task args
    # to send as args to the lookup query.
    inputArgFields: Dict[str, str] = {}

    # Use these fields in the order provided
    # to select the fields in the query.
    selectFields: List[str] = None

    qryField: DSLField

    def __init__(self, query: str, inputArgFields: Dict[str, str] = {},
                 selectFields: List[str] = None):

        super().__init__()
        self.query = query
        self.inputArgFields = inputArgFields
        self.selectFields = selectFields

    def client(self) -> GqlClient:
        global globalClient
        return globalClient

    def hasInputArgs(self, inputArgs: dict) -> bool:
        self.qryField = getattr(self.client().ds.Query, self.query)
        queryArgKeys = list(self.qryField.field.args.keys())
        if len(self.inputArgFields):
            queryArgKeys = self.inputArgFields.keys()

        intersectedArgs = {k: v for k, v in inputArgs.items() if k in queryArgKeys}

        if len(intersectedArgs) != len(queryArgKeys):
            return False

        for arg in intersectedArgs:
            if len(self.inputArgFields):
                self.qryField.args(**{self.inputArgFields[arg]: inputArgs[arg]})
                continue
            self.qryField.args(**{arg: inputArgs[arg]})

        return True

    def execute(self, inputArgs: dict,
                compareFields: List[str]) -> Dict[str, Any]|None:
        typeObj: DSLType = getattr(self.client().ds, self.qryField.field.type.name)

        leafQueryFields = list(inputArgs.keys())
        if 'id' not in leafQueryFields:
            leafQueryFields.append('id')

        if len(self.selectFields):
            self.qryField.select(
                nested_field_selector(
                    self.client().ds, typeObj, self.selectFields, leafQueryFields))

        results = self.client().execute_query_dynamic(DSLQuery(self.qryField))
        results = results[self.query]
        if not len(self.selectFields):
            return results

        for f in self.selectFields:
            if not isinstance(results, list):
                results = results[f]
                continue

            newRes = []
            for r in results:
                if not isinstance(r[f], list):
                    newRes.append(r[f])
                    continue

                for i in r[f]:
                    newRes.append(i)
            results = newRes

        matchedRecord = None
        for r in results:
            for cf in compareFields:
                if cf not in r:
                    continue
                if r[cf] == inputArgs[cf]:
                    matchedRecord = r
                    break

        return matchedRecord

def field_selector(ds: DSLSchema,
                   selector: DSLField,
                   selectorType: GraphQLOutputType,
                   selectFields: List[str]) -> DSLField:

    if is_list_type(selectorType):
        return field_selector(ds, selector, selectorType.of_type, selectFields)
    elif is_union_type(selectorType):
        unionType = cast(GraphQLUnionType, selectorType)
        for t in unionType.types:
            inlineFragment = DSLInlineFragment()
            inlineFragmentType: DSLType = getattr(ds, t.name)
            inlineFragment.on(inlineFragmentType)
            for f in selectFields:
                if not hasattr(inlineFragmentType, f):
                    continue
                inlineFragment.select(getattr(inlineFragmentType, f))
            selector.select(inlineFragment)
    else:
        print('selector', selector)
        print('selectorType', selectorType, selectorType.to_kwargs())
        print('selectFields', selectFields)
        raise Exception("Unsupported field type found when generating field selector")

    return selector

def nested_field_selector(
        ds: DSLSchema,
        parentType: DSLType,
        selectFields: List[str],
        leafFields: List[str]) -> Union[DSLType, DSLField]:

    if len(selectFields) == 1:
        leafSelector: DSLField = getattr(parentType, selectFields[0])
        return field_selector(ds, leafSelector, leafSelector.field.type, leafFields)

    selector: DSLField = getattr(parentType, selectFields[0])
    if is_list_type(selector.field.type):
        selectorType: DSLType = getattr(ds, selector.field.type.of_type.name)
    else:
        selectorType: DSLType = getattr(ds, selector.field.type.name)

    selector.select(
        nested_field_selector(
            ds, selectorType, selectFields[1:], leafFields))

    return selector
