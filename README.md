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

Install antsibull-docs
```sh
python3 -m pip install antsibull-docs
```

Lint the collection docs and fix any issues:
```sh
# Ensure the project is cloned into a directory suitable for Ansible
# collections to be recognised, in the format
# .../.../ansible_collections/lagoon/api.
# E.g ~/projects/ansible_collections/lagoon/api
ANSIBLE_COLLECTIONS_PATH=~/projects antsibull-docs lint-collection-docs --plugin-docs .
```

Generate the docs:
```sh
antsibull-docs sphinx-init --use-current --squash-hierarchy lagoon.api --dest-dir ../built-docs
cd ../built-docs
python3 -m pip install -r requirements.txt
./build.sh
```
