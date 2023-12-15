import ruamel.yaml # To preserve comments & order.

from ansible.plugins.action import ActionBase

yaml = ruamel.yaml.YAML()
yaml.indent(mapping=2, sequence=4, offset=2)

class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):
        """Updates a .lagoon.yml file to add a cron job."""

        res = super(ActionModule, self).run(tmp, task_vars)

        config_file = self._task.args.get('config_file')
        crons = self._task.args.get('crons', {})
        routes = self._task.args.get('routes', {})
        monitoring_urls = self._task.args.get('monitoring_urls', {})
        state = self._task.args.get('state', 'present')

        if config_file is None:
            res['failed'] = True
            res['reason'] = 'config_file is required'
            return res

        if not crons and not routes and not monitoring_urls:
            res['failed'] = True
            res['reason'] = 'at least one of crons, routes, or monitoring_urls is required'
            return res

        if state not in ['present', 'absent']:
            res['failed'] = True
            res['reason'] = 'state must be present or absent'
            return res

        if crons:
            self._update_crons(config_file, crons, state, res)

        if routes:
            self._update_routes(config_file, routes, state, res)

        if monitoring_urls:
            self._update_monitoring_urls(config_file, monitoring_urls, state, res)

        return res

    def _update_crons(self, config_file, crons, state, res):
        if not isinstance(crons, dict):
            res['failed'] = True
            res['reason'] = 'crons must be a dictionary of env => [cronjobs]'
            return res

        for env in crons:
            envcrons = crons[env]
            if not len(envcrons):
                self._display.warning(f'No crons found for environment {env}')
                continue

            _validate_cron_jobs(envcrons, state, res)
            if res.get('failed', False):
                return res


        with open(config_file, 'r') as f:
            config_file_dict = yaml.load(f)

        _update_cron_jobs(crons, config_file_dict, state, res)

        with open(config_file, 'w') as f:
            yaml.dump(config_file_dict, f)

    def _update_routes(self, config_file, routes, state, res):
        pass

    def _update_monitoring_urls(self, config_file, monitoring_urls, state, res):
        pass

def _validate_cron_jobs(envcrons, state, res):
    if not isinstance(envcrons, list):
        res['failed'] = True
        res['reason'] = 'list of cron jobs expected per environment'
        return res
    for cron in envcrons:
        if not isinstance(cron, dict):
            res['failed'] = True
            res['reason'] = 'cron must be a dictionary'
            return res

        name = cron.get('name', False)
        schedule = cron.get('schedule', False)
        command = cron.get('command', False)
        if name == False:
            res['failed'] = True
            res['reason'] = f'cron name is required for cron job'
            return res
        if state == 'present' and schedule == False:
            res['failed'] = True
            res['reason'] = f'cron schedule is required for cron job {name}'
            return res
        if state == 'present' and command == False:
            res['failed'] = True
            res['reason'] = f'cron command is required for cron job {name}'
            return res

def _update_cron_jobs(crons, config_file_dict, state, res):
    for env in crons:
        envcrons = crons[env]
        try:
            existing_cronjobs = config_file_dict['environments'][env]['cronjobs']
        except KeyError:
            existing_cronjobs = []

        if state == 'absent' and not len(existing_cronjobs):
            continue

        config_file_dict['environments'][env]['cronjobs'] = _merge_env_crons(envcrons, existing_cronjobs, state, res)

def _merge_env_crons(envcrons, existing_cronjobs, state, res):
    cronjobs_to_write = []

    for cron in envcrons:
        # Are we updating an existing cron entry?
        update = False
        for existingCron in existing_cronjobs:
            if cron['name'] == existingCron['name']:
                if state == 'absent':
                    res['changed'] = True
                    continue

                update = True
                if cron['schedule'] != existingCron['schedule'] or cron['command'] != existingCron['command']:
                    res['changed'] = True
                    existingCron['schedule'] = cron['schedule']
                    existingCron['command'] = cron['command']
                    existingCron['service'] = cron.get('service', 'cli')
                cronjobs_to_write.append(existingCron)
                continue

            cronjobs_to_write.append(existingCron)

        if state == 'present' and not update:
            cron.update({'service': cron.get('service', 'cli')})
            cronjobs_to_write.append(cron)
            res['changed'] = True

    return cronjobs_to_write
