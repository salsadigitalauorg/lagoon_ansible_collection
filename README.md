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

## Running action plugins ad hoc
Navigate to the collection's directory then run the following:

```sh
export ANSIBLE_ACTION_PLUGINS='{{CWD}}/plugins/action:{{ ANSIBLE_HOME ~ "/plugins/action:/usr/share/ansible/plugins/action" }}'

# Example using the lagoon.api.config plugin.
ansible localhost -m config -a '{"config_file":"'$HOME'/govcms/scaffold/.lagoon.yml","crons":{"master":[{"name":"custom cron","command":"drush cron", "schedule":"M * * * *"}]},"state":"absent"}'
```
