from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from .client import LagoonClient
from .errors import (
    LagoonAmbiguousResultError,
    LagoonConfigError,
    LagoonNotFoundError,
)

_DEFAULT_ARG_TYPE = 'String!'


def resolve_lookup(client, lookup_config, value, cache=None):
    """Resolve one declared lookup to a concrete id.

    ``lookup_config`` is one entry from the allowlist's ``lookups:`` map,
    a dict with keys ``query`` (e.g. ``projectByName``), ``arg`` (e.g.
    ``name``) and ``returns`` (e.g. ``id``). An optional ``arg_type`` key
    gives the GraphQL type of the lookup's argument for
    :meth:`.client.LagoonClient.build_query` (defaults to ``'String!'``,
    which covers every lookup the real allowlist declares today -- all
    take a name/namespace string). An optional ``resource`` key names the
    resource for error messages; defaults to the lookup's ``query`` value
    when absent.

    ``client`` is a constructed :class:`.client.LagoonClient`. ``value``
    is the alias-param value supplied by the caller (e.g. the project
    name), sent only as a GraphQL variable -- it never appears in the
    query document itself.

    ``cache`` is a plain dict the caller owns and passes in -- this
    function never constructs its own cache, so its lifetime is entirely
    the caller's decision (module-level for the in-memory case, matching
    the token cache's own scoping in ``auth.py``). Cache key is exactly
    ``(lookup_config['query'], lookup_config['arg'], value)``. ``cache=
    None`` disables caching outright.

    The declared lookup query is expected to resolve to a single
    nullable object (e.g. ``projectByName(name: $name): Project``), not
    a list. Three failure shapes are distinguished:

      - The query resolves to no result (``null``) -- raises
        :class:`.errors.LagoonNotFoundError`.
      - The query resolves to a list (a lookup config pointed at a
        list-returning query by mistake) -- raises
        :class:`.errors.LagoonAmbiguousResultError`.
      - The resolved object's ``returns`` field is itself a list or
        object rather than a scalar (a lookup config whose ``returns``
        points at the wrong field) -- raises
        :class:`.errors.LagoonConfigError`, since this is a caller
        configuration defect rather than an ambiguous or missing result.
        Caught here, on first use, rather than discovered later as a
        confusing type error somewhere downstream.

    Never falls through to a null id: every failure shape above raises.
    """
    query = lookup_config['query']
    arg = lookup_config['arg']
    returns = lookup_config['returns']
    arg_type = lookup_config.get('arg_type', _DEFAULT_ARG_TYPE)
    resource = lookup_config.get('resource', query)

    key = (query, arg, value)
    if cache is not None and key in cache:
        return cache[key]

    document = LagoonClient.build_query(
        query, fields=[returns], args={arg: arg_type})
    data = client.execute(document, variables={arg: value})

    result = data.get(query)

    if isinstance(result, list):
        raise LagoonAmbiguousResultError(
            resource, query=query, arg=arg, value=value, count=len(result))

    if result is None:
        raise LagoonNotFoundError(resource, query=query, arg=arg,
                                   value=value)

    resolved = result.get(returns) if isinstance(result, dict) else None

    if isinstance(resolved, (list, dict)):
        raise LagoonConfigError(
            "lookup %r: 'returns' field %r resolves to a non-scalar "
            "value -- a lookup's 'returns' must name a scalar field" %
            (query, returns))

    if resolved is None:
        raise LagoonNotFoundError(resource, query=query, arg=arg,
                                   value=value)

    if cache is not None:
        cache[key] = resolved

    return resolved


def invalidate_lookup(cache, lookup_config, value):
    """Remove one cache entry.

    Called after any successful create/delete affecting that resource
    type, and unconditionally when ``state=absent`` (the resource may
    have just been deleted). A no-op if ``cache`` is ``None`` or the
    entry is absent -- invalidating something that was never cached is
    not an error.
    """
    if cache is None:
        return
    query = lookup_config['query']
    arg = lookup_config['arg']
    cache.pop((query, arg, value), None)
