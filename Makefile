COLLECTION_PATH := /usr/share/ansible/collections/ansible_collections/salsadigitalauorg/lagoon

.PHONY: test build lint-docs shell

test:            ## Run unit tests in the containerised ansible-test image
	docker compose run --rm test-v3 units -v --requirements

build:           ## Build the collection artifact and list its contents
	ansible-galaxy collection build --force --output-path ./dist

lint-docs:
	docker compose run --rm lint-docs-v3

shell:
	docker compose run --rm test-v3 bash
