# AtlasBridge — developer workflow targets
#
# Quick start:
#   make install    — install package + dev deps in editable mode
#   make test       — run the full test suite
#   make lint       — lint + format check
#   make check      — lint + type check + tests (CI equivalent)

PYTHON ?= python3

.PHONY: install test lint format typecheck check clean

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/ -q

test-verbose:
	$(PYTHON) -m pytest tests/ -v --tb=short

lint:
	$(PYTHON) -m ruff check src/ tests/
	$(PYTHON) -m ruff format --check src/ tests/

format:
	$(PYTHON) -m ruff format src/ tests/
	$(PYTHON) -m ruff check --fix src/ tests/

typecheck:
	$(PYTHON) -m mypy src/atlasbridge/

check: lint typecheck test

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
