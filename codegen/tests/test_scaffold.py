from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


def test_graphql_core_importable():
    """Confirms the container has the generator's actual dependency,
    not just a package that happens to share the name."""
    import graphql
    assert hasattr(graphql, 'build_schema')


def test_vendored_sdl_parses():
    """First real use of graphql-core against the SDL this collection
    ships -- proves the P2-S7 unresolved assumption (SDL loads under a
    graphql-import-based loader) generalises to graphql-core's own
    parser, which is what codegen/ actually uses at generation time.
    P2-S7 only proved the mock server's loader; this proves the
    generator's."""
    from pathlib import Path
    from graphql import build_schema
    sdl = Path(__file__).parents[2] / 'schema' / 'lagoon-2.33.0.graphql'
    schema = build_schema(sdl.read_text())
    assert schema.query_type is not None
    assert schema.mutation_type is not None
