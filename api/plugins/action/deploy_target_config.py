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
    required_updates = []
    marked_for_deletion = []

    # Existing configs mapped by branch for easier comparison
    existing_by_branch = {ec['branches']: ec for ec in existing_configs}

    # Desired branch patterns
    desired_branch_patterns = [dc['branches'] for dc in desired_configs]

    # Mark existing configs for deletion if their branches don't match any desired config
    for ec in existing_configs:
        if ec['branches'] not in desired_branch_patterns:
            marked_for_deletion.append(ec['id'])

    # Determine updates or additions for desired configs
    for dc in desired_configs:
        if dc['branches'] in existing_by_branch:
            ec = existing_by_branch[dc['branches']]
            # Compare other attributes to determine if an update is needed
            if (ec['pullrequests'] != dc['pullrequests'] or
                str(ec['deployTarget']['id']) != str(dc['deployTarget']) or
                str(ec['weight']) != str(dc.get('weight', 0))):
                # Mark for update, include '_existing_id'
                dc['_existing_id'] = ec['id']
                required_updates.append(dc)
        else:
            # New config, doesn't exist in existing configs
            required_updates.append(dc)

    return required_updates, marked_for_deletion
