"""Field specs: the caller-controlled selection sets the client sends.

A field spec is a list of scalar field names and single-key dicts mapping a
field name to a nested spec:

    ["id", "name", {"kubernetes": ["id", "name"]}]
    -> "id name kubernetes { id name }"

Nesting is unbounded. Values never appear in a spec - only field names - so
rendering a spec cannot inject a caller-supplied value into a document.
"""

import re
from collections.abc import Sequence
from typing import Any, Optional, Union

FieldSpec = list[Union[str, dict[str, Any]]]

# A GraphQL name. Field names are interpolated into the document (unavoidable
# in a selection set), so anything that is not a plain name is rejected rather
# than passed through.
FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

PROJECT_FIELDS = [
    "autoIdle",
    "availability",
    "branches",
    "created",
    "deploymentsDisabled",
    "developmentBuildPriority",
    "developmentEnvironmentsLimit",
    "gitUrl",
    "id",
    "metadata",
    "name",
    "openshiftProjectName",
    "openshiftProjectPattern",
    "productionAlias",
    "productionBuildPriority",
    "productionEnvironment",
    "productionRoutes",
    "pullrequests",
    "routerPattern",
    "standbyAlias",
    "standbyProductionEnvironment",
    "standbyRoutes",
]

# metadata is the one unbounded-size field on Project (a JSON scalar), so it is
# fetched on its own request and merged back in. Splitting it keeps the main
# project request predictable without changing the resulting project dict.
PROJECT_FIELDS_NO_METADATA = [f for f in PROJECT_FIELDS if f != "metadata"]

# Deliberately narrow. Widening the selection on a query that spans every
# project on the estate slows the request down and past a point fails it;
# enumerating names is the only job a list query has. Callers wanting more pass
# it explicitly at the call site and own the cost.
PROJECT_LIST_FIELDS = ["name"]

VARIABLES_FIELDS = [
    "id",
    "name",
    "value",
    "scope",
]

CLUSTER_FIELDS = [
    "id",
    "name",
]

ENVIRONMENTS_FIELDS = [
    "autoIdle",
    "created",
    "environmentType",
    "id",
    "kubernetesNamespaceName",
    "name",
    "route",
    "routes",
    "updated",
]

DEPLOYMENTS_FIELDS = [
    "bulkId",
    "bulkName",
    "completed",
    "created",
    "id",
    "name",
    "started",
    "status",
    "uiLink",
]

# GroupInterface declares id, name and type on the interface itself, so this
# needs no inline fragments.
GROUPS_FIELDS = [
    "id",
    "name",
    "type",
]


def check_name(name: str) -> str:
    """Return name if it is a usable GraphQL name, else raise ValueError."""
    if not isinstance(name, str) or not FIELD_NAME.match(name):
        raise ValueError(f"Not a valid GraphQL field name: {name!r}")
    return name


def render_fields(spec: Sequence[Any]) -> str:
    """Render a field spec to a GraphQL selection set body.

    Cannot express arguments on a nested field - `deployments(limit: 1) { .. }`
    has no representation here, and the format should not be extended to give it
    one. A method needing that writes its own document and passes it to
    LagoonClient.execute(), which still supplies variables, error handling,
    check mode and redaction.
    """

    if not spec:
        raise ValueError("Cannot render an empty field spec")

    parts = []
    for entry in spec:
        if isinstance(entry, str):
            parts.append(check_name(entry))
        elif isinstance(entry, dict):
            for name, sub in entry.items():
                parts.append(f"{check_name(name)} {{ {render_fields(sub)} }}")
        else:
            raise TypeError(
                f"Field spec entries must be a str or a dict, got {type(entry).__name__}"
            )

    return " ".join(parts)


def _index(spec: Sequence[Any]) -> dict[str, Optional[list]]:
    """Ordered name -> sub-spec map for a spec. None marks a scalar field."""

    indexed: dict[str, Optional[list]] = {}
    for entry in spec:
        if isinstance(entry, str):
            indexed.setdefault(check_name(entry), None)
        elif isinstance(entry, dict):
            for name, sub in entry.items():
                existing = indexed.get(check_name(name))
                # A name selected both as a scalar and with a sub-selection
                # resolves to the sub-selection; the scalar form carries no
                # information the nested form lacks.
                indexed[name] = merge_fields(existing, sub) if existing else list(sub)
        else:
            raise TypeError(
                f"Field spec entries must be a str or a dict, got {type(entry).__name__}"
            )
    return indexed


def merge_fields(base: Sequence[Any], extra: Sequence[Any]) -> FieldSpec:
    """Union of two field specs, nested selections merged recursively.

    Recursion matters: merging {"kubernetes": ["consoleUrl"]} into a base
    selecting kubernetes { id name } must yield kubernetes { id name consoleUrl }
    and not replace the subtree, or adding one nested field silently drops the
    defaults around it.
    """

    merged = _index(base)
    for name, sub in _index(extra).items():
        if name not in merged or merged[name] is None:
            merged[name] = sub
        elif sub is not None:
            merged[name] = merge_fields(merged[name], sub)

    return [name if sub is None else {name: sub} for name, sub in merged.items()]


def resolve_fields(
    default: Sequence[Any],
    fields: Optional[Sequence[Any]] = None,
    extra_fields: Optional[Sequence[Any]] = None,
) -> FieldSpec:
    """Apply the fields/extra_fields convention of the typed client methods.

    fields replaces the default; extra_fields adds to it. Supplying both raises,
    rather than resolving a precedence silently - a caller passing both has
    almost certainly misunderstood which one they want.
    """

    if fields and extra_fields:
        raise ValueError(
            "Pass either fields (to replace the defaults) or extra_fields "
            "(to add to them), not both"
        )

    if fields:
        return list(fields)
    if extra_fields:
        return merge_fields(default, extra_fields)
    return list(default)
