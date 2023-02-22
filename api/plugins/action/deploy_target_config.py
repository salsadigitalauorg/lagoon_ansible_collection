from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.utils.display import Display
from . import LagoonActionBase
from ..module_utils.gqlProject import Project
from ..module_utils.api_client import ApiClient


display = Display()

class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        result = {}
        result['result'] = []

        self.createClient(task_vars)

        display.vvv("With: " + self._task.args.get('project'))
        lagoonProject = Project(self.client).byName(self._task.args.get('project')).withDeployTargetConfigs()

        if len(lagoonProject.errors) > 0:
            result['failed'] = True
            return result

        state = self._task.args.get('state', 'present')
        replace = self._task.args.get('replace', False)

        for project in lagoonProject.projects:
            if state == "present":
                changes = determine_required_updates(
                    project["deployTargetConfigs"],
                    self._task.args.get('configs', []),
                )
                result['changed'] = False
                if len(changes) > 0:
                    for _, config in changes:
                        if replace:
                            self.client.DeployTargetConfig.delete(project['id'], changes['_existing_id'])

                        if self.client.DeployTargetConfig.add(
                                project['id'], 
                                config['branches'],
                                config['deployTarget'],
                                config['pullrequests'],
                                config['weight']
                            ):
                            result['result'].append(config)
                    result['changed'] = True
            elif state == "absent":
                result['changed'] = False
                for _, c in project["deployTargetConfigs"]:
                    if self.client.DeployTargetConfig.delete(project['id'], c['id']):
                        result['result'].append(c['id'])
                    result['changed'] = True
                    
        return result

def determine_required_updates(existing_configs, desired_configs):
    updates_required = []
    for config in desired_configs:
        found = False
        uptodate = True
        for existing_config in existing_configs:
            if existing_config['branches'] != config['branches']:
                continue
            else:
                config['_existing_id'] = existing_config['id']
                found = True

            if (existing_config['pullrequests'] != config['pullrequests'] or
                    str(existing_config['deployTarget']['id']) != str(config['deployTarget']) or
                    str(existing_config['weight']) != str(config['weight'])):
                config['_existing_id'] = existing_config['id']
                uptodate = False
                break

            if found:
                break

        if not found or not uptodate:
            updates_required.append(config)

    return updates_required
