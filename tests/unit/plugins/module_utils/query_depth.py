"""Flat-query nesting-depth guardrail.

Enforces the REST-semantics rule (docs/plans/v3-refactor.md 7.1): every
GraphQL document in the collection must be a *flat*, single-level query --
one operation selection set, and at most one level of field selection below
it. No field's selection set may itself contain a nested selection set.

This module is a **test-time helper**, not runtime code. It lives under
``tests/`` rather than ``plugins/`` deliberately (see
``docs/plans/v3-phase1-stories.md`` P1-S5) and must not be imported from
anything under ``plugins/``.

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


#: Matches a name assigned a GraphQL document, e.g. ``PROJECT_QUERY``,
#: ``ADD_PROJECT_MUTATION``, ``SOME_GQL``, ``FOO_DOCUMENT``.
_NAME_RE = re.compile(r'(?i)(QUERY|MUTATION|_GQL|DOCUMENT)')

#: Matches a string literal that looks like it *contains* a GraphQL
#: operation -- used to catch documents that are not conveniently named,
#: e.g. inline literals passed straight to ``client.execute(...)``.
_OPERATION_LITERAL_RE = re.compile(r'(query[\s(]|mutation[\s(])')


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
    body -- deliberately *not* inside a function/method body, per the
    "module-level or class-level" scope in the story spec.
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


def collect_candidate_documents(root_dir):
    """Walk every ``.py`` file under ``root_dir`` via :mod:`ast` (never
    ``import``, which would pull in ``AnsibleModule`` and fail under bare
    pytest) and return a list of ``(source_label, document)`` pairs for
    every string that looks like it might be a GraphQL document:

    1. Every module-level or class-level string constant assigned to a
       name matching ``(?i)(QUERY|MUTATION|_GQL|DOCUMENT)``.
    2. Every string literal anywhere in the file that contains both ``{``
       and one of ``query ``/``mutation ``/``query(``/``mutation(``.

    The two sets overlap by design (a named constant that also matches the
    literal pattern is reported once for each reason) -- the goal is
    coverage, not a single canonical classification.
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
            if _NAME_RE.search(name):
                candidates.append(('%s:%s' % (path, name), value))

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
                if '{' in text and _OPERATION_LITERAL_RE.search(text):
                    lineno = getattr(node, 'lineno', '?')
                    candidates.append(('%s:%s' % (path, lineno), text))

    return candidates
