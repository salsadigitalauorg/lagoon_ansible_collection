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

        print("Task args: %s" % self._task.args)

        try:
            self.createClient(task_vars)
        except Exception as e:
            print(f"Error creating client: {e}")
            return {'failed': True, 'message': f"Error creating client: {e}"}

        state = self._task.args.get('state', 'present')
        data = self._task.args.get('data', None)
        project_id = int(self._task.args.get('project_id', None))
        project_name = self._task.args.get('project_name', None)  

        print(f"State: {state}, Project ID: {project_id}, Project Name: {project_name}")
        print(f"Data: {data}")

        result = {'result': [], 'invalid': [], 'changed': False}

        if not isinstance(data, list) and not isinstance(data, dict):
            return {
                'failed': True,
                'message': 'Invalid data type (%s) expected List or Dict' % (str(type(data)))
            }

        try:
            current_metadata = Project(self.client).byName(project_name, ['metadata']) if project_name else {}
            if not current_metadata:
                raise ValueError(f"No metadata found for project {project_name}")
        except Exception as e:
            print(f"Error fetching metadata for project {project_name}: {e}")
            return {'failed': True, 'message': f"Error fetching metadata for project {project_name}: {e}"}

        def is_change_required(key, value):
            # Check if the current metadata value is different from the intended update
            return current_metadata.get(key) != value

        lagoonMetadata = Metadata(self.client)
        
        if state == 'present':
            for item in (data if isinstance(data, list) else data.items()):
                key, value = (item['key'], item['value']) if isinstance(item, dict) else item
                if is_change_required(key, value):
                    try:
                        update_result = lagoonMetadata.update(project_id, key, value)
                        print(f"Update result for {key}: {update_result}")
                        result['result'].append(update_result)
                        result['changed'] = True
                    except Exception as e:
                        print(f"Error updating metadata for {key}: {e}")
                        result['invalid'].append(key)
                else:
                    print(f"No change required for {key}")

        elif state == 'absent':
            for key in (data if isinstance(data, list) else data.keys()):
                if key in current_metadata:
                    try:
                        remove_result = lagoonMetadata.remove(project_id, key)
                        print(f"Remove result for {key}: {remove_result}")
                        result['result'].append(remove_result)
                        result['changed'] = True
                    except Exception as e:
                        print(f"Error removing metadata for {key}: {e}")
                        result['invalid'].append(key)
                else:
                    print(f"No need to remove {key}, not present")

        if len(result['invalid']) > 0:
            result['failed'] = True
            result['message'] = f"Errors occurred with keys: {result['invalid']}"

        print(f"Final result: {result}")
        return result
