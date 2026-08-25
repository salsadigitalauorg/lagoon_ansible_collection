# Ansible Collection - salsadigitalauorg.lagoon
[![tests](https://github.com/salsadigitalauorg/lagoon_ansible_collection/actions/workflows/test.yml/badge.svg)](https://github.com/salsadigitalauorg/lagoon_ansible_collection/actions/workflows/test.yml)

An Ansible collection for interacting with the [Lagoon](https://github.com/uselagoon/lagoon)
application delivery platform GraphQL API.

This is the v3 collection (`salsadigitalauorg.lagoon`), a ground-up rewrite of
the v1 `lagoon.api` collection. It targets `ansible-core>=2.16`, has zero
runtime dependencies beyond `ansible-core`, and uses flat, single-level
GraphQL queries throughout. See
[`docs/plans/v3-refactor.md`](docs/plans/v3-refactor.md) for the design and
rationale.

> **v1 users:** the previous `lagoon.api` collection is still available at
> [`api/`](api) and continues to work unchanged during the v3 migration. See
> [`api/README.md`](api/README.md) for its documentation. It will be removed
> after the v3 migration completes.

## Requirements

* `ansible-core>=2.16`
* Python 3.11, 3.12, or 3.13

## Run unit tests

```sh
docker compose run --rm test-v3 units -v --requirements
```

## Linting the docs

```sh
docker compose run --rm lint-docs-v3
```

## Building the collection

```sh
ansible-galaxy collection build --force --output-path ./dist
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Security

See [SECURITY.md](SECURITY.md) for our security policy.

## Licence

This project is licensed under the MIT Licence. See [LICENSE](LICENSE) for details.
