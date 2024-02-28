from . import LagoonActionBase
from ..module_utils.gqlMetadata import Metadata
from ..module_utils.gqlProject import Project
import json

class ActionModule(LagoonActionBase):
    '''Perform comparisons on dictionary objects and update metadata accordingly.'''

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

        print(f"rmk-debug: State={state}, Project ID={project_id}, Project Name={project_name}")

        result = {'result': [], 'invalid': [], 'changed': False, 'failed': False}

        if not isinstance(data, (dict, list)):
            result['failed'] = True
            result['message'] = 'Invalid data type; expected Dict or List'
            print("rmk-debug: Invalid data type provided.")
            return result

        try:
            if project_name:
                project_instance = Project(self.client).byName(project_name, ['metadata'])
                print(f"rmk-debug: project_instance details: {project_instance}")
                current_metadata = project_instance.projects[0]['metadata'] if project_instance.projects else {}
                print(f"rmk-debug: current_metadata: {current_metadata}")
                print(f"rmk-debug: Fetched current metadata for project '{project_name}'.")
            else:
                current_metadata = {}  # Assuming no project name means no current metadata
                print("rmk-debug: No project name provided, proceeding without current metadata.")
        except Exception as e:
            result['failed'] = True
            result['message'] = f"Error fetching project metadata: {e}"
            print(f"rmk-debug: Exception caught while fetching project metadata: {e}")
            return result

        lagoonMetadata = Metadata(self.client)

        def is_change_required(key, value):
            required = current_metadata.get(key) != value
            print(f"rmk-debug: Change required for '{key}'? {required}")
            return required

        if state == 'present':
            print("rmk-debug: Processing state 'present'.")
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict) or 'key' not in item or 'value' not in item:
                        result['invalid'].append(item)
                        print(f"rmk-debug: Invalid item skipped: {item}")
                        continue
                    key, value = item['key'], item['value']
                    if is_change_required(key, value):
                        try:
                            update_result = lagoonMetadata.update(project_id, key, value)
                            result['result'].append({key: value})
                            result['changed'] = True
                            print(f"rmk-debug: Updated metadata list for key '{key}' with value '{value}'.")
                        except Exception as e:
                            result['invalid'].append(key)
                            print(f"rmk-debug: Exception caught list while updating '{key}': {e}")
            else:  # if data is a dict
                for key, value in data.items():
                    if is_change_required(key, value):
                        try:
                            update_result = lagoonMetadata.update(project_id, key, value)
                            result['result'].append({key: value})
                            result['changed'] = True
                            print(f"rmk-debug: Updated metadata for key '{key}' with value '{value}'.")
                        except Exception as e:
                            result['invalid'].append(key)
                            print(f"rmk-debug: Exception caught while updating '{key}': {e}")

        elif state == 'absent':
            print("rmk-debug: Processing state 'absent'.")
            keys_to_remove = [k if isinstance(data, list) else k for k in (data if isinstance(data, list) else data.keys())]
            for key in keys_to_remove:
                if isinstance(key, dict):  # Handle unexpected dictionary
                    print(f"rmk-debug: Skipping unexpected dict in keys_to_remove: {key}")
                    continue  # Skip or handle dictionaries differently
                if key in current_metadata:
                    try:
                        remove_result = lagoonMetadata.remove(project_id, key)
                        result['result'].append({key: 'removed'})
                        result['changed'] = True
                        print(f"rmk-debug: Removed metadata for key '{key}'.")
                    except Exception as e:
                        result['invalid'].append(key)
                        print(f"rmk-debug: Exception caught while removing '{key}': {e}")

        if result['invalid']:
            result['failed'] = True
            result['message'] = f"Errors occurred with keys: {', '.join(result['invalid'])}"
            print(f"rmk-debug: Operation completed with errors: {result['invalid']}")

        print(f"rmk-debug: Final result: {result}")
        return result
