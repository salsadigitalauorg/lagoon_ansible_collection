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
        project_id = self._task.args.get('project_id', None)
        if project_id is not None:
            project_id = int(project_id)  # Ensure project_id is an integer
        project_name = self._task.args.get('project_name', None)  

        print(f"State: {state}, Project ID: {project_id}")
        print(f"Data: {data}")

        result = {'result': [], 'invalid': [], 'changed': False, 'failed': False}

        if not isinstance(data, dict):
            result['failed'] = True
            result['message'] = 'Invalid data type; expected Dict'
            return result

        try:
            project_instance = Project(self.client).byName(project_name, ['metadata'])
            current_metadata = project_instance.projects[0]['metadata'] if project_instance.projects else {}
        except Exception as e:
            result['failed'] = True
            result['message'] = f"Error fetching project metadata: {e}"
            return result

        lagoonMetadata = Metadata(self.client)

        def is_change_required(key, value):
            # Adjusted to handle potentially missing current_metadata
            return current_metadata.get(key) != value

        if state == 'present':
            for key, value in data.items():
                if is_change_required(key, value):
                    try:
                        update_result = lagoonMetadata.update(project_id, key, value)
                        print(f"Updated {key}: {update_result}")
                        result['result'].append({key: value})
                        result['changed'] = True
                    except Exception as e:
                        print(f"Failed to update {key}: {e}")
                        result['invalid'].append(key)
                else:
                    print(f"No change required for {key}")

        elif state == 'absent':
            for key in data.keys():
                if key in current_metadata:
                    try:
                        remove_result = lagoonMetadata.remove(project_id, key)
                        print(f"Removed {key}: {remove_result}")
                        result['result'].append({key: 'removed'})
                        result['changed'] = True
                    except Exception as e:
                        print(f"Failed to remove {key}: {e}")
                        result['invalid'].append(key)
                else:
                    print(f"{key} not present in current metadata.")

        if result['invalid']:
            result['failed'] = True
            result['message'] = f"Errors occurred with keys: {result['invalid']}"

        print(f"Final result: {result}")
        return result
