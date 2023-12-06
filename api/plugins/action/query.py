from gql.dsl import DSLQuery
from . import LagoonActionBase

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
            res = self.client.execute_query_dynamic(DSLQuery(queryObj))
            result['result'] = res[query]
        return result
