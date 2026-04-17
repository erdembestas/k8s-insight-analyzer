.PHONY: help test lint run-dry

help:
	@echo "Makefile commands:"
	@echo "  make test        - run pytest"
	@echo "  make lint        - run ansible-lint (if installed)"
	@echo "  make run-dry     - run a dry local simulation (MOCK_LLM=1)"

test:
	pytest -q

lint:
	ansible-lint || true

run-dry:
	@echo "Run a single-cluster dry run (requires ansible-playbook)"
	export PATH="$(PWD)/mocks:$$PATH" && export MOCK_LLM=1 && ansible-playbook playbooks/tmp_run_single_cluster.yml
