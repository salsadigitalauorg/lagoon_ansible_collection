from . import LagoonActionBase
from ..module_utils.gqlProject import Project
from ..module_utils.gqlDeployTargetConfig import DeployTargetConfig


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        result = {}
        result['result'] = []

        self.createClient(task_vars)

        self._display.vvv(f"With: {self._task.args}")
        lagoonProject = Project(self.client).byName(
            self._task.args.get('project'),
            ['id', 'name']).withDeployTargetConfigs()

        if len(lagoonProject.errors) > 0:
            result['failed'] = True
            return result

        state = self._task.args.get('state', 'present')
        replace = self._task.args.get('replace', False)
        configs = self._task.args.get('configs', [])

        for project in lagoonProject.projects:
            if state == "present":
                specified_branch_patterns = [config['branches'] for config in configs]
                existing_config_ids = [config['id'] for config in project["deployTargetConfigs"]]
                changes = determine_required_updates(
                    project["deployTargetConfigs"],
                    configs,
                )
                result['changed'] = False
                if len(changes) > 0:
                    for config in changes:
                        if replace and config.get('_existing_id'):
                            self._display.vvvv(f"deleting config {config}")
                            DeployTargetConfig(self.client).delete(
                                project['id'], config['_existing_id'])

                        self._display.vvvv(f"adding config {config}")
                        addResult = DeployTargetConfig(self.client).add(
                            int(project['id']),
                            config['branches'],
                            int(config['deployTarget']),
                            config['pullrequests'],
                            int(config['weight']) if 'weight' in config.keys() else 0
                        )
                        if addResult:
                            config['id'] = addResult['id']
                        else:
                            config['failed'] = True
                        result['result'].append(config)
                    result['changed'] = True
                # Cleanup code for deploytargetconfig when replace == true 
                if replace:
                    for existing_config in project["deployTargetConfigs"]:
                        if existing_config['id'] in existing_config_ids and existing_config['branches'] not in specified_branch_patterns:
                            self._display.vvvv(f"Deleting unmatched config with ID {existing_config['id']}")
                            if DeployTargetConfig(self.client).delete(project['id'], existing_config['id']):
                                result['result'].append({'id': existing_config['id'], 'deleted': True})
                                result['changed'] = True

            elif state == "absent":
                result['changed'] = False
                for c in project["deployTargetConfigs"]:
                    delete_desired = False
                    for given_config in configs:
                        if given_config['branches'] != c['branches']:
                            continue
                        if given_config['pullrequests'] != c['pullrequests']:
                            continue
                        if str(given_config['deployTarget']) != str(c['deployTarget']['id']):
                            continue
                        if str(given_config['weight']) != str(c['weight']):
                            continue
                        delete_desired = True
                        self._display.vvvv(f"deleting config {c}")
                        break
                    if delete_desired and DeployTargetConfig(self.client).delete(project['id'], c['id']):
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