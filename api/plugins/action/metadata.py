from . import LagoonActionBase
from ..module_utils.gqlMetadata import Metadata
from ..module_utils.gqlProject import Project
import json

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
        project_id = int(self._task.args.get('project_id', None))
        project_name = self._task.args.get('project_name', None)  

        print(f"State: {state}, Project ID: {project_id}")
        print(f"Data: {data}")

        result = {'result': [], 'invalid': [], 'changed': False}

        if not isinstance(data, list) and not isinstance(data, dict):
            return {
                'failed': True,
                'message': 'Invalid data type (%s) expected List or Dict' % (str(type(data)))
            }

        # Fetch current metadata using the optimized byName method
        current_metadata = {}
        if project_name:
            project_instance = Project(self.client).byName(project_name, ['metadata'])
            if project_instance:
                project_metadata = project_instance.get_metadata() if hasattr(project_instance, 'get_metadata') else {}
                current_metadata = project_metadata if isinstance(project_metadata, dict) else {}
            else:
                # Handle the case where the project is not found or an error occurred
                return {
                    'failed': True,
                    'message': f'Project {project_name} not found or could not retrieve metadata.'
                }


        def is_change_required(key, value):
            # Check if the current metadata value is different from the intended update
            return current_metadata.get(key) != value

        lagoonMetadata = Metadata(self.client)

        if state == 'present':
            for item in (data if isinstance(data, list) else data.items()):
                key, value = (item['key'], item['value']) if isinstance(item, dict) else item
                if is_change_required(key, value):
                    update_result = lagoonMetadata.update(project_id, key, value)
                    print(f"Update result: {update_result}")
                    result['result'].append(update_result)
                    result['changed'] = True
                else:
                    print(f"No change required for {key}")

        elif state == 'absent':
            for key in (data if isinstance(data, list) else data.keys()):
                if key in current_metadata:
                    remove_result = lagoonMetadata.remove(project_id, key)
                    print(f"Remove result: {remove_result}")
                    result['result'].append(remove_result)
                    result['changed'] = True
                else:
                    print(f"No need to remove {key}, not present")

        if len(result['invalid']) > 0:
            result['failed'] = True

        print(f"Final result: {result}")
        return result
