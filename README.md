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
docker compose build test
docker compose run --rm test units -v --requirements
```

## Creating the docs

To view the module docs in the terminal, run
```sh
# List modules
docker compose run --rm --entrypoint="" -T lint-docs bash -c \
  'ansible-doc -t module lagoon.api -l'

# Specific module (group)
docker compose run --rm --entrypoint="" -T lint-docs bash -c \
  'ansible-doc -t module lagoon.api.group'
```

Linting the docs
```sh
docker compose run --rm lint-docs
```

Build & serve the docs:
```sh
docker compose up -d docs
```

Docs should be ready to browse at [http://localhost:9180](http://localhost:9180).


## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Security

See [SECURITY.md](SECURITY.md) for our security policy.

## Licence

This project is licensed under the MIT Licence. See [LICENSE](LICENSE) for details.