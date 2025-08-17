.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help`
help:
	@grep -E \
		'^.PHONY: .*?## .*$$' $(MAKEFILE_LIST) | \
		sort | \
		awk 'BEGIN {FS = ".PHONY: |## "}; {printf "\033[36m%-16s\033[0m %s\n", $$2, $$3}'


.PHONY: install ## install required dependencies on bare metal
install:
	uv sync
	uv run pre-commit install


.PHONY: format ## Run the formatter on bare metal
format:
	uv run tox -e format


.PHONY: lint ## run the linter on bare metal
lint:
	uv run tox -e lint


.PHONY: test ## run unit tests on bare metal
test:
	uv run tox -e test


.PHONY: clean-docker ## Purge / remove related docker entities
clean-docker:
	docker compose down --remove-orphans


.PHONY: build-docker ## Build the main image in docker
build-docker:
	docker compose build


.PHONY: run-docker ## Runs containers with watching
run-docker:
	docker compose up


.PHONY: test-docker ## run unit tests in docker
test-docker:
	docker compose run --remove-orphans --entrypoint uv package run tox -e test


.PHONY: publish ## Build & publish the package to Nexus. Ensure to have UV_PUBLISH_USERNAME & UV_PUBLISH_PASSWORD environment variables set.
publish:
	@version=$$(grep '^version *= *' pyproject.toml | head -1 | sed 's/version *= *"\(.*\)"/\1/'); \
	echo "Current version: $$version"; \
	read -p "Publish version $$version? (y/n): " confirm; \
	if [ "$$confirm" = "y" ]; then \
		uv build --no-sources && \
		uv publish --verbose; \
	else \
		echo "Publish cancelled."; \
	fi