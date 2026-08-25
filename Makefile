COLLECTION_PATH := /usr/share/ansible/collections/ansible_collections/salsadigitalauorg/lagoon

.PHONY: test build lint-docs shell fetch-schema

test:            ## Run unit tests in the containerised ansible-test image
	docker compose run --rm test-v3 units -v --requirements

build:           ## Build the collection artifact and list its contents
	ansible-galaxy collection build --force --output-path ./dist

lint-docs:
	docker compose run --rm lint-docs-v3

shell:
	docker compose run --rm test-v3 bash

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
