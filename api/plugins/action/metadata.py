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

        result = {'result': [], 'invalid': [], 'changed': False, 'failed': False}

        if not isinstance(data, (dict, list)):
            result['failed'] = True
            result['message'] = 'Invalid data type; expected Dict or List'
            return result

        try:
            if project_name:
                project_instance = Project(self.client).byName(project_name, ['metadata'])
                current_metadata = project_instance.projects[0]['metadata'] if project_instance.projects else {}
            else:
                current_metadata = {}  # Assuming no project name means no current metadata
        except Exception as e:
            result['failed'] = True
            result['message'] = f"Error fetching project metadata: {e}"
            return result

        lagoonMetadata = Metadata(self.client)

        def is_change_required(key, value):
            required = current_metadata.get(key) != value
            return required

        if state == 'present':
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict) or 'key' not in item or 'value' not in item:
                        result['invalid'].append(item)
                        continue
                    key, value = item['key'], item['value']
                    if is_change_required(key, value):
                        try:
                            update_result = lagoonMetadata.update(project_id, key, value)
                            result['result'].append({key: value})
                            result['changed'] = True
                        except Exception as e:
                            result['invalid'].append(key)
            else:  # if data is a dict
                for key, value in data.items():
                    if is_change_required(key, value):
                        try:
                            update_result = lagoonMetadata.update(project_id, key, value)
                            result['result'].append({key: value})
                            result['changed'] = True
                        except Exception as e:
                            result['invalid'].append(key)

        elif state == 'absent':
            # handle both list and dictionaries
            if isinstance(data, list):
                keys_to_remove = []
                for item in data:
                    if isinstance(item, dict):
                        keys_to_remove.append(item['key'])
                    else:
                        keys_to_remove.append(item)
            else:
                keys_to_remove = list(data.keys())


            for key in keys_to_remove:
                if key in current_metadata:
                    try:
                        remove_result = lagoonMetadata.remove(project_id, key)
                        result['result'].append({key: 'removed'})
                        result['changed'] = True
                    except Exception as e:
                        result['invalid'].append(key)

        if result['invalid']:
            result['failed'] = True
            result['message'] = f"Errors occurred with keys: {', '.join(result['invalid'])}"

        return result
