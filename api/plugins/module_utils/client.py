"""A thin, string-based client for the Lagoon GraphQL API.

Documents are plain GraphQL text built from a caller-supplied field spec, and
every caller-supplied *value* travels as a declared GraphQL variable. No value
is ever formatted into the document, so there is no injection path and enums,
booleans, ints, lists and nested input objects all serialise as plain JSON with
no literal-rendering step.

The only schema knowledge needed is each root field's argument type names, for
the variable declarations, and those come from the committed schema_args map -
so there is no introspection round trip before the first useful request.
"""

import re
from collections.abc import Mapping, Sequence
from random import randint
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter

from .auth import LagoonCredentials
from .clientEnvironment import EnvironmentMethods
from .clientGroup import GroupMethods
from .clientProject import ProjectMethods
from .display import Display, redact_keys
from .fields import FIELD_NAME, check_name, render_fields
from .schema_args import MUTATION_ARG_TYPES, QUERY_ARG_TYPES

# Characters a GraphQL type reference can be built from: a name, list brackets
# and non-null markers. Type strings reach the document text, so they are
# checked rather than trusted, whether they came from the generated map or from
# a caller's arg_types override.
TYPE_CHARS = re.compile(r"^[\[\]!A-Za-z0-9_]+$")


class LagoonApiError(Exception):
    """Raised when the API returns errors and the caller asked to stop.

    Attributes:
        errors -- the GraphQL errors list
        data   -- any partial data returned alongside them
    """

    def __init__(self, errors: list, data: Any = None, message: str = ""):
        self.errors = errors
        self.data = data
        super().__init__(message or f"Lagoon API returned errors: {errors}")


def is_type_reference(value) -> bool:
    """Whether this is a plain GraphQL type reference, e.g. "[EnvType]!"."""
    if not isinstance(value, str) or not TYPE_CHARS.match(value):
        return False
    return bool(FIELD_NAME.match(value.strip("[]!")))


class LagoonClient(ProjectMethods, EnvironmentMethods, GroupMethods, Display):
    def __init__(
        self,
        endpoint: str,
        credentials: Optional[Any] = None,
        headers: Optional[Mapping[str, str]] = None,
        check_mode: bool = False,
        timeout: int = 30,
        retries: int = 3,
        exit_on_error: bool = False,
    ) -> None:
        super().__init__()

        if headers is not None and not isinstance(headers, Mapping):
            raise ValueError("Expecting client headers to be a dictionary.")

        self.endpoint = endpoint
        self.check_mode = check_mode
        self.timeout = timeout
        self.exit_on_error = exit_on_error
        self.errors = []

        # A bare token string is accepted so that a caller holding one does not
        # have to reach for the credentials class, but it is wrapped rather
        # than used directly so there is a single token code path.
        if isinstance(credentials, str):
            credentials = LagoonCredentials(token=credentials)
        self.credentials = credentials
        if credentials is not None:
            credentials.bind_endpoint(endpoint)

        self.headers = {"Content-Type": "application/json"}
        self.headers.update(headers or {})

        # One session for the client's life, so keep-alive and connection
        # pooling hold across the thousands of requests an inventory refresh
        # issues. There is no connect/close lifecycle to manage.
        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def request_headers(self) -> dict[str, str]:
        """Request headers, with a bearer token resolved on demand.

        Resolved per request rather than stored on the session, so constructing
        a client performs no I/O and an invalidated token is picked up on the
        next call. The token must never be logged, here or in a traceback.
        """

        headers = dict(self.headers)
        if self.credentials is not None:
            headers["Authorization"] = f"Bearer {self.credentials.token()}"
        return headers

    def post(self, payload: dict) -> requests.Response:
        """POST the payload, retrying once if the token is rejected.

        verify is left at its default of True and is not configurable: every
        request carries a Lagoon bearer token, so an unverified connection
        hands that token to anything able to intercept the path.
        """

        response = self.session.post(
            self.endpoint,
            json=payload,
            headers=self.request_headers(),
            timeout=self.timeout,
        )

        # A token can be inside its stated lifetime and still be rejected,
        # through clock skew or server-side revocation. One retry with a fresh
        # token covers that without making every call verify validity first.
        if response.status_code == 401 and self.credentials is not None:
            self.vv("Lagoon API rejected the token; refetching and retrying once.")
            self.credentials.invalidate()
            response = self.session.post(
                self.endpoint,
                json=payload,
                headers=self.request_headers(),
                timeout=self.timeout,
            )

        return response

    def execute(
        self,
        document: str,
        variables: Optional[dict] = None,
        raise_on_error: Optional[bool] = None,
    ) -> Optional[dict]:
        """Run a document and return its data.

        GraphQL can return data and errors together, and callers such as the
        inventory depend on the partial data, so errors are collected onto
        self.errors and the data returned. With raise_on_error - defaulting to
        the constructor's exit_on_error - a LagoonApiError is raised instead.
        """

        if raise_on_error is None:
            raise_on_error = self.exit_on_error

        self.vvv(f"GraphQL document: \n{document}")
        # Values travel as variables rather than inlined in the document, so
        # redacting by key is enough to keep a secret being written out of the
        # log while leaving the rest of the request visible.
        self.vvv(f"GraphQL variables: \n{redact_keys(variables or {})}")

        payload = {"query": document}
        if variables:
            payload["variables"] = variables

        response = self.post(payload)

        try:
            result = response.json()
        except ValueError as e:
            # Deliberately excludes the body: an error page is not a GraphQL
            # response and may carry anything.
            raise LagoonApiError(
                [{"message": f"HTTP {response.status_code} from the Lagoon API"}],
                None,
                f"Lagoon API returned a non-JSON response (HTTP {response.status_code}).",
            ) from e

        if not isinstance(result, dict):
            raise LagoonApiError(
                [{"message": f"HTTP {response.status_code} from the Lagoon API"}],
                None,
                "Lagoon API returned JSON that is not a GraphQL response "
                f"(HTTP {response.status_code}).",
            )

        errors = result.get("errors") or []
        if not isinstance(errors, list):
            errors = [errors]
        self.vvv(f"GraphQL result: {result}\n\n")

        # An HTTP failure status with neither key is not a GraphQL response at
        # all - a gateway, WAF or proxy in front of Lagoon rejecting the
        # request in its own shape, after the one token retry in post() has
        # already been exhausted. Without this, such a response has no
        # "errors" to collect and no "data" to be null, so it would otherwise
        # look exactly like a query that legitimately returned nothing.
        if (
            response.status_code >= 400
            and "errors" not in result
            and "data" not in result
        ):
            errors = [{"message": f"HTTP {response.status_code} from the Lagoon API"}]

        data = result.get("data")

        # groupByName errors where projectByName returns null for the same
        # condition. Treat a wholly "not found" error list as the absence it
        # describes, so callers get one behaviour.
        if errors and all("not found" in str(e) for e in errors):
            return data

        if errors:
            self.errors.extend(errors)
            if raise_on_error:
                raise LagoonApiError(errors, data)

        return data

    def arg_types_for(self, operation: str, field: str) -> dict[str, str]:
        mapping = QUERY_ARG_TYPES if operation == "query" else MUTATION_ARG_TYPES
        try:
            return mapping[field]
        except KeyError:
            raise ValueError(
                f"No argument types known for {operation} field '{field}'. Pass "
                "arg_types={'argName': 'GraphQLType!'} explicitly, or regenerate "
                "schema_args.py if the schema has gained the field."
            ) from None

    def build_document(
        self,
        operation: str,
        field: str,
        args: Optional[Mapping[str, Any]] = None,
        fields: Optional[Sequence[Any]] = None,
        arg_types: Optional[Mapping[str, str]] = None,
    ) -> str:
        """Render a single-root-field operation, arguments declared as variables."""

        check_name(field)
        args = args or {}

        if args:
            types = (
                dict(arg_types)
                if arg_types is not None
                else self.arg_types_for(operation, field)
            )

            unknown = [name for name in args if name not in types]
            if unknown:
                raise ValueError(
                    f"No argument type known for {', '.join(sorted(unknown))} on "
                    f"{operation} field '{field}'. Known arguments: "
                    f"{', '.join(sorted(types)) or 'none'}."
                )

            for name in args:
                check_name(name)
                if not is_type_reference(types[name]):
                    raise ValueError(
                        f"Not a valid GraphQL type for argument '{name}': {types[name]!r}"
                    )

            declarations = ", ".join(f"${name}: {types[name]}" for name in args)
            arguments = ", ".join(f"{name}: ${name}" for name in args)
            header = f"{operation} {field}({declarations})"
            invocation = f"{field}({arguments})"
        else:
            header = f"{operation} {field}"
            invocation = field

        selection = f" {{ {render_fields(fields)} }}" if fields else ""
        return f"{header} {{ {invocation}{selection} }}"

    def query(
        self,
        field: str,
        args: Optional[Mapping[str, Any]] = None,
        fields: Optional[Sequence[Any]] = None,
        arg_types: Optional[Mapping[str, str]] = None,
        raise_on_error: Optional[bool] = None,
    ) -> Any:
        """Run a single-field query and return that field's value."""

        document = self.build_document("query", field, args, fields, arg_types)
        data = self.execute(document, dict(args) if args else None, raise_on_error)
        return (data or {}).get(field)

    def mutate(
        self,
        field: str,
        args: Optional[Mapping[str, Any]] = None,
        fields: Optional[Sequence[Any]] = ("id",),
        arg_types: Optional[Mapping[str, str]] = None,
        raise_on_error: Optional[bool] = None,
    ) -> Any:
        """Run a single-field mutation and return that field's value.

        In check mode the mutation is logged rather than sent, and a stand-in
        result returned: a negative id, or "success" for a delete.
        """

        document = self.build_document("mutation", field, args, fields, arg_types)

        if self.check_mode:
            self.info(
                f"Check mode enabled, skipping mutation execution. "
                f"Mutation to execute: \n{document}"
            )
            if field.startswith("delete"):
                return "success"
            return {"id": -1 * randint(1, 1000)}

        data = self.execute(document, dict(args) if args else None, raise_on_error)
        return (data or {}).get(field)
