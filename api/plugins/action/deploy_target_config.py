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
                addition_required, deletion_required = determine_required_updates(
                    project["deployTargetConfigs"],
                    configs,
                )
                result['changed'] = False

                # Handle deletions for deletion_required IDs
                if replace and len(deletion_required) > 0:
                    for config_id in deletion_required:
                        self._display.vvvv(f"deleting config with ID {config_id}")
                        DeployTargetConfig(self.client).delete(project['id'], config_id)
                        result['changed'] = True

                # Process additions and updates
                if len(addition_required) > 0:
                    for config in addition_required:
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
        addition_required = []
        deletion_required = []
        grouped_configs = {}

        for config in existing_configs:
            key = (config['branches'], config['pullrequests'], str(config['deployTarget']['id']), str(config['weight']))
            if key not in grouped_configs:
                grouped_configs[key] = []
            grouped_configs[key].append(config)
        

        for desired in desired_configs:
            key = (desired['branches'], desired['pullrequests'], str(desired['deployTarget']), str(desired['weight']))
            if key not in grouped_configs:
                addition_required.append(desired)
                

        for configs in grouped_configs.values():
            for config in configs:
                if not any(
                    config['branches'] == desired['branches'] and
                    str(config['deployTarget']['id']) == str(desired['deployTarget']) and
                    config['pullrequests'] == desired['pullrequests'] and
                    str(config['weight']) == str(desired['weight'])
                    for desired in desired_configs):
                    deletion_required.append(config['id'])
                    
        return addition_required, deletion_required