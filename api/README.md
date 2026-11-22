# Ansible Collection - lagoon.api

An Ansible collection for interaction with the Lagoon GraphQL API.

## Requirements

* [gql[requests]](https://github.com/graphql-python/gql) - The GraphQL client used to make requests. Install by running:

  ```sh
  pip3 install gql[requests]
  ```

## Usage

The following variables are required in the playbook:

* lagoon_api_endpoint
* lagoon_api_token

`lagoon_api_token` is optional for the inventory plugin: when omitted, a token is
minted over SSH on first use from `ssh_private_key`, `ssh_private_key_file`, or
the machine's own SSH configuration and agent.

## Breaking change: SSH host key verification

Up to and including 2.3.3, fetching an API token over SSH always passed
`-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no`. That disabled host
key verification on the one call that hands over a bearer token, so any
machine-in-the-middle could present its own host key and capture the token.

Those options are **no longer passed by default**. The machine's own
`~/.ssh/config`, identities and `known_hosts` now apply, and host key
verification is yours to configure.

If token fetching starts failing with `Host key verification failed`, add the
Lagoon SSH host to `known_hosts`:

```sh
ssh-keyscan -p 32222 ssh.lagoon.amazeeio.cloud >> ~/.ssh/known_hosts
```

To restore the old behaviour instead, request it explicitly per Lagoon in your
inventory:

```yaml
lagoons:
  - api_endpoint: 'https://api.lagoon.amazeeio.cloud/graphql'
    ssh_options:
      - -o
      - UserKnownHostsFile=/dev/null
      - -o
      - StrictHostKeyChecking=no
```

Agent, port and X11 forwarding and terminal allocation are always disabled on
this call and cannot be re-enabled through `ssh_options`; `grant` is a single
non-interactive command that needs none of them.

`lagoon_ssh_options` is the single place to set ssh options for token
fetching - the `roles/token` role and the `fetch_token` action both read it,
alongside the inventory and every other plugin that mints a token. An
explicit `ssh_options` task arg still overrides it. Prefer the list form over
a string: a string is split on whitespace, so `-o "Foo=bar"` keeps its
literal quotes in argv.

## Testing

Updating the schema:
```sh
lagoon config list
lagoon login -l amazeeio
LAGOON_TOKEN=$(lagoon -l amazeeio get token)
gql-cli https://api.lagoon.amazeeio.cloud/graphql --print-schema \
  --header Authorization:"Bearer $LAGOON_TOKEN" > api/tests/common/schema.graphql
```
