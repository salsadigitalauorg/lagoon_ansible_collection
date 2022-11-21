# Ansible Collection - lagoon

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
docker run --rm -it -v \
    $PWD/api:/usr/share/collections/ansible_collections/lagoon/api \
    -w /usr/share/collections/ansible_collections/lagoon/api \
    ghcr.io/salsadigitalauorg/ansible-test:latest units -v --requirements
```
