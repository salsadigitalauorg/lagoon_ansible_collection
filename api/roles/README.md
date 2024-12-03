# Lagoon roles

## Fetching a token
The following play can be used to fetch a token:
```yaml
- name: Fetch the lagoon token.
  hosts: localhost
  connection: local
  gather_facts: false
  become: false
  roles:
    - lagoon.api.common
  tasks:
    - include_role:
        name: lagoon.api.fetch_token
```

The token will now be available in the `lagoon_api_token` localhost variable. Default Lagoon variables are also exported from the `lagoon.api.common` role.

To reuse the token in another play, the following can be done:
```yaml
- name: Do other actions
  hosts: all
  gather_facts: false
  become: false
  tasks:
    - name: Use the lagoon token from localhost.
      set_fact: "{{ hostvars.localhost.lagoon_api_token }}"

    - name: Who am I?
      lagoon.api.whoami: {}
      register: whoami

    - name: Display user information.
      debug: var=whoami
```

## Fetch all projects
```yaml
- name: Fetch the lagoon token.
  hosts: localhost
  connection: local
  gather_facts: false
  become: false
  roles:
    - lagoon.api.common
  tasks:
    - include_role:
        name: lagoon.api.fetch_token

    - name: Retrieve all projects.
      set_fact:
        all_projects: "{{ lookup('lagoon.api.all_projects') }}"
```

## Fetch a single project
```yaml
- name: Fetch the lagoon token.
  hosts: localhost
  connection: local
  gather_facts: false
  become: false
  roles:
    - lagoon.api.common
  tasks:
    - include_role:
        name: lagoon.api.fetch_token

    - name: Retrieve project by name.
      set_fact:
        project_info: "{{ lookup('lagoon.api.project', project_name) }}"
```
