from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import re

_CAMEL_BOUNDARY_RE = re.compile(r'(?<!^)(?=[A-Z])')


def _camel_to_snake(name):
    """Convert a camelCase wire field name (e.g. ``gitUrl``) to the
    snake_case argspec option name Ansible convention expects
    (``git_url``). A mechanical case transform, not a lookup table --
    every declared field gets this for free.
    """
    return _CAMEL_BOUNDARY_RE.sub('_', name).lower()


class LagoonResourceModule:
    """Read-diff-mutate-check_mode engine for resource modules.

    Operates entirely in the wire field namespace -- the camelCase
    field names a flat read operation returns (``self.fields``). It
    holds no argspec-option-name mapping table (derived mechanically via
    :func:`_camel_to_snake`) and no mutation wire-shaping logic (the
    create/update asymmetry, create-only/update-only enforcement): both
    are resource-specific business logic and stay with the caller
    (module ``main()``), matching the rule that modules hold 100% of the
    business logic.

    Constructor arguments:

      fields
        Scalar wire field names participating in read/diff/report.
      diff_ignore
        Subset of ``fields`` excluded from diffing and reporting
        (server-computed fields such as ``id``).
      no_log_fields
        Subset of ``fields`` that must never appear with a real value in
        a diff. Stripped entirely from both ``before`` and ``after``;
        a top-level ``changed_no_log_fields`` list in the diff carries
        the changed/unchanged fact instead. Applies identically to the
        check-mode preview and a real run's diff.
      enum_case_normalise
        Maps a field name to ``'upper'`` or ``'lower'``. Applied to the
        read side only, before diffing and before the field is used as
        a reported ``before`` value -- the desired side already carries
        whatever case the argspec's ``choices`` enforces.
      read
        ``callable(client) -> dict | None``, or ``None``. Returns the
        resource's current wire-field state, or ``None`` if it does not
        exist. ``None`` selects a degraded mode for resources with no
        read operation: every ``present`` call unconditionally creates
        and every ``absent`` call unconditionally deletes, both with
        ``changed=True`` and no diff -- there is no current state to
        diff against, and reporting one anyway would be dishonest.
      create, update, delete
        Caller-supplied closures performing the actual mutation call
        (document construction, wire-shaping, ``client.execute``).
        Never called under ``check_mode``. ``update`` receives
        ``client``, ``current``, ``desired`` and ``changed_fields`` --
        the last is the list of wire field names the diff found
        different, so the caller's wire-shaping only has to send what
        actually changed. Their return value is ignored: state after a
        real mutation comes from re-reading via ``read``, never from the
        mutation response or from ``desired`` -- the server may default
        or normalise fields the caller didn't set explicitly. In
        ``read=None`` mode there is nothing to read, so ``delete``
        receives ``current=None`` rather than a real current state.

    ``run()`` returns a dict with keys ``changed`` (bool), ``diff``
    (dict or ``None``) and ``resource`` (dict or ``None``).
    ``resource`` is the resource's field dict, or ``None`` after a
    delete -- the caller places it under whatever key its own
    ``exit_json()`` uses (e.g. ``project=``), since this class has no
    resource-specific name to give it.
    """

    def __init__(self, fields, diff_ignore=(), no_log_fields=(),
                 enum_case_normalise=None, read=None, create=None,
                 update=None, delete=None):
        self.fields = tuple(fields)
        self.diff_ignore = frozenset(diff_ignore)
        self.no_log_fields = frozenset(no_log_fields)
        self.enum_case_normalise = dict(enum_case_normalise or {})
        self.read = read
        self.create = create
        self.update = update
        self.delete = delete

    # -- Public surface ---------------------------------------------------

    def run(self, module, client, lookups=None):
        """Execute the full read/diff/mutate flow for one module
        invocation.

        ``lookups`` is a dict of already-resolved lookup values, keyed
        by wire field name (e.g. ``{'project': 42}``) -- this class
        never calls lookup resolution itself; the caller resolves
        aliases (project name -> id) before calling ``run()`` and passes
        the resolved field value here, so this class needs no knowledge
        of the allowlist's lookup names or alias params. Lookup values
        override any same-named value derived from ``module.params``.
        """
        desired = self._desired_from_params(module.params)
        if lookups:
            desired.update(lookups)
        desired = {field: value for field, value in desired.items()
                   if field not in self.diff_ignore}

        state = module.params['state']

        if self.read is None:
            return self._run_without_read(module, client, state, desired)

        current = self._normalise_current(self.read(client))

        if state == 'present':
            if current is None:
                return self._do_create(module, client, desired)
            changed_fields = self._diff_keys(current, desired)
            if not changed_fields:
                return self._result(False, None, current)
            return self._do_update(
                module, client, current, desired, changed_fields)

        if current is None:
            return self._result(False, None, None)
        return self._do_delete(module, client, current)

    # -- State transitions -----------------------------------------------

    def _do_create(self, module, client, desired):
        after_preview = self._filtered(desired)
        diff = self._report_diff(None, after_preview)
        if module.check_mode:
            return self._result(True, diff, dict(desired))

        self.create(client, desired)
        fresh = self._normalise_current(self.read(client))
        after = self._filtered(fresh) if fresh is not None else after_preview
        diff = self._report_diff(None, after)
        return self._result(True, diff, fresh)

    def _do_update(self, module, client, current, desired, changed_fields):
        before = self._filtered(current)
        after_preview = dict(before)
        after_preview.update(self._filtered(desired))
        diff = self._report_diff(before, after_preview)
        if module.check_mode:
            return self._result(True, diff, current)

        self.update(client, current, desired, changed_fields)
        fresh = self._normalise_current(self.read(client))
        after = self._filtered(fresh) if fresh is not None else after_preview
        diff = self._report_diff(before, after)
        return self._result(True, diff, fresh)

    def _do_delete(self, module, client, current):
        before = self._filtered(current)
        diff = self._report_diff(before, None)
        if module.check_mode:
            return self._result(True, diff, None)

        self.delete(client, current)
        return self._result(True, diff, None)

    def _run_without_read(self, module, client, state, desired):
        if state == 'present':
            if not module.check_mode:
                self.create(client, desired)
            return self._result(True, None, dict(desired))

        if not module.check_mode:
            self.delete(client, None)
        return self._result(True, None, None)

    # -- Field-level helpers ---------------------------------------------

    def _desired_from_params(self, params):
        desired = {}
        for field in self.fields:
            if field in self.diff_ignore:
                continue
            key = _camel_to_snake(field)
            if key not in params:
                continue
            value = params[key]
            if value is None:
                continue
            desired[field] = value
        return desired

    def _normalise_current(self, current):
        if not current:
            return current
        normalised = dict(current)
        for field, direction in self.enum_case_normalise.items():
            value = normalised.get(field)
            if value is None:
                continue
            normalised[field] = (
                value.upper() if direction == 'upper' else value.lower())
        return normalised

    def _diff_keys(self, current, desired):
        # Restricted to self.fields: `desired` may also carry resolved
        # lookup values (e.g. environment's project_id lookup) that
        # have no counterpart in the read query's own field set at all
        # -- `current` can never carry a value for them, so comparing
        # them here would report every present call against an
        # already-up-to-date resource as changed, forever.
        return [field for field, value in desired.items()
                if field in self.fields and current.get(field) != value]

    def _filtered(self, data):
        if data is None:
            return None
        return {field: data[field] for field in self.fields
                if field not in self.diff_ignore and field in data}

    def _report_diff(self, before_full, after_full):
        before_map = before_full or {}
        after_map = after_full or {}
        changed_no_log = sorted(
            field for field in self.no_log_fields
            if before_map.get(field) != after_map.get(field))

        diff = {
            'before': self._strip_no_log(before_full),
            'after': self._strip_no_log(after_full),
        }
        if changed_no_log:
            diff['changed_no_log_fields'] = changed_no_log
        return diff

    def _strip_no_log(self, data):
        if data is None:
            return None
        return {field: value for field, value in data.items()
                if field not in self.no_log_fields}

    def _result(self, changed, diff, resource):
        return {'changed': changed, 'diff': diff, 'resource': resource}
