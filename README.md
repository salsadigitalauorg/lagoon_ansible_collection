# Ansible Collection - lagoon
[![tests](https://github.com/salsadigitalauorg/lagoon_ansible_collection/actions/workflows/test.yml/badge.svg)](https://github.com/salsadigitalauorg/lagoon_ansible_collection/actions/workflows/test.yml)

This repository contains collections related to the [Lagoon](https://github.com/uselagoon/lagoon) application delivery platform.

The following collections are available:

* [api](/api)

## Update graphql schema
This uses the Lagoon CLI to acquire an updated token, then uses the `gql-cli` to download the schema.

```sh
# Install requirements.
python3 -m pip install -r api/requirements.txt

# Ensure a fresh token is available.
lagoon -l amazeeio whoami
export LAGOON_TOKEN=$(yq -r '.lagoons.amazeeio.token' ~/.lagoon.yml)

# Download the schema.
gql-cli https://api.lagoon.amazeeio.cloud/graphql --print-schema \
    --header Authorization:"Bearer $LAGOON_TOKEN" > api/tests/common/schema.graphql
```

## Run unit tests
```sh
docker-compose build
docker-compose run --rm test units -v --requirements
```

## Creating the docs

Linting the docs
```sh
docker compose build lint-docs
docker compose run --rm lint-docs
```

Build the docs:
```sh
docker compose build docs
docker compose up -d docs
```

Docs should be ready to browse at [http://localhost:9180](http://localhost:9180).
