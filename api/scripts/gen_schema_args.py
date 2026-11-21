#!/usr/bin/env python3
"""Regenerate module_utils/schema_args.py from the committed schema.

A development tool - not shipped at runtime, and not importable by any plugin.
The argument type names the client needs for its variable declarations are
baked into a committed constant precisely so that no schema fetch happens on
the request path.

    python api/scripts/gen_schema_args.py

Requires graphql-core, which arrives with gql in the test requirements. Run it
after refreshing api/tests/common/schema.graphql; test_schema_args.py fails if
the two drift apart.
"""

import sys
from pathlib import Path

from graphql import build_ast_schema, parse, print_ast

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "api" / "tests" / "common" / "schema.graphql"
TARGET = REPO_ROOT / "api" / "plugins" / "module_utils" / "schema_args.py"

HEADER = '''"""Argument type names for Lagoon Query and Mutation fields.

GENERATED FILE - do not edit by hand. Regenerate with:

    python api/scripts/gen_schema_args.py

Maps a root field name to {{argument name: GraphQL type}}, which is all the
schema knowledge the client needs to declare its variables. Committed rather
than introspected so no schema fetch happens before the first useful request.

Source: api/tests/common/schema.graphql ({query_count} Query fields,
{mutation_count} Mutation fields).
"""

'''


def arg_types(schema, type_name):
    root = schema.get_type(type_name)
    if root is None:
        raise SystemExit(f"Schema has no {type_name} type")

    return {
        field_name: {
            arg_name: print_ast(arg.ast_node.type)
            for arg_name, arg in field.args.items()
        }
        for field_name, field in sorted(root.fields.items())
        if field.args
    }


def render(name, mapping):
    lines = [f"{name} = {{"]
    for field_name, args in mapping.items():
        rendered = ", ".join(f'"{a}": "{t}"' for a, t in args.items())
        lines.append(f'    "{field_name}": {{{rendered}}},')
    lines.append("}")
    return "\n".join(lines)


def main():
    if not SCHEMA.is_file():
        raise SystemExit(f"Schema not found: {SCHEMA}")

    schema = build_ast_schema(parse(SCHEMA.read_text()))
    queries = arg_types(schema, "Query")
    mutations = arg_types(schema, "Mutation")

    body = HEADER.format(query_count=len(queries), mutation_count=len(mutations))
    body += render("QUERY_ARG_TYPES", queries)
    body += "\n\n"
    body += render("MUTATION_ARG_TYPES", mutations)
    body += "\n"

    TARGET.write_text(body)
    print(
        f"Wrote {TARGET.relative_to(REPO_ROOT)}: "
        f"{len(queries)} queries, {len(mutations)} mutations.",
        file=sys.stderr,
    )
    print("Run `ruff format` on the result.", file=sys.stderr)


if __name__ == "__main__":
    main()
