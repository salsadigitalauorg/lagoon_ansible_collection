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

## Testing

Updating the schema:
```sh
lagoon config list
lagoon login -l amazeeio
LAGOON_TOKEN=$(lagoon -l amazeeio get token)
gql-cli https://api.lagoon.amazeeio.cloud/graphql --print-schema \
  --header Authorization:"Bearer $LAGOON_TOKEN" > api/tests/common/schema.graphql
```
