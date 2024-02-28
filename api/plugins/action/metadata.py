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
        print(f"Debug: Task arguments - {self._task.args}")  # Debug print

        self.createClient(task_vars)

        state = self._task.args.get('state', 'present')
        data = self._task.args.get('data', None)
        project_id = int(self._task.args.get('project_id', None))
        project_name = self._task.args.get('project_name', None)  

        print(f"Debug: State - {state}, Project ID - {project_id}, Project Name - {project_name}")  # Debug print
        print(f"Debug: Data - {data}")  # Debug print

        result = {'result': [], 'invalid': [], 'changed': False}

        if not isinstance(data, list) and not isinstance(data, dict):
            print("Debug: Data is neither a list nor a dict")  # Debug print
            return {
                'failed': True,
                'message': 'Invalid data type (%s) expected List or Dict' % (str(type(data)))
            }

        # Fetch current metadata using the optimized byName method
        current_metadata = {}
        if project_name:
            print(f"Debug: Fetching metadata for project {project_name}")  # Debug print
            project_instance = Project(self.client).byName(project_name, ['metadata'])
            print(f"Debug: Project instance - {project_instance}")  # Debug print
            if project_instance:
                # Assuming get_metadata() is the correct method to fetch metadata, replace it with the actual method if different
                project_metadata = project_instance.get_metadata() if hasattr(project_instance, 'get_metadata') else {}
                print(f"Debug: Current metadata - {project_metadata}")  # Debug print
                current_metadata = project_metadata if isinstance(project_metadata, dict) else {}
            else:
                print("Debug: Project instance is None")  # Debug print
                return {
                    'failed': True,
                    'message': f'Project {project_name} not found or could not retrieve metadata.'
                }


        def is_change_required(key, value):
            # Check if the current metadata value is different from the intended update
            required = current_metadata.get(key) != value
            print(f"Debug: Is change required for {key}? - {required}")  # Debug print
            return required

        lagoonMetadata = Metadata(self.client)

        if state == 'present':
            for item in (data if isinstance(data, list) else data.items()):
                key, value = (item['key'], item['value']) if isinstance(item, dict) else item
                print(f"Debug: Processing {key} with value {value}")  # Debug print
                if is_change_required(key, value):
                    update_result = lagoonMetadata.update(project_id, key, value)
                    print(f"Debug: Update result for {key} - {update_result}")  # Debug print
                    result['result'].append(update_result)
                    result['changed'] = True
                else:
                    print(f"Debug: No change required for {key}")

        elif state == 'absent':
            for key in (data if isinstance(data, list) else data.keys()):
                print(f"Debug: Checking for absence of {key}")  # Debug print
                if key in current_metadata:
                    remove_result = lagoonMetadata.remove(project_id, key)
                    print(f"Debug: Remove result for {key} - {remove_result}")  # Debug print
                    result['result'].append(remove_result)
                    result['changed'] = True
                else:
                    print(f"Debug: No need to remove {key}, not present")

        if len(result['invalid']) > 0:
            result['failed'] = True

        print(f"Debug: Final result - {result}")
        return result
