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
    deletion_required = [
        config['id']
        for config in existing_configs
        if not any(
            config['branches'] == desired['branches']
            for desired in desired_configs
        )
    ]

    for desired in desired_configs:
        found = False
        uptodate = True
        for existing_config in existing_configs:
            if existing_config['branches'] != desired['branches']:
                continue

            desired['_existing_id'] = existing_config['id']
            found = True
            print("Found a match based on branches. Appended _existing_id:", desired) # checking desired

            # Mark for update (or in this context, addition) if there are discrepancies in any key property
            if (existing_config['pullrequests'] != desired['pullrequests'] or
                    str(existing_config['deployTarget']['id']) != str(desired['deployTarget']) or
                    str(existing_config['weight']) != str(desired['weight'])):
                desired['_existing_id'] = existing_config['id']
                uptodate = False
                print("Discrepancy found. Marked as not up-to-date:", desired)
                break

        if not found or not uptodate:
            addition_required.append(desired)
            print("Added to addition_required:", desired) # checking desired 

    # Filter out additions for configs already marked for deletion
    additions_filtered = [
        config for config in addition_required
        if config.get('_existing_id') not in deletion_required
    ]

    print("Final additions_filtered:", additions_filtered) # checking final addititions filtered
    print("deletion_required:", deletion_required)  # checking final deletion required

    return additions_filtered, deletion_required
