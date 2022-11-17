EXAMPLES = r'''
- name: Query specific fields for all projects.
  lagoon.api.query:
    query: allProjects
    mainType: Project
    fields:
      - id
      - name
  register: query_results

- name: Query specific fields for a project.
  lagoon.api.query:
    query: projectByName
    mainType: Project
    args:
      name: '{{ project_name }}'
    fields:
      - id
      - name
      - branches
      - metadata
    subFields:
      kubernetes:
        type: Kubernetes
        fields:
          - id
          - name
  register: query_results

- name: Query variables for a project.
  lagoon.api.query:
    query: projectByName
    mainType: Project
    args:
      name: '{{ project_name }}'
    subFields:
      envVariables:
        type: EnvKeyValue
        fields:
          - id
          - name
          - value
          - scope
  register: query_results
'''

from ansible_collections.lagoon.api.plugins.action import LagoonActionBase
from gql.dsl import DSLQuery, dsl_gql
from graphql import print_ast

class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self.createClient(task_vars)

        query = self._task.args.get('query')
        mainType = self._task.args.get('mainType')
        args = self._task.args.get('args', {})
        fields = self._task.args.get('fields', [])
        subFields = self._task.args.get('subFields', {})

        with self.client:
            queryObj = self.client.build_dynamic_query(
                query, mainType, args, fields, subFields)
            query_ast = dsl_gql(DSLQuery(queryObj))
            self._display.vvvv(f"Built query: \n{print_ast(query_ast)}")
            res = self.client.execute_query_dynamic(queryObj)
            result['result'] = res[query]
        return result
