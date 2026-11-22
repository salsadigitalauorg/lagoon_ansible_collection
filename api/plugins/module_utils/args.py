"""The shared argspec fragment for LagoonClientActionBase consumers.

Free of any gql import, unlike argspec.py, which pulls in gql.dsl and
graphql and is scheduled for deletion. Argument names and aliases match
argspec.auth_argument_spec() so both bases accept identical task arguments
while both exist.
"""

AUTH_ARGS = dict(
    api_endpoint=dict(type="str", aliases=["lagoon_api_endpoint", "lagoon_endpoint"]),
    api_token=dict(
        type="str", no_log=True, aliases=["lagoon_api_token", "lagoon_token"]
    ),
    headers=dict(type="dict", default={}),
)


def lagoon_argument_spec(**extra) -> dict:
    """AUTH_ARGS merged with a plugin's own arguments."""
    spec = dict(AUTH_ARGS)
    spec.update(extra)
    return spec
