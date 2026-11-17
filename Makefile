UV ?= uv
EXPERIMENT_FLAGS ?= --quick

.PHONY: setup lint typecheck test experiments figures report demo

setup:
	$(UV) sync --locked --extra dev

lint:
	$(UV) run --locked --extra dev ruff check .

typecheck:
	$(UV) run --locked --extra dev mypy --strict src experiments demos

test:
	$(UV) run --locked --extra dev pytest

experiments:
	$(UV) run --locked --extra dev python experiments/run_all.py $(EXPERIMENT_FLAGS)

figures report: experiments

demo:
	$(UV) run --locked --extra dev python demos/secure_chat.py --self-test
	$(UV) run --locked --extra dev python demos/file_encrypt_demo.py self-test
