# Vendored Lagoon GraphQL SDL

This directory holds a single, version-pinned copy of the Lagoon GraphQL
schema. It is the single input to the Phase 3 module generator, and it ships
with the built `salsadigitalauorg.lagoon` collection (it is intentionally
**not** in `galaxy.yml`'s `build_ignore`).

There must be exactly **one** `schema/lagoon-*.graphql` file at a time. Do not
add a second version alongside it — replace it, following the procedure below.

- `schema/lagoon-<VERSION>.graphql` — the fetched SDL, committed verbatim.
  Never hand-edit, reformat, or prettify this file. It is a vendored artifact;
  byte-for-byte fidelity is what makes the drift guard (Phase 8) meaningful.
- `schema/VERSION` — provenance record: the Lagoon version the SDL was
  fetched from, the endpoint, the fetch date, who fetched it, and the tool
  used.

## Refreshing the schema

The generator relies on SDL `"""..."""` descriptions for module option help
text. If the fetched SDL has no descriptions, generated docs will be empty
and the fetch must be redone against a different endpoint.

```sh
# 1. Pick the target Lagoon.
lagoon config list
lagoon login -l <target>
export LAGOON_TOKEN=$(lagoon -l <target> get token)
export LAGOON_GRAPHQL=https://api.lagoon.example.com/graphql   # the target's endpoint

# 2. Record the exact server version. This value drives the filename,
#    schema/VERSION, and every generated-file header.
curl -sS "$LAGOON_GRAPHQL" \
  -H "Authorization: Bearer $LAGOON_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ lagoonVersion }"}'
# -> {"data":{"lagoonVersion":"<VERSION>"}}

# 3. Print the SDL. gql-cli emits SDL including descriptions.
pip install 'gql[requests]'
mkdir -p schema
gql-cli "$LAGOON_GRAPHQL" --print-schema \
  --header Authorization:"Bearer $LAGOON_TOKEN" \
  > schema/lagoon-<VERSION>.graphql

# 4. Sanity-check descriptions survived introspection.
grep -c '"""' schema/lagoon-<VERSION>.graphql    # must be > 0, expect hundreds
```

If step 4 returns `0`, the server has introspection descriptions disabled.
Stop — generated docs would be empty. Try a different endpoint or raise it.

This procedure is codified as a `make fetch-schema` target (see the root
`Makefile`). It requires `LAGOON_GRAPHQL`, `LAGOON_TOKEN`, and `LAGOON_VERSION`
to be set, refuses to run if any are missing, and refuses to overwrite an
existing `schema/lagoon-<VERSION>.graphql`.

```sh
export LAGOON_GRAPHQL=https://api.lagoon.example.com/graphql
export LAGOON_TOKEN=$(lagoon -l <target> get token)
export LAGOON_VERSION=2.33.0
make fetch-schema
```

**Do not pass `LAGOON_TOKEN` on the `make` command line**
(e.g. `make fetch-schema LAGOON_TOKEN=...`). Command-line arguments are
visible to other users on the same host via the process table (`ps`). Always
export it into the environment first, as shown above.

After a successful fetch, delete the old `schema/lagoon-<OLD_VERSION>.graphql`,
update `schema/VERSION` with the new version, endpoint, date, and fetcher, and
commit both together in a single commit.

## Do not

- Do not delete or modify `api/tests/common/schema.graphql`. It belongs to the
  v1 `lagoon.api` collection and is used by v1's tests.
- Do not add `schema/` to `build_ignore`. It ships with the collection.
- Do not reformat, prettify, or hand-edit the vendored SDL.
