import unittest
from unittest.mock import MagicMock

from .....plugins.module_utils.client import LagoonApiError, LagoonClient

ENDPOINT = "https://api.example.com/graphql"


def response(body, status=200):
    res = MagicMock()
    res.status_code = status
    res.json.return_value = body
    return res


def client(responses, **kwargs) -> LagoonClient:
    """A client whose session returns these bodies in order."""
    lagoon = LagoonClient(ENDPOINT, **kwargs)
    lagoon.session = MagicMock()
    lagoon.session.post.side_effect = [
        r if isinstance(r, MagicMock) else response(r) for r in responses
    ]
    return lagoon


class ExecuteTester(unittest.TestCase):
    def test_returns_data(self):
        lagoon = client([{"data": {"me": {"id": 1}}}])
        assert lagoon.execute("query { me { id } }") == {"me": {"id": 1}}
        assert lagoon.errors == []

    def test_partial_data_is_returned_with_errors_collected(self):
        """The inventory depends on this: a failing subresource must not
        discard the projects that did come back."""

        body = {
            "data": {"allProjects": [{"name": "p1"}, None]},
            "errors": [{"message": "Unauthorized for p2"}],
        }
        lagoon = client([body])

        data = lagoon.execute("query { allProjects { name } }")

        assert data == {"allProjects": [{"name": "p1"}, None]}
        assert lagoon.errors == [{"message": "Unauthorized for p2"}]

    def test_raise_on_error_raises_with_the_partial_data_attached(self):
        body = {"data": {"allProjects": [{"name": "p1"}]}, "errors": [{"message": "x"}]}
        lagoon = client([body])

        with self.assertRaises(LagoonApiError) as caught:
            lagoon.execute("query { allProjects { name } }", raise_on_error=True)

        assert caught.exception.errors == [{"message": "x"}]
        assert caught.exception.data == {"allProjects": [{"name": "p1"}]}

    def test_exit_on_error_is_the_default_for_raise_on_error(self):
        body = {"data": None, "errors": [{"message": "x"}]}

        with self.assertRaises(LagoonApiError):
            client([body], exit_on_error=True).execute("query { me }")

        # And the constructor default collects instead of raising.
        lagoon = client([body])
        assert lagoon.execute("query { me }") is None
        assert len(lagoon.errors) == 1

    def test_raise_on_error_false_overrides_exit_on_error(self):
        body = {"data": None, "errors": [{"message": "Duplicate"}]}
        lagoon = client([body], exit_on_error=True)

        assert lagoon.execute("query { me }", raise_on_error=False) is None
        assert lagoon.errors == [{"message": "Duplicate"}]

    def test_not_found_is_not_an_error(self):
        """groupByName errors where projectByName returns null for the same
        condition. Callers get one behaviour."""

        body = {
            "data": {"groupByName": None},
            "errors": [{"message": 'group "nope" not found'}],
        }
        lagoon = client([body], exit_on_error=True)

        assert lagoon.execute("query { groupByName { id } }") == {"groupByName": None}
        assert lagoon.errors == []

    def test_a_mixed_error_list_is_still_an_error(self):
        body = {
            "data": None,
            "errors": [{"message": "not found"}, {"message": "Unauthorized"}],
        }
        lagoon = client([body], exit_on_error=True)

        with self.assertRaises(LagoonApiError):
            lagoon.execute("query { groupByName { id } }")

    def test_a_non_json_response_raises(self):
        res = MagicMock()
        res.status_code = 502
        res.json.side_effect = ValueError("not json")
        lagoon = client([res])

        with self.assertRaises(LagoonApiError) as caught:
            lagoon.execute("query { me }")

        assert "502" in str(caught.exception)

    def test_a_json_body_that_is_not_a_graphql_response_raises(self):
        """A proxy or gateway can return valid JSON that is not a GraphQL
        envelope. That must be an error, not an AttributeError."""

        lagoon = client([["unexpected", "list"]])

        with self.assertRaises(LagoonApiError):
            lagoon.execute("query { me }")

    def test_variables_are_sent_as_json(self):
        lagoon = client([{"data": {"projectByName": {"id": 1}}}])
        lagoon.query("projectByName", {"name": "p1"}, ["id"])

        payload = lagoon.session.post.call_args.kwargs["json"]
        assert payload["variables"] == {"name": "p1"}
        assert "p1" not in payload["query"]

    def test_booleans_and_enums_survive_as_json(self):
        """No literal serialisation step, so no coercion to fix.

        The previous client rendered values into the document as GraphQL
        literals, which turned True into 1 and quoted enum values.
        """

        lagoon = client([{"data": {"updateProject": {"id": 1}}}])
        patch = {
            "sharedBaasBucket": True,
            "availability": "STANDARD",
            "branches": "123",
        }
        lagoon.mutate("updateProject", {"input": {"id": 1, "patch": patch}})

        sent = lagoon.session.post.call_args.kwargs["json"]["variables"]
        assert sent["input"]["patch"]["sharedBaasBucket"] is True
        assert sent["input"]["patch"]["availability"] == "STANDARD"
        assert sent["input"]["patch"]["branches"] == "123"


class CheckModeTester(unittest.TestCase):
    def test_a_mutation_is_not_sent(self):
        lagoon = client([], check_mode=True)

        result = lagoon.mutate("addEnvVariable", {"input": {"name": "X"}})

        assert lagoon.session.post.call_count == 0
        assert result["id"] < 0

    def test_a_delete_mutation_reports_success(self):
        lagoon = client([], check_mode=True)

        assert lagoon.mutate("deleteProject", {"input": {"project": "p"}}) == "success"
        assert lagoon.session.post.call_count == 0

    def test_queries_always_execute(self):
        lagoon = client([{"data": {"projectByName": {"id": 1}}}], check_mode=True)

        assert lagoon.query("projectByName", {"name": "p"}, ["id"]) == {"id": 1}
        assert lagoon.session.post.call_count == 1


class TokenRetryTester(unittest.TestCase):
    def test_a_rejected_token_is_refetched_once(self):
        credentials = MagicMock()
        credentials.token.side_effect = ["stale-token", "fresh-token"]

        lagoon = LagoonClient(ENDPOINT, credentials)
        lagoon.session = MagicMock()
        lagoon.session.post.side_effect = [
            response({"errors": [{"message": "Unauthorized"}]}, status=401),
            response({"data": {"me": {"id": 1}}}),
        ]

        assert lagoon.execute("query { me { id } }") == {"me": {"id": 1}}

        credentials.invalidate.assert_called_once()
        assert lagoon.session.post.call_count == 2
        headers = [c.kwargs["headers"] for c in lagoon.session.post.call_args_list]
        assert headers[0]["Authorization"] == "Bearer stale-token"
        assert headers[1]["Authorization"] == "Bearer fresh-token"

    def test_the_retry_happens_only_once(self):
        credentials = MagicMock()
        credentials.token.return_value = "t"

        lagoon = LagoonClient(ENDPOINT, credentials)
        lagoon.session = MagicMock()
        lagoon.session.post.side_effect = [
            response({"errors": [{"message": "Unauthorized"}]}, status=401),
            response({"errors": [{"message": "Unauthorized"}]}, status=401),
        ]

        lagoon.execute("query { me }")

        assert lagoon.session.post.call_count == 2

    def test_a_persistent_401_with_no_graphql_envelope_is_not_silent(self):
        """A gateway or WAF fronting Lagoon can reject the retried request in
        its own shape rather than Lagoon's GraphQL {errors, data} envelope.

        Without a response.status_code check, that body has no "errors" to
        collect and no "data" key to be null, so it would look exactly like a
        query that legitimately returned nothing - defeating exit_on_error.
        """

        credentials = MagicMock()
        credentials.token.return_value = "t"

        lagoon = LagoonClient(ENDPOINT, credentials, exit_on_error=True)
        lagoon.session = MagicMock()
        lagoon.session.post.side_effect = [
            response({"errors": [{"message": "Unauthorized"}]}, status=401),
            response({"message": "Unauthorized"}, status=401),
        ]

        with self.assertRaises(LagoonApiError) as caught:
            lagoon.execute("query { me }")

        assert "401" in str(caught.exception)

    def test_a_persistent_error_status_is_collected_without_raising(self):
        credentials = MagicMock()
        credentials.token.return_value = "t"

        lagoon = LagoonClient(ENDPOINT, credentials)
        lagoon.session = MagicMock()
        lagoon.session.post.side_effect = [
            response({"errors": [{"message": "Unauthorized"}]}, status=401),
            response({"message": "Unauthorized"}, status=401),
        ]

        assert lagoon.execute("query { me }") is None
        assert lagoon.errors == [{"message": "HTTP 401 from the Lagoon API"}]

    def test_an_error_status_with_a_graphql_envelope_is_not_duplicated(self):
        """A response that does carry errors/data must not also get the
        synthetic HTTP-status error appended on top."""

        lagoon = client([response({"data": None, "errors": [{"message": "x"}]}, 400)])

        lagoon.execute("query { me }")

        assert lagoon.errors == [{"message": "x"}]

    def test_an_error_status_with_null_data_is_not_treated_as_envelope_less(self):
        """ "data": null still counts as a GraphQL-shaped response, even with
        no "errors" key - a query resolving to nothing is not a transport
        failure."""

        lagoon = client([response({"data": None}, 404)])

        assert lagoon.execute("query { me }") is None
        assert lagoon.errors == []

    def test_no_credentials_means_no_authorization_header(self):
        lagoon = client([{"data": {"me": None}}])
        lagoon.execute("query { me }")

        assert "Authorization" not in lagoon.session.post.call_args.kwargs["headers"]

    def test_a_bare_token_string_is_accepted(self):
        lagoon = LagoonClient(ENDPOINT, "supplied-token")
        lagoon.session = MagicMock()
        lagoon.session.post.side_effect = [response({"data": {"me": None}})]

        lagoon.execute("query { me }")

        headers = lagoon.session.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer supplied-token"


class ConstructorTester(unittest.TestCase):
    def test_no_io_on_construction(self):
        """Credentials are resolved lazily, so building a client is free."""
        credentials = MagicMock()
        LagoonClient(ENDPOINT, credentials)
        credentials.token.assert_not_called()

    def test_headers_must_be_a_mapping(self):
        with self.assertRaises(ValueError):
            LagoonClient(ENDPOINT, None, "not-a-dict")

    def test_content_type_is_set_and_callers_can_add_headers(self):
        lagoon = LagoonClient(ENDPOINT, None, {"X-Trace": "abc"})
        assert lagoon.headers["Content-Type"] == "application/json"
        assert lagoon.headers["X-Trace"] == "abc"
