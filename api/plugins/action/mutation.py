from . import LagoonActionBase
from gql.dsl import DSLMutation, DSLQuery
from time import sleep
from typing import Any, Dict

class ActionModule(LagoonActionBase):

    WAIT_QUERIES = {
        'invokeRegisteredTask': {
            'query': 'taskById',
            'matchField': 'id',
            'statusField': 'status',
        }
    }

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self.createClient(task_vars)

        mutation = self._task.args.get('mutation')
        mutationArgs = self._task.args.get('arguments')
        subfields = self._task.args.get('subfields', ['id'])
        wait = self._task.args.get('wait', False)
        waitCondition = self._task.args.get('waitCondition', {
            'field': 'status',
            'value': ['complete', 'failed'],
        })

        with self.client:
            mutationObj = self.client.build_dynamic_mutation(
                mutation, mutationArgs, subfields)
            res = self.client.execute_query_dynamic(DSLMutation(mutationObj))
            result['result'] = res[mutation]
            result['changed'] = True

            if wait and mutation in self.WAIT_QUERIES:
                waitQuery = self.WAIT_QUERIES[mutation]

                qryArgs = {}
                if isinstance(waitQuery["matchField"], str):
                    qryArgs = {waitQuery["matchField"]: res[mutation][waitQuery["matchField"]]}
                else:
                    # Use a dictionary to match differing field names.
                    pass

                waitQry = self.client.build_dynamic_query(
                    query=waitQuery["query"],
                    args=qryArgs,
                    fields=[waitQuery["statusField"]],
                )
                waitResult = self.waitQuery(waitQuery["query"], waitQry, waitCondition)
                result['wait'] = waitResult
        return result

    def waitQuery(self, qryName, waitQry, waitCondition) -> Dict[str, Any]:
        waitResult = self.client.execute_query_dynamic(DSLQuery(waitQry))

        while not self.evaluateWaitCondition(qryName, waitResult, waitCondition):
            sleep(5)
            waitResult = self.client.execute_query_dynamic(DSLQuery(waitQry))

        return waitResult

    def evaluateWaitCondition(self, qryName, waitResult, waitCondition) -> bool:
        if waitCondition["field"] in waitResult[qryName]:
            if isinstance(waitCondition["value"], list):
                return waitResult[qryName][waitCondition["field"]] in waitCondition["value"]
            else:
                return waitResult[qryName][waitCondition["field"]] == waitCondition["value"]
        return False
