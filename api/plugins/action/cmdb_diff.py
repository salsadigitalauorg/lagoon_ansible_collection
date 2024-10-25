#
# Action: cmdb_diff
#
# This performs logic comparisions between local configuration state and
# remote Lagoon tracked state. It supports various comparison modes to
# assist with granularity in the compare.
#
# Parameters:
#    head: [list] The expected head state of the variables
#    base: [list] The remote state of the variables
#    ignore (optional): [list] A list of variable names to skip
#    mode(optional): [string] strict|key
#    keys(optional): [list] required when key, variable keys to match on
#
# Returns:
#    The action_plugin will update the 'ansible_facts' variable definition
#    with all vairables that have comparison differences. These will be
#    accessible via 'ansible_facts.cmdb' if differences are detected.
from __future__ import (absolute_import, division, print_function)
from json.decoder import JSONDecodeError
__metaclass__ = type

from ansible.plugins.action import ActionBase
import json

# Compare certainkeys of the object to ensure parity.
#
# @param head_row {dict}
#    The expected values.
# @param base_row {dict}
#    The values to compare against the head values.
# @param keys {list}
#    A list of keys to compare between the dicts.
#
# @return {Tupple}
#    Status, key, new value, old value
def key_diff(head_row, base_row, keys):
    for key in keys:
        if key not in head_row or key not in base_row:
            # Should never get here - this is just defensive coding.
            return True, key, '', ''

        head_value = head_row[key]
        base_value = base_row[key]

        if key == 'scope':
            head_value = str(head_row[key]).lower()
            base_value = str(base_row[key]).lower()

        # Unquoted yaml values are cast to bool - this
        # causes false positives when comparing as Lagoon
        # stores all variables as strings.
        if isinstance(base_row[key], bool) or isinstance(head_row[key], bool):
            head_value = str(head_row[key]).lower()
            base_value = str(base_row[key]).lower()

        if head_value != base_value:
            return True, key, head_row[key].lower(), base_row[key].lower()

    return False, False, False, False

# Lazy comparison - should be using key for CMDB.
def strict_diff(head_row, base_row):
    return head_row == base_row


class ActionModule(ActionBase):
    ''' Perform copmarisons on dictionary objects '''

    TRANSFERS_FILES = False
    _VALID_ARGS = frozenset(('base', 'head', 'mode', 'keys', 'remove', 'ignore'))

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = {}

        if 'base' not in self._task.args and 'head' not in self._task.args:
            return {"failed": True, "msg": "'base' and 'head' are required to perform the diff"}

        facts = {}
        facts['remove'] = []
        facts['write'] = []
        facts['diff_message'] = []

        head = self._task.args["head"]
        base = self._task.args["base"]
        remove_ignore = self._task.args['ignore'] if 'ignore' in self._task.args else []
        mode = self._task.args['mode'] if 'mode' in self._task.args else 'strict'
        keys = self._task.args["keys"] if "keys" in self._task.args else []
        remove = bool(self._task.args["keys"]) if "keys" in self._task.args else True
        result = {}

        if mode not in ['strict', 'key']:
            return {"failed": True, "msg": "Unsupported diff mode '{mode}'".format(mode=mode)}

        if mode == 'key' and len(keys) == 0:
            return {"failed": True, "msg": "Unsupported diff mode '{mode}'".format(mode=mode)}

        # Set the diff method to use when processing a row.
        for head_row in head:
            base_match = {}
            name = head_row['name'] if 'name' in head_row else 'Undef'
            sensitive = True if 'sensitive' in head_row and bool(head_row['sensitive']) else False

            if 'name' in head_row and head_row['name'] in remove_ignore:
                continue

            for base_row in base:
                if base_row['name'] == head_row['name']:
                    base_match = base_row
                    break

            if base_match == {}:
                # We didn't find a match to compare, so we assume that we need to add this row.
                facts['write'].append(head_row)
                facts['diff_message'].append('+ {name}'.format(name=head_row['name']))
                continue

            # @TODO: Remove support for json variables.
            if 'type' in head_row and head_row['type'] == 'json' and isinstance(base_match['value'], str):
                # This will fail with single quoted json strings.
                # Note: ast.literal_eval can decode single quoted json strings.
                try:
                    json.loads(base_match['value'])
                    # Skip handling valid JSON from Lagoon - CMDB will currently
                    # insert bad data.
                    continue
                except JSONDecodeError:
                    facts['remove'].append(base_row)
                    facts['diff_message'].append('{name} is invalid JSON marking for write'.format(
                        name=name
                    ))
                    continue

            if mode == 'key':
                diff_status, key, new_val, old_val = key_diff(head_row, base_match, keys)
                if diff_status:
                    # Head differs from base we need to update this item.
                    facts['write'].append(head_row)
                    facts['remove'].append(base_row)
                    facts['diff_message'].append('{name}: [{key}] -{old} +{new}'.format(
                        name=name,
                        key=key,
                        old=old_val if not sensitive else '****',
                        new=new_val if not sensitive else '****'
                    ))
                    continue
            else:
                if strict_diff(head_row, base_match):
                    # The objects were different completely, write.
                    facts['write'].append(head_row)
                    facts['remove'].append(base_row)
                    continue

        if remove:
            for base_row in base:
                head_match = {}

                if 'name' in base_row and base_row['name'] in remove_ignore:
                    continue

                for head_row in head:
                    if head_row['name'] == base_row['name']:
                        head_match = head_row

                if head_match == {}:
                    # Base had values not present in head, they should be removed.
                    facts['remove'].append(base_row)
                    facts['diff_message'].append('- {name}'.format(name=base_row['name']))

        # As lagoon api now has the capability to update the value of a variable, we need to filter out items that are in facts['write'] from facts['remove']
        # Before setting the final values of facts['remove'], filter out items that are also in facts['write']
        names_in_write = set([item['name'] for item in facts['write']])
        final_remove_list = [item for item in facts['remove'] if item['name'] not in names_in_write]

        # Set the filtered list to facts['remove']
        facts['remove'] = final_remove_list

        # Remove dupes from the lists so Lagoon is okay.
        facts['write'] = list({v['name']: v for v in facts['write']}.values())
        facts['remove'] = list({v['name']: v for v in facts['remove']}.values())

        # Standard Ansible stuff.
        result = super(ActionModule, self).run(tmp, task_vars)

        # This merges to the ansible_facts global variable for the current host. This
        # means that after the plugin calculates the diff we can access the results in
        # the plays with '{{ ansible_facts.cmdb }}'
        result['ansible_facts'] = {"cmdb": facts}
        return result