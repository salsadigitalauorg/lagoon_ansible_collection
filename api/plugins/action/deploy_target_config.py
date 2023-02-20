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
        self.createClient(task_vars)

        display.vvv("With: " + self._task.args.get('project'))

        lagoon = ApiClient(
            task_vars.get('lagoon_api_endpoint'),
            task_vars.get('lagoon_api_token'),
            {
                'headers': self._task.args.get('headers', {}),
                'timeout': self._task.args.get('timeout', 30),
            }
        )

        lagoonProject = Project(self.client).byName(self._task.args.get('project')).withDeployTargetConfigs()

        if len(lagoonProject.errors) > 0:
            result['failed'] = True
            return result
        
        for project in lagoonProject.projects:
            if self._task.args.get('state', 'present') == 'present':
                add_or_update(
                    lagoon,
                    project,
                    self._task.args.get('replace', False),
                    project["deployTargetConfigs"],
                    self._task.args.get('configs', []),
                    result
                )
            elif self._task.args.get('state') == 'absent':
                delete_existing(
                    lagoon,
                    project,
                    project["deployTargetConfigs"],
                    result
                )

        return result


def add_or_update(lagoon, project, replace, existing_configs, desired_configs, result):
    if not existing_configs:
        updates_required = desired_configs
    elif not replace:
        updates_required = determine_required_updates(
            existing_configs, desired_configs)
    elif replace:
        delete_ids = [ec['id'] for ec in existing_configs]
        lagoon.deploy_target_config_delete(project['id'], delete_ids)
        updates_required = desired_configs

    if not updates_required:
        result['result'] = project['deployTargetConfigs']
        return

    result['result'] = lagoon.deploy_target_config_add(
        project['id'], updates_required)
    result['changed'] = True


def delete_existing(lagoon, project, existing_configs, result):
    if not existing_configs:
        return
    else:
        delete_ids = [ec['id'] for ec in existing_configs]
        result['result'] = lagoon.deploy_target_config_delete(
            project['id'], delete_ids)
        result['changed'] = True


def determine_required_updates(existing_configs, desired_configs):
    updates_required = []
    for config in desired_configs:
        found = False
        uptodate = True
        for existing_config in existing_configs:
            if existing_config['branches'] != config['branches']:
                continue
            else:
                found = True

            if (existing_config['pullrequests'] != config['pullrequests'] or
                    str(existing_config['deployTarget']['id']) != str(config['deployTarget']) or
                    str(existing_config['weight']) != str(config['weight'])):
                uptodate = False
                break

            if found:
                break

        if not found or not uptodate:
            updates_required.append(config)

    return updates_required
