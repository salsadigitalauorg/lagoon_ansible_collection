COLLECTION_PATH := /usr/share/ansible/collections/ansible_collections/salsadigitalauorg/lagoon

.PHONY: test build lint-docs shell fetch-schema mock-up mock-down verify-mock \
	codegen-test codegen-shell

test:            ## Run unit tests in the containerised ansible-test image
	docker compose run --rm test-v3 units -v --requirements

build:           ## Build the collection artifact and list its contents
	ansible-galaxy collection build --force --output-path ./dist

lint-docs:
	docker compose run --rm lint-docs-v3

shell:
	docker compose run --rm test-v3 bash

mock-up:            ## Start the v3 GraphQL mock, serving the vendored SDL
	docker compose up -d --build graphql-mock-v3

mock-down:            ## Stop the v3 GraphQL mock
	docker compose stop graphql-mock-v3

verify-mock: mock-up            ## Confirm the vendored SDL loads under the mock's graphql-import
	# `me { id email }` deliberately avoids any field typed as the custom
	# `JSON` scalar (e.g. lagoonVersion) -- @graphql-tools/mock cannot
	# auto-mock a custom scalar with no mock function registered for it
	# and raises "No mock defined for type "JSON"" even on a
	# successfully loaded schema, on both this service and the v1
	# graphql-mock. A plain-scalar field is what actually proves the SDL
	# parsed and resolved under graphql-import, which is this target's
	# job.
	curl -sS -X POST http://localhost:4200/graphql \
	  -H 'Content-Type: application/json' \
	  -d '{"query":"{ me { id email } }"}' | grep -q '"email"'

codegen-test:            ## Run codegen's own test suite in its own container
	docker compose run --rm codegen-v3

codegen-shell:
	docker compose run --rm --entrypoint bash codegen-v3

fetch-schema:            ## Fetch and vendor the Lagoon SDL. Requires LAGOON_GRAPHQL, LAGOON_TOKEN, LAGOON_VERSION
	@test -n "$(LAGOON_GRAPHQL)" || (echo "LAGOON_GRAPHQL is required" && exit 1)
	@test -n "$(LAGOON_TOKEN)"   || (echo "LAGOON_TOKEN is required" && exit 1)
	@test -n "$(LAGOON_VERSION)" || (echo "LAGOON_VERSION is required" && exit 1)
	@test ! -f schema/lagoon-$(LAGOON_VERSION).graphql || \
	  (echo "schema/lagoon-$(LAGOON_VERSION).graphql exists; remove it first" && exit 1)
	gql-cli "$(LAGOON_GRAPHQL)" --print-schema \
	  --header Authorization:"Bearer $(LAGOON_TOKEN)" \
	  > schema/lagoon-$(LAGOON_VERSION).graphql
	@grep -q '"""' schema/lagoon-$(LAGOON_VERSION).graphql || \
	  (echo "FAIL: SDL has no descriptions -- generated docs would be empty" && exit 1)
