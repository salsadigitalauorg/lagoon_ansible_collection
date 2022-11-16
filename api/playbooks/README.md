# Lagoon playbooks

These playbooks can be used for testing the Lagoon queries as well as fetching information.

## Fetch all projects

```sh
ansible-playbook lagoon.api.project --limit localhost
```

## Fetch a single project

```sh
ansible-playbook lagoon.api.project --limit localhost --extra-vars project_name=some-project-name
```

## Fetch a project's variables

```sh
ansible-playbook lagoon.api.project_vars --limit localhost --extra-vars project_name=some-project-name
```

## Fetch all environments

```sh
ansible-playbook lagoon.api.environment --limit localhost
```

## Fetch a single environment

```sh
ansible-playbook lagoon.api.environment --limit localhost --extra-vars environment_ns=some-project-environment-ns
```

## Fetch an environment's variables

```sh
ansible-playbook lagoon.api.environment_vars --limit localhost --extra-vars environment_ns=some-project-environment-ns
```
