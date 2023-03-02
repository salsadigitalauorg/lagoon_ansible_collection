from . import LagoonActionBase
from ..module_utils.gqlMetadata import Metadata


class ActionModule(LagoonActionBase):
    ''' Perform comparisons on dictionary objects '''

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        self.createClient(task_vars)

        state = self._task.args.get('state', 'present')
        data = self._task.args.get('data', None)
        project_id = self._task.args.get('project_id', None)

        result = {}
        result['result'] = []
        result['invalid'] = []

        if not isinstance(data, list) and not isinstance(data, dict):
            return {
                'failed': True,
                'message': 'Invalid data type (%s) expected List or Dict' % (str(type(data)))
            }

        lagoonMetadata = Metadata(self.client)

        if state == 'present':
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        result['invalid'].append(item)
                        continue

                    if 'key' not in item and 'value' not in item:
                        result['invalid'].append(item)
                        continue

                    result['result'].append(lagoonMetadata.update(
                        project_id, item['key'], item['value']))

            else:
                for key, value in data.items():
                    result['result'].append(
                        lagoonMetadata.update(project_id, key, value))

        elif state == 'absent':
            if isinstance(data, list):
                for key in data:
                    result['result'].append(
                        lagoonMetadata.remove(project_id, key))
            else:
                for key, value in data.items():
                    result['result'].append(
                        lagoonMetadata.remove(project_id, key))

        if len(result['result']) > 0:
            result['changed'] = True

        if len(result['invalid']) > 0:
            result['failed'] = True

        return result
