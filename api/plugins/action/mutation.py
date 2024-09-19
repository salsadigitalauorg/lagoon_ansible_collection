from . import LagoonActionBase
from gql.dsl import DSLMutation

class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self.createClient(task_vars)

        mutation = self._task.args.get('mutation')
        mutationArgs = self._task.args.get('arguments')
        subfields = self._task.args.get('subfields', ['id'])

        with self.client:
            mutationObj = self.client.build_dynamic_mutation(
                mutation, mutationArgs, subfields)
            res = self.client.execute_query_dynamic(DSLMutation(mutationObj))
            result['result'] = res[mutation]
            result['changed'] = True
        return result
