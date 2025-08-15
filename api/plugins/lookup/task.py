DOCUMENTATION = """
  name: task
  author: Sonny Kieu <sonny.kieu@salsa.digital>
  short_description: Get a Lagoon task
  description:
      - This lookup returns the information for a Lagoon task.
  options:
    _terms:
      description: The task ID or task name to fetch
      required: True
    lagoon_api_endpoint:
      description: The Lagoon graphql endpoint
      type: string
      required: True
      vars:
        - name: lagoon_api_endpoint
    lagoon_api_token:
      description: The token for Lagoon graphql API
      type: string
      required: True
      vars:
        - name: lagoon_api_token
    validate_certs:
      description: Flag to control SSL certificate validation
      type: boolean
      default: False
    headers:
      description: HTTP request headers
      type: dictionary
      default: {}
    timeout:
      description: How long to wait for the server to send data before giving up
      type: float
      default: 10
      vars:
          - name: ansible_lookup_url_timeout
      env:
          - name: ANSIBLE_LOOKUP_URL_TIMEOUT
      ini:
          - section: url_lookup
            key: timeout
"""

EXAMPLES = """
- name: Retrieve a Lagoon task information by ID
  debug: msg="{{ lookup('lagoon.api.task', '115141') }}"
- name: Retrieve a Lagoon task information by task name
  debug: msg="{{ lookup('lagoon.api.task', 'lagoon-task-7wty3') }}"

- name: Retrieve a Lagoon task information by ID
  set_fact:
    task: "{{ lookup('lagoon.api.task', 115141) }}"
- name: Display the task name
  debug: var=task.taskName
- name: Display the task status
  debug: var=task.status
"""

from ansible_collections.lagoon.api.plugins.module_utils.gqlTask import Task
from ansible_collections.lagoon.api.plugins.lookup import LagoonLookupBase

class LookupModule(LagoonLookupBase):

    def run(self, terms, variables=None, **kwargs):
        ret = []
        self.set_options(var_options=variables, direct=kwargs)
        self.createClient()

        for term in terms:
            if isinstance(term, int):
                task = Task(self.client).byId(term)
            elif isinstance(term, str):
                if term.isdigit():
                    task = Task(self.client).byId(int(term))
                else:
                    task = Task(self.client).byTaskName(term)
            else:
                raise AnsibleError(
                    f"Unable to fetch Lagoon task by {term}; only task ID (int) or name (str) is accepted.")
            ret.append(task)

        return ret
