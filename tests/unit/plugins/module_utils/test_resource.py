from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ast
import os
import unittest
from unittest.mock import MagicMock

from .....plugins.module_utils.resource import LagoonResourceModule

_FIELDS = ('id', 'name', 'gitUrl', 'autoIdle')
_DIFF_IGNORE = ('id',)


def _module(state='present', check_mode=False, **params):
    module = MagicMock()
    module.check_mode = check_mode
    module.params = dict(state=state, name='my-project', git_url=None,
                          auto_idle=None)
    module.params.update(params)
    return module


def _resource_module(read_result, no_log_fields=(),
                      enum_case_normalise=None):
    """A faithful fake resource: create/update/delete actually mutate
    the state ``read`` returns, so a real mutation followed by the
    re-read produces genuinely post-mutation data -- exactly what a
    real API round-trip would, and what a "just echo desired back"
    shortcut would not.
    """
    calls = {'create': [], 'update': [], 'delete': [], 'read': 0}
    box = {'state': dict(read_result) if read_result else None}

    def _read(client):
        calls['read'] += 1
        return dict(box['state']) if box['state'] is not None else None

    def _create(client, desired):
        calls['create'].append(dict(desired))
        box['state'] = dict(desired)
        box['state'].setdefault('id', 1)

    def _update(client, current, desired, changed_fields):
        calls['update'].append((dict(current), dict(desired),
                                 list(changed_fields)))
        box['state'].update(desired)

    def _delete(client, current):
        calls['delete'].append(dict(current))
        box['state'] = None

    resource = LagoonResourceModule(
        fields=_FIELDS, diff_ignore=_DIFF_IGNORE,
        no_log_fields=no_log_fields,
        enum_case_normalise=enum_case_normalise,
        read=_read, create=_create, update=_update, delete=_delete)
    return resource, calls


class TestCreate(unittest.TestCase):

    def test_absent_remotely_creates(self):
        resource, calls = _resource_module(None)
        module = _module(git_url='https://example.test/repo.git')

        result = resource.run(module, client=None)

        self.assertTrue(result['changed'])
        self.assertEqual(len(calls['create']), 1)
        self.assertEqual(calls['update'], [])
        self.assertEqual(calls['delete'], [])

    def test_check_mode_creates_no_mutation_call(self):
        resource, calls = _resource_module(None)
        module = _module(check_mode=True,
                          git_url='https://example.test/repo.git')

        result = resource.run(module, client=None)

        self.assertTrue(result['changed'])
        self.assertEqual(calls['create'], [])


class TestNoOp(unittest.TestCase):

    def test_present_no_diff_reports_unchanged(self):
        current = {'id': 1, 'name': 'my-project',
                   'gitUrl': 'https://example.test/repo.git',
                   'autoIdle': True}
        resource, calls = _resource_module(current)
        module = _module(git_url='https://example.test/repo.git',
                          auto_idle=True)

        result = resource.run(module, client=None)

        self.assertFalse(result['changed'])
        self.assertEqual(calls['create'], [])
        self.assertEqual(calls['update'], [])

    def test_check_mode_no_diff_reports_unchanged(self):
        current = {'id': 1, 'name': 'my-project',
                   'gitUrl': 'https://example.test/repo.git',
                   'autoIdle': True}
        resource, calls = _resource_module(current)
        module = _module(check_mode=True,
                          git_url='https://example.test/repo.git',
                          auto_idle=True)

        result = resource.run(module, client=None)

        self.assertFalse(result['changed'])
        self.assertEqual(calls['create'], [])


class TestUpdate(unittest.TestCase):

    def test_present_with_diff_updates(self):
        current = {'id': 1, 'name': 'my-project',
                   'gitUrl': 'https://example.test/old.git',
                   'autoIdle': True}
        resource, calls = _resource_module(current)
        module = _module(git_url='https://example.test/new.git',
                          auto_idle=True)

        result = resource.run(module, client=None)

        self.assertTrue(result['changed'])
        self.assertEqual(len(calls['update']), 1)
        _, _, changed_fields = calls['update'][0]
        self.assertEqual(changed_fields, ['gitUrl'])

    def test_check_mode_update_no_mutation_call(self):
        current = {'id': 1, 'name': 'my-project',
                   'gitUrl': 'https://example.test/old.git',
                   'autoIdle': True}

        real_resource, real_calls = _resource_module(current)
        real_result = real_resource.run(
            _module(git_url='https://example.test/new.git', auto_idle=True),
            client=None)

        check_resource, check_calls = _resource_module(current)
        check_result = check_resource.run(
            _module(check_mode=True,
                    git_url='https://example.test/new.git', auto_idle=True),
            client=None)

        self.assertEqual(real_calls['update'], [
            (current,
             {'name': 'my-project',
              'gitUrl': 'https://example.test/new.git', 'autoIdle': True},
             ['gitUrl'])])
        self.assertEqual(check_calls['update'], [])
        self.assertEqual(check_result['changed'], real_result['changed'])
        self.assertEqual(check_result['diff'], real_result['diff'])


class TestDelete(unittest.TestCase):

    def test_present_remotely_with_state_absent_deletes(self):
        current = {'id': 1, 'name': 'my-project',
                   'gitUrl': 'https://example.test/repo.git',
                   'autoIdle': True}
        resource, calls = _resource_module(current)
        module = _module(state='absent')

        result = resource.run(module, client=None)

        self.assertTrue(result['changed'])
        self.assertEqual(len(calls['delete']), 1)

    def test_check_mode_delete_no_mutation_call(self):
        current = {'id': 1, 'name': 'my-project',
                   'gitUrl': 'https://example.test/repo.git',
                   'autoIdle': True}
        resource, calls = _resource_module(current)
        module = _module(state='absent', check_mode=True)

        result = resource.run(module, client=None)

        self.assertTrue(result['changed'])
        self.assertEqual(calls['delete'], [])


class TestAbsentAlready(unittest.TestCase):

    def test_absent_remotely_with_state_absent_is_noop(self):
        resource, calls = _resource_module(None)
        module = _module(state='absent')

        result = resource.run(module, client=None)

        self.assertFalse(result['changed'])
        self.assertEqual(calls['delete'], [])

    def test_check_mode_absent_already_is_noop(self):
        resource, calls = _resource_module(None)
        module = _module(state='absent', check_mode=True)

        result = resource.run(module, client=None)

        self.assertFalse(result['changed'])
        self.assertEqual(calls['delete'], [])


class TestDiffIgnore(unittest.TestCase):

    def test_id_excluded_from_diff_even_when_present_in_current(self):
        current = {'id': 999, 'name': 'my-project',
                   'gitUrl': 'https://example.test/repo.git',
                   'autoIdle': True}
        resource, calls = _resource_module(current)
        module = _module(git_url='https://example.test/repo.git',
                          auto_idle=True)

        result = resource.run(module, client=None)

        self.assertFalse(result['changed'])
        self.assertEqual(calls['update'], [])


class TestNoLogFields(unittest.TestCase):

    def _resource_with_value(self, current_value, desired_value,
                              check_mode=False):
        pre = {'id': 1, 'name': 'env-var', 'value': current_value}
        post = {'id': 1, 'name': 'env-var', 'value': desired_value}
        reads = iter([pre, post] if not check_mode else [pre])
        resource = LagoonResourceModule(
            fields=('id', 'name', 'value'), diff_ignore=('id',),
            no_log_fields=('value',),
            read=lambda client: next(reads),
            create=lambda client, desired: None,
            update=lambda client, current, desired, changed: None,
            delete=lambda client, current: None)
        module = _module(name='env-var', check_mode=check_mode)
        module.params['value'] = desired_value
        return resource, module

    def test_value_absent_from_diff_but_change_flagged(self):
        resource, module = self._resource_with_value('old-secret',
                                                        'new-secret')
        result = resource.run(module, client=None)

        diff = result['diff']
        self.assertNotIn('value', diff['before'] or {})
        self.assertNotIn('value', diff['after'] or {})
        self.assertEqual(diff.get('changed_no_log_fields'), ['value'])
        self.assertNotIn('old-secret', str(diff))
        self.assertNotIn('new-secret', str(diff))

    def test_value_unchanged_not_flagged(self):
        resource, module = self._resource_with_value('same-secret',
                                                        'same-secret')
        result = resource.run(module, client=None)

        self.assertFalse(result['changed'])
        self.assertNotIn('changed_no_log_fields', (result['diff'] or {}))

    def test_check_mode_still_withholds_value(self):
        resource, module = self._resource_with_value(
            'old-secret', 'new-secret', check_mode=True)
        result = resource.run(module, client=None)

        diff = result['diff']
        self.assertNotIn('old-secret', str(diff))
        self.assertNotIn('new-secret', str(diff))
        self.assertEqual(diff.get('changed_no_log_fields'), ['value'])


class TestEnumCaseNormalise(unittest.TestCase):

    def test_read_side_uppercased_before_diff(self):
        current = {'id': 1, 'name': 'my-project', 'scope': 'runtime'}
        resource = LagoonResourceModule(
            fields=('id', 'name', 'scope'), diff_ignore=('id',),
            enum_case_normalise={'scope': 'upper'},
            read=lambda client: current,
            create=lambda client, desired: None,
            update=lambda client, current, desired, changed: None,
            delete=lambda client, current: None)
        module = _module(name='my-project')
        module.params['scope'] = 'RUNTIME'

        result = resource.run(module, client=None)

        self.assertFalse(result['changed'])


class TestRereadAfterMutation(unittest.TestCase):

    def test_update_returns_post_mutation_state_not_desired(self):
        pre = {'id': 1, 'name': 'my-project',
               'gitUrl': 'https://example.test/old.git', 'autoIdle': True}
        post = {'id': 1, 'name': 'my-project',
                'gitUrl': 'https://example.test/new.git',
                'autoIdle': False}
        reads = iter([pre, post])
        resource = LagoonResourceModule(
            fields=_FIELDS, diff_ignore=_DIFF_IGNORE,
            read=lambda client: next(reads),
            create=lambda client, desired: None,
            update=lambda client, current, desired, changed: None,
            delete=lambda client, current: None)
        module = _module(git_url='https://example.test/new.git',
                          auto_idle=True)

        result = resource.run(module, client=None)

        self.assertEqual(result['resource'], post)
        self.assertNotEqual(result['resource'], module.params)

    def test_create_returns_post_mutation_state_not_desired(self):
        created = {'id': 5, 'name': 'my-project',
                   'gitUrl': 'https://example.test/repo.git',
                   'autoIdle': True}
        reads = iter([None, created])
        resource = LagoonResourceModule(
            fields=_FIELDS, diff_ignore=_DIFF_IGNORE,
            read=lambda client: next(reads),
            create=lambda client, desired: None,
            update=lambda client, current, desired, changed: None,
            delete=lambda client, current: None)
        module = _module(git_url='https://example.test/repo.git',
                          auto_idle=True)

        result = resource.run(module, client=None)

        self.assertEqual(result['resource'], created)


class TestReadQueryNoneMode(unittest.TestCase):
    """A sentinel (never ``None``) client is used throughout so a
    hard-coded ``None`` passed to a mutation closure -- rather than the
    real client ``run()`` was given -- is caught, not masked by the
    fixture's own client happening to be ``None`` too.
    """

    def test_present_always_creates_with_changed_true(self):
        calls = []
        sentinel_client = object()
        resource = LagoonResourceModule(
            fields=_FIELDS, diff_ignore=_DIFF_IGNORE, read=None,
            create=lambda client, desired: calls.append((client, desired)))
        module = _module(git_url='https://example.test/repo.git')

        result = resource.run(module, client=sentinel_client)

        self.assertTrue(result['changed'])
        self.assertIsNone(result['diff'])
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], sentinel_client)

    def test_check_mode_present_makes_no_create_call(self):
        calls = []
        resource = LagoonResourceModule(
            fields=_FIELDS, diff_ignore=_DIFF_IGNORE, read=None,
            create=lambda client, desired: calls.append(desired))
        module = _module(check_mode=True,
                          git_url='https://example.test/repo.git')

        result = resource.run(module, client=object())

        self.assertTrue(result['changed'])
        self.assertEqual(calls, [])

    def test_absent_always_deletes_with_changed_true(self):
        calls = []
        sentinel_client = object()
        resource = LagoonResourceModule(
            fields=_FIELDS, diff_ignore=_DIFF_IGNORE, read=None,
            delete=lambda client, current: calls.append((client, current)))
        module = _module(state='absent')

        result = resource.run(module, client=sentinel_client)

        self.assertTrue(result['changed'])
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], sentinel_client)
        self.assertIsNone(calls[0][1])


class TestLookupsOverrideParams(unittest.TestCase):

    def test_resolved_lookup_value_used_in_desired_state(self):
        resource, calls = _resource_module(None)
        module = _module(git_url='https://example.test/repo.git')

        resource.run(module, client=None, lookups={'name': 'resolved-name'})

        self.assertEqual(calls['create'][0]['name'], 'resolved-name')

    def test_lookup_field_outside_fields_does_not_defeat_no_op(self):
        """environment's project_id lookup resolves to a wire field
        ('project') that is not part of environment.fields at all --
        current can never carry a value for it, so it must never be
        compared in the diff. Regression test for the bug where every
        present call against an unchanged resource with a declared
        lookup was reported as changed, forever.
        """
        current = {'id': 1, 'name': 'my-project', 'gitUrl': None,
                   'autoIdle': True}
        resource, calls = _resource_module(current)
        module = _module(auto_idle=True)

        result = resource.run(module, client=None,
                               lookups={'project': 123})

        self.assertFalse(result['changed'])
        self.assertEqual(calls['update'], [])

    def test_lookup_field_reaches_update_when_real_field_changed(self):
        """The lookup value must still reach the update closure's
        wire-shaping (it needs `project` to build the mutation payload)
        even though it is excluded from the diff comparison itself.
        """
        current = {'id': 1, 'name': 'my-project', 'gitUrl': None,
                   'autoIdle': True}
        resource, calls = _resource_module(current)
        module = _module(auto_idle=False)

        result = resource.run(module, client=None,
                               lookups={'project': 123})

        self.assertTrue(result['changed'])
        self.assertEqual(len(calls['update']), 1)
        _, desired, changed_fields = calls['update'][0]
        self.assertEqual(changed_fields, ['autoIdle'])
        self.assertEqual(desired['project'], 123)


class TestNoForbiddenImports(unittest.TestCase):

    def test_forbidden_imports_absent(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'plugins', 'module_utils', 'resource.py')
        path = os.path.normpath(path)
        tree = ast.parse(open(path).read())
        bad = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                bad += [a.name for a in n.names
                        if a.name.split('.')[0] in
                        ('ansible', 'gql', 'graphql', 'requests')]
            if isinstance(n, ast.ImportFrom) and n.module:
                if n.module.split('.')[0] in \
                        ('ansible', 'gql', 'graphql', 'requests'):
                    bad.append(n.module)
                if n.module == 'ansible.errors':
                    bad.append(n.module)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
