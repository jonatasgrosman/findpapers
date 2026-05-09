.PHONY: help clean setup test test_integration lint format complexity security docstrings dead-code coverage check

VENV ?= .venv
VENV_BIN = $(VENV)/bin
PYTHON = $(VENV_BIN)/python
PIP = $(VENV_BIN)/pip
POETRY = $(VENV_BIN)/poetry
PYTEST_ARGS ?=
TARGET ?= .

# Ensure poetry run uses our local venv even when the shell has not
# been activated with ``source .venv/bin/activate``.
export VIRTUAL_ENV := $(abspath $(VENV))
export POETRY_VIRTUALENVS_CREATE := false

-include .env
export $(shell [ -f .env ] && grep -v '^\s*#' .env | grep -v '^\s*$$' | sed 's/=.*//')

help:
	@echo "make clean"
	@echo "       clean project removing unnecessary files"
	@echo "make setup"
	@echo "       prepare environment"
	@echo "make lint [TARGET='path']"
	@echo "       run lint and formatting checks (optional: specify target path)"
	@echo "       examples: make lint TARGET='findpapers/models'"
	@echo "                 make lint TARGET='findpapers/models/query.py'"
	@echo "make format [TARGET='path']"
	@echo "       auto-fix formatting and lint issues (optional: specify target path)"
	@echo "       note: type errors (mypy) are NOT auto-fixed; run 'make lint' to review them"
	@echo "       examples: make format TARGET='findpapers/models'"
	@echo "                 make format TARGET='tests/unit/test_query.py'"
	@echo "make test [PYTEST_ARGS='args']"
	@echo "       run tests (optional: pass additional pytest arguments)"
	@echo "       examples: make test PYTEST_ARGS='-k test_name'"
	@echo "                 make test PYTEST_ARGS='tests/unit/test_query.py::TestClass -v'"
	@echo "make test_integration [PYTEST_ARGS='args']"
	@echo "       run integration/smoke tests that hit real external APIs"
	@echo "make complexity"
	@echo "       check cyclomatic complexity (fails if project average degrades below grade B)"
	@echo "make security"
	@echo "       security checks: static analysis (bandit) and dependency vulnerabilities (pip-audit)"
	@echo "make docstrings"
	@echo "       check docstring coverage (fails if below 95%)"
	@echo "make dead-code"
	@echo "       detect unused code (vulture)"
	@echo "make coverage"
	@echo "       run tests and fail if coverage drops below the configured threshold"
	@echo "make check"
	@echo "       run all quality checks: lint, complexity, security, docstrings, dead-code and coverage (includes running the test suite)"

setup:
	@[ -d $(VENV) ] || python -m venv $(VENV)
	@$(PIP) install --upgrade pip poetry
	@$(POETRY) install --with dev --no-interaction --no-ansi -vvv
	@touch poetry.lock

clean:
	@rm -rf build dist .eggs *.egg-info
	@rm -rf .benchmarks .coverage reports htmlcov .tox
	@find . -type d -name '.mypy_cache' -exec rm -rf {} +
	@find . -type d -name '__pycache__' -exec rm -rf {} +
	@find . -type d -name '*pytest_cache*' -exec rm -rf {} +
	@find . -type f -name "*.py[co]" -exec rm -rf {} +

test:
	@$(POETRY) run pytest --durations=3 -v --cov=${PWD}/findpapers --cov-report=term-missing $(PYTEST_ARGS)

test_integration:
	@$(POETRY) run pytest -v -m integration $(PYTEST_ARGS)

lint:
	@$(POETRY) run ruff check $(TARGET)
	@$(POETRY) run ruff format --check $(TARGET)
	@if [ "$(TARGET)" = "." ]; then \
		MYPYPATH=typings $(POETRY) run mypy findpapers tests/unit; \
	else \
		MYPYPATH=typings $(POETRY) run mypy $(TARGET); \
	fi

complexity:
	@$(POETRY) run xenon --max-absolute C --max-average B findpapers/

# PYSEC-2022-42969 (py): no fix available upstream; py is a transitive dep of
# interrogate and the vulnerable code path (py.path.svn) is never exercised here.
security:
	@$(POETRY) run bandit -r findpapers/ -c pyproject.toml
	@$(POETRY) run pip-audit --ignore-vuln PYSEC-2022-42969

docstrings:
	@$(POETRY) run interrogate findpapers/

dead-code:
	@$(POETRY) run vulture findpapers/

coverage:
	@$(POETRY) run pytest --durations=3 -q --cov=${PWD}/findpapers --cov-report=term-missing $(PYTEST_ARGS)

check:
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory complexity
	@$(MAKE) --no-print-directory security
	@$(MAKE) --no-print-directory docstrings
	@$(MAKE) --no-print-directory dead-code
	@$(MAKE) --no-print-directory coverage

format:
	@$(POETRY) run ruff check $(TARGET) --fix
	@$(POETRY) run ruff format $(TARGET)
