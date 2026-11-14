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

## Code formatting

Python code is formatted and linted with [Ruff](https://docs.astral.sh/ruff/),
configured in [`ruff.toml`](/ruff.toml). CI checks formatting on every pull
request and will fail if it does not match.

The recommended setup is the pre-commit hook, which formats automatically so CI
never fails on something you could not see locally:

```sh
python3 -m pip install pre-commit && pre-commit install
```

Alternatively, format manually:

```sh
python3 -m pip install ruff==0.17.5
ruff format .          # format in place
ruff format --check .  # check only, as CI does
ruff check .           # lint (advisory, not yet enforced)
```

Or without installing anything locally:

```sh
docker compose run --rm lint-python            # check, as CI does
docker compose run --rm lint-python format .   # format in place
```

### Bumping the Ruff version

Different Ruff versions can produce different formatting, so the version is
pinned and **must be updated in all four places together**:

| File | Field |
| --- | --- |
| [`.github/workflows/lint.yml`](/.github/workflows/lint.yml) | `RUFF_VERSION` |
| [`.pre-commit-config.yaml`](/.pre-commit-config.yaml) | `rev` |
| [`docker-compose.yml`](/docker-compose.yml) | `lint-python` image tag |
| [`README.md`](/README.md) | the `pip install` above |

`ruff.toml` sets `target-version = "py39"`, matching the `test.yml` matrix and
`api/tests/config.yml`. Python 3.8 was dropped in 05f5ec2. If the floor ever
changes, update all three together.

The formatting baseline was applied in a single mechanical commit, listed in
[`.git-blame-ignore-revs`](/.git-blame-ignore-revs). To keep `git blame` useful
locally:

```sh
git config blame.ignoreRevsFile .git-blame-ignore-revs
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