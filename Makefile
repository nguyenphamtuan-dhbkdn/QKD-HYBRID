UV ?= uv

.PHONY: setup lint typecheck test

setup:
	$(UV) sync --locked --extra dev

lint:
	$(UV) run ruff check .

typecheck:
	$(UV) run mypy --strict src

test:
	$(UV) run pytest
