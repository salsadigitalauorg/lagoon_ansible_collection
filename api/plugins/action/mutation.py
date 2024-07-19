from gql.dsl import DSLMutation
from . import LagoonActionBase

class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self.createClient(task_vars)

        mutation = self._task.args.get('mutation')
        input = self._task.args.get('input')
        selectType = self._task.args.get('select', None)
        subfields = self._task.args.get('subfields', [])

        with self.client:
            mutationObj = self.client.build_dynamic_mutation(
                mutation, input, selectType, subfields)
            res = self.client.execute_query_dynamic(DSLMutation(mutationObj))
            result['result'] = res[mutation]
            result['changed'] = True
        return result
