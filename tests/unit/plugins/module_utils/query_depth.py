"""Flat-query nesting-depth guardrail.

Enforces the REST-semantics rule (docs/plans/v3-refactor.md 7.1): every
GraphQL document in the collection must be a *flat*, single-level query --
one operation selection set, and at most one level of field selection below
it. No field's selection set may itself contain a nested selection set.

This module is a **test-time helper**, not runtime code. It lives under
``tests/`` rather than ``plugins/`` deliberately and must not be
imported from anything under ``plugins/``.

It imports :class:`.module_utils.client.LagoonClient` to reconstruct
``build_query(...)`` call sites (see :func:`collect_candidate_documents`)
by calling the real implementation rather than re-deriving its
string-building logic here, which could drift from it. This is safe:
``client.py`` has no ``AnsibleModule`` dependency of its own, so this
stays a plain function call, never an ``import`` of an actual *module*
file under ``plugins/modules/`` (those require a constructed
``AnsibleModule`` to run at all).

Depth is computed with a small character scanner rather than a regex --
brace-nesting depth is not a regular language, and the scanner must be
aware of string literals (including GraphQL block strings) and ``#``
comments so that braces appearing inside them are not mistaken for
selection-set boundaries.

Depth definition, precisely::

    query ($name: String!) { projectByName(name: $name) { id name } }
                             ^ depth 1                    ^ depth 2

- depth 1 = the operation's own selection set
- depth 2 = a field's selection set

The maximum permitted depth is **2**. A document with no selection set at
all (e.g. a mutation returning a bare scalar) has max depth 1 and is valid.
Anything reaching depth 3 or deeper is a violation.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ast
import os
import re

from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils \
    .client import LagoonClient
from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils \
    .errors import LagoonConfigError

#: Matches a name assigned a GraphQL document, e.g. ``PROJECT_QUERY``,
#: ``ADD_PROJECT_MUTATION``, ``SOME_GQL``, ``FOO_DOCUMENT``.
_NAME_RE = re.compile(r'(?i)(QUERY|MUTATION|_GQL|DOCUMENT)')

#: Matches a string literal that looks like it *contains* a GraphQL
#: operation -- used to catch documents that are not conveniently named,
#: e.g. inline literals passed straight to ``client.execute(...)``.
_OPERATION_LITERAL_RE = re.compile(r'(query[\s(]|mutation[\s(])')

#: Ansible ``DOCUMENTATION``/``EXAMPLES``/``RETURN`` module-level string
#: constants are YAML prose, never GraphQL documents, even though their
#: names and content can incidentally match ``_NAME_RE`` (``RETURN``
#: contains no match, but ``DOCUMENTATION`` does) or
#: ``_OPERATION_LITERAL_RE`` (prose mentioning "the flat-query rule" or
#: similar contains "query " next to a brace). Both rules must skip
#: these constants and every string literal nested inside them, or the
#: sweep finds "documents" that were never GraphQL at all -- which
#: defeats the vacuous-pass guard: it would keep finding *something*
#: even with no GraphQL-producing code in the tree.
_DOC_CONSTANTS = frozenset({'DOCUMENTATION', 'EXAMPLES', 'RETURN'})

#: Placeholder recorded for a ``build_query(...)`` call site whose
#: arguments could not be fully statically resolved (e.g. ``fields``
#: built dynamically at runtime). It still counts toward the
#: vacuous-pass guard, but carries no document for
#: :func:`assert_flat_query` to check -- callers must skip the depth
#: assertion for this marker rather than pass it through as a document.
UNRESOLVED_BUILD_QUERY = '<build_query: unresolved arguments>'

#: Placeholder recorded for a ``build_query(...)`` call site whose
#: arguments resolve statically but that the real
#: :meth:`LagoonClient.build_query` itself rejects (e.g. an invalid
#: operation name) -- a call site guaranteed to fail at runtime. Unlike
#: :data:`UNRESOLVED_BUILD_QUERY`, this is not a "not checked" state:
#: callers must treat it as an unconditional violation.
INVALID_BUILD_QUERY = '<build_query: invalid arguments>'

#: Placeholder recorded for a call site named ``build_query`` that the
#: sweep cannot prove resolves to the real
#: :meth:`LagoonClient.build_query` -- a locally defined/assigned
#: ``build_query`` that shadows the real one, or an import from
#: somewhere other than ``module_utils.client``. Reconstructing such a
#: call site by invoking the real implementation would silently check
#: the wrong function's output. Callers must treat this as an
#: unconditional violation: a shadowed ``build_query`` inside
#: ``plugins/`` is itself a defect worth failing the sweep over.
SHADOWED_BUILD_QUERY = '<build_query: shadowed, not the real implementation>'


class QueryDepthError(ValueError):
    """Raised when a document has unbalanced braces or an unterminated
    string/comment -- i.e. the scanner cannot compute a depth at all."""


#: The REST-semantics rule permits at most one level of field selection
#: below the operation's own selection set.
MAX_PERMITTED_DEPTH = 2


def max_selection_depth(document):
    """Return the maximum GraphQL selection-set nesting depth in
    ``document``.

    A character scanner, not a regex: tracks brace depth while skipping
    over string literals (``"..."`` and block strings ``\"\"\"...\"\"\"``,
    including ``\\"`` escapes) and ``#`` comments to end of line, so that
    braces appearing inside either are never mistaken for selection-set
    boundaries.

    Raises :class:`QueryDepthError` (a :class:`ValueError`) if the braces
    are unbalanced, or if a string literal or block string is left
    unterminated -- both indicate a malformed document worth surfacing,
    not something to silently score as depth 0.
    """
    depth = 0
    max_depth = 0
    i = 0
    n = len(document)

    while i < n:
        ch = document[i]

        if ch == '#':
            newline = document.find('\n', i)
            i = n if newline == -1 else newline + 1
            continue

        if ch == '"':
            if document[i:i + 3] == '"""':
                end = document.find('"""', i + 3)
                if end == -1:
                    raise QueryDepthError(
                        "unterminated block string (triple-quote) "
                        "starting at position %d" % i)
                i = end + 3
                continue
            j = i + 1
            closed = False
            while j < n:
                if document[j] == '\\':
                    j += 2
                    continue
                if document[j] == '"':
                    closed = True
                    j += 1
                    break
                j += 1
            if not closed:
                raise QueryDepthError(
                    "unterminated string literal starting at position %d"
                    % i)
            i = j
            continue

        if ch == '{':
            depth += 1
            if depth > max_depth:
                max_depth = depth
            i += 1
            continue

        if ch == '}':
            depth -= 1
            if depth < 0:
                raise QueryDepthError(
                    "unbalanced braces: unexpected '}' at position %d" % i)
            i += 1
            continue

        i += 1

    if depth != 0:
        raise QueryDepthError(
            "unbalanced braces: %d unclosed '{' remaining" % depth)

    return max_depth


def assert_flat_query(document, source=None):
    """Raise :class:`AssertionError` if ``document`` nests deeper than
    :data:`MAX_PERMITTED_DEPTH`.

    ``source`` -- typically ``"<path>:<name-or-lineno>"`` -- is included in
    the failure output so a sweep failure names the offending file and
    symbol, not just the document text.
    """
    depth = max_selection_depth(document)
    if depth > MAX_PERMITTED_DEPTH:
        where = " in %s" % source if source else ""
        raise AssertionError(
            "GraphQL document%s exceeds max selection depth of %d "
            "(found depth %d) -- nested selection sets are forbidden, see "
            "docs/plans/v3-refactor.md 7.1:\n%s"
            % (where, MAX_PERMITTED_DEPTH, depth, document))


def _iter_python_files(root_dir):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for filename in sorted(filenames):
            if filename.endswith('.py'):
                yield os.path.join(dirpath, filename)


def _module_and_class_level_assigns(tree):
    """Yield ``(name, value, lineno)`` for every string-constant assignment
    to a plain name that appears directly in a module body or a class
    body -- deliberately *not* inside a function/method body, since a
    GraphQL document is always built and named at that scope, never
    inside a function.
    """
    results = []

    def _scan_body(body):
        for stmt in body:
            if isinstance(stmt, ast.Assign):
                value = stmt.value
                if isinstance(value, ast.Constant) and \
                        isinstance(value.value, str):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            results.append(
                                (target.id, value.value, stmt.lineno))
            if isinstance(stmt, ast.ClassDef):
                _scan_body(stmt.body)

    _scan_body(tree.body)
    return results


def _literal_from_ast(node):
    """Return the plain Python value ``node`` represents if -- and only
    if -- it is fully built from :class:`ast.Constant` leaves (nested
    inside, at most, ``ast.List``/``ast.Tuple``/``ast.Dict``).

    Raises :class:`ValueError` for anything else (a name reference, a
    function call, a comprehension, an f-string, ...) so the caller can
    treat the containing ``build_query(...)`` invocation as not fully
    statically resolvable, rather than silently resolving to a wrong or
    partial value.
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_literal_from_ast(elt) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_literal_from_ast(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        if any(k is None for k in node.keys):
            # A ``**spread`` entry -- not a literal key/value pair.
            raise ValueError("dict contains a non-literal spread entry")
        return {
            _literal_from_ast(k): _literal_from_ast(v)
            for k, v in zip(node.keys, node.values)
        }
    raise ValueError("not a statically resolvable literal: %r" % (node,))


def _is_build_query_call(node):
    """True if ``node`` is a call to something named ``build_query`` --
    either the attribute form (``<expr>.build_query(...)``) or the bare
    form (``build_query(...)``).

    This only tests the *name* -- it says nothing about whether the
    callee is actually :meth:`LagoonClient.build_query`. Use
    :func:`_call_is_trusted_build_query` to decide whether reconstructing
    the call by invoking the real implementation is safe; a call site
    can match this function and still turn out to be shadowed.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == 'build_query'
    if isinstance(func, ast.Name):
        return func.id == 'build_query'
    return False


def _names_bound_to_lagoon_client(tree):
    """Return the set of local names bound, anywhere in ``tree``, to the
    real ``LagoonClient`` class via
    ``from ...module_utils.client import LagoonClient [as X]``.

    Only this specific import shape is trusted -- a name that merely
    *looks* like it holds ``LagoonClient`` (e.g. reassigned later, or
    imported from somewhere else entirely) is not, and any
    ``build_query`` reached through it must be treated as shadowed
    rather than reconstructed via the real implementation.
    """
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and \
                node.module.endswith('module_utils.client'):
            for alias in node.names:
                if alias.name == 'LagoonClient':
                    names.add(alias.asname or alias.name)
    return names


def _names_bound_to_build_query(tree, trusted_client_names):
    """Return the set of local names bound, anywhere in ``tree``, to the
    real ``LagoonClient.build_query`` via a plain alias assignment
    (``build_query = LagoonClient.build_query``, where ``LagoonClient``
    is itself one of ``trusted_client_names``).

    Any other name called as ``build_query(...)`` -- a local ``def``, a
    ``lambda``, a class, or an import from anywhere else -- is not
    trusted, and the bare-form call site must be recorded as shadowed
    rather than reconstructed via the real implementation.
    """
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if isinstance(value, ast.Attribute) and value.attr == 'build_query' \
                and isinstance(value.value, ast.Name) \
                and value.value.id in trusted_client_names:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _call_is_trusted_build_query(node, trusted_client_names,
                                  trusted_bare_names):
    """True if ``node`` -- already known to be named ``build_query`` by
    :func:`_is_build_query_call` -- provably resolves to the real
    :meth:`LagoonClient.build_query`, and can therefore be safely
    reconstructed by invoking that real implementation.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        return isinstance(func.value, ast.Name) and \
            func.value.id in trusted_client_names
    if isinstance(func, ast.Name):
        return func.id in trusted_bare_names
    return False


def _resolve_build_query_args(node):
    """Resolve ``node`` (a call to ``build_query``) to the
    ``(operation, kwargs)`` pair :meth:`LagoonClient.build_query` would
    receive at runtime.

    Raises :class:`ValueError` if any argument is not fully statically
    resolvable (dynamic ``fields``, a variable, a comprehension, a
    ``*args``/``**kwargs`` spread, ...) or if the call shape omits a
    required argument -- callers must record such a call site as
    unresolved rather than dropping it, so it still counts toward the
    vacuous-pass guard while making the "not checked" state visible
    rather than silent.
    """
    if any(isinstance(a, ast.Starred) for a in node.args):
        raise ValueError("*args spread is not statically resolvable")

    kwargs = {}
    for keyword in node.keywords:
        if keyword.arg is None:
            raise ValueError("**kwargs spread is not statically resolvable")
        kwargs[keyword.arg] = _literal_from_ast(keyword.value)

    positional = [_literal_from_ast(arg) for arg in node.args]

    if positional:
        if 'operation' in kwargs:
            raise ValueError("operation given both positionally and "
                              "by keyword")
        operation = positional[0]
        positional = positional[1:]
    else:
        operation = kwargs.pop('operation', None)

    if operation is None or positional:
        # No operation resolved, or unexpected extra positional args --
        # not a call shape build_query() actually accepts.
        raise ValueError("no resolvable operation, or unexpected extra "
                          "positional arguments")

    if 'fields' not in kwargs:
        # fields is a required keyword-only argument on the real
        # signature; a call site omitting it cannot be reconstructed by
        # calling build_query() (it would raise TypeError), so treat it
        # as unresolved rather than letting that exception escape the
        # sweep.
        raise ValueError("fields is required and was not supplied")

    return operation, kwargs


def _reconstruct_build_query_call(node):
    """Reconstruct the GraphQL document a trusted ``build_query(...)``
    call site would produce at runtime.

    Returns one of: the reconstructed document string; or
    :data:`UNRESOLVED_BUILD_QUERY` if the arguments are not fully
    statically resolvable; or :data:`INVALID_BUILD_QUERY` if the
    arguments resolve but the real :meth:`LagoonClient.build_query`
    itself rejects them (e.g. an invalid operation name) -- a call site
    guaranteed to fail at runtime, and therefore an unconditional
    violation, not merely "not checked".
    """
    try:
        operation, kwargs = _resolve_build_query_args(node)
    except ValueError:
        return UNRESOLVED_BUILD_QUERY

    try:
        return LagoonClient.build_query(operation, **kwargs)
    except (LagoonConfigError, TypeError):
        return INVALID_BUILD_QUERY


def _build_query_call_sites(tree, path):
    """Yield ``(source_label, document)`` for every call site named
    ``build_query`` in ``tree``.

    A call that provably resolves to the real
    :meth:`LagoonClient.build_query` (see
    :func:`_call_is_trusted_build_query`) is reconstructed via
    :func:`_reconstruct_build_query_call`, which may itself yield
    :data:`UNRESOLVED_BUILD_QUERY` or :data:`INVALID_BUILD_QUERY` in
    place of a document.

    A call that is *not* provably the real implementation -- a locally
    defined/assigned ``build_query`` that shadows it, or an import from
    anywhere else -- is yielded as :data:`SHADOWED_BUILD_QUERY` without
    ever being reconstructed: doing so would silently check a document
    the shadowing code will never actually produce.
    """
    trusted_client_names = _names_bound_to_lagoon_client(tree)
    trusted_bare_names = _names_bound_to_build_query(
        tree, trusted_client_names)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_build_query_call(node):
            continue
        lineno = getattr(node, 'lineno', '?')
        label = '%s:%s' % (path, lineno)
        if not _call_is_trusted_build_query(
                node, trusted_client_names, trusted_bare_names):
            yield (label, SHADOWED_BUILD_QUERY)
        else:
            yield (label, _reconstruct_build_query_call(node))


def _doc_constant_value_node_ids(tree):
    """Return the set of ``id()`` for every AST node nested inside the
    value of a module-level ``DOCUMENTATION``/``EXAMPLES``/``RETURN``
    assignment (see :data:`_DOC_CONSTANTS`), so rule 2 below can skip
    every string literal that lives inside one of these YAML doc blocks,
    not just the top-level constant itself.
    """
    ids = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in _DOC_CONSTANTS:
                for sub in ast.walk(node.value):
                    ids.add(id(sub))
    return ids


def collect_candidate_documents(root_dir):
    """Walk every ``.py`` file under ``root_dir`` via :mod:`ast` (never
    ``import``, which would pull in ``AnsibleModule`` and fail under bare
    pytest) and return a list of ``(source_label, document)`` pairs for
    every string that looks like it might be a GraphQL document:

    1. Every module-level or class-level string constant assigned to a
       name matching ``(?i)(QUERY|MUTATION|_GQL|DOCUMENT)``, excluding
       :data:`_DOC_CONSTANTS`.
    2. Every string literal anywhere in the file that contains both ``{``
       and one of ``query ``/``mutation ``/``query(``/``mutation(``,
       excluding any literal nested inside a :data:`_DOC_CONSTANTS`
       assignment.
    3. Every call site named ``build_query`` (attribute form
       ``LagoonClient.build_query(...)``, or bare ``build_query(...)``
       via a plain alias). One that provably resolves to the real
       :meth:`LagoonClient.build_query` is reconstructed by calling that
       real implementation with its statically-resolved arguments, and
       may itself be paired with a placeholder instead of a document:
       :data:`UNRESOLVED_BUILD_QUERY` (arguments not fully resolvable --
       skip the depth assertion for this entry) or
       :data:`INVALID_BUILD_QUERY` (arguments resolve, but the real
       implementation rejects them -- an unconditional violation). A
       call that cannot be proven to reach the real implementation at
       all -- a shadowing local ``build_query`` -- is paired with
       :data:`SHADOWED_BUILD_QUERY` instead of being reconstructed, and
       is likewise an unconditional violation.

    Rule 1 and rule 2 deliberately exclude
    ``DOCUMENTATION``/``EXAMPLES``/``RETURN``: these are YAML prose, not
    GraphQL, even though their names and content can incidentally match
    either rule's pattern.

    The remaining sets overlap by design (a named constant that also
    matches the literal pattern is reported once for each reason) -- the
    goal is coverage, not a single canonical classification.
    """
    candidates = []
    for path in sorted(_iter_python_files(root_dir)):
        try:
            source_text = open(path, encoding='utf-8').read()
        except (IOError, OSError):
            continue
        try:
            tree = ast.parse(source_text, filename=path)
        except SyntaxError:
            continue

        for name, value, lineno in _module_and_class_level_assigns(tree):
            if name in _DOC_CONSTANTS:
                continue
            if _NAME_RE.search(name):
                candidates.append(('%s:%s' % (path, name), value))

        doc_node_ids = _doc_constant_value_node_ids(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in doc_node_ids:
                text = node.value
                if '{' in text and _OPERATION_LITERAL_RE.search(text):
                    lineno = getattr(node, 'lineno', '?')
                    candidates.append(('%s:%s' % (path, lineno), text))

        candidates.extend(_build_query_call_sites(tree, path))

    return candidates
