.PHONY: help clean setup test test-integration lint format types complexity security deps-audit docstrings dead-code check
.DEFAULT_GOAL := help

VENV ?= .venv
VENV_BIN = $(VENV)/bin
PIP = $(VENV_BIN)/pip
POETRY = $(VENV_BIN)/poetry
PYTEST_ARGS ?=
TARGET ?= .
FIX ?=

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
	@echo "make lint [TARGET='path'] [FIX=1]"
	@echo "       check for lint issues with ruff; pass FIX=1 to auto-fix (optional: specify target path)"
	@echo "make format [TARGET='path'] [FIX=1]"
	@echo "       check code formatting with ruff; pass FIX=1 to auto-fix (optional: specify target path)"
	@echo "make types [TARGET='path']"
	@echo "       run static type checks with mypy (optional: specify target path)"
	@echo "       note: type errors are NOT auto-fixed"
	@echo "make test [PYTEST_ARGS='args']"
	@echo "       run tests with coverage report (optional: pass additional pytest arguments)"
	@echo "       examples: make test PYTEST_ARGS='-k test_name'"
	@echo "                 make test PYTEST_ARGS='tests/unit/test_query.py::TestClass -v'"
	@echo "make test-integration [PYTEST_ARGS='args']"
	@echo "       run integration/smoke tests that hit real external APIs"
	@echo "make complexity"
	@echo "       check cyclomatic complexity with xenon (fails if any block exceeds grade C)"
	@echo "make security"
	@echo "       run static security analysis with bandit"
	@echo "make deps-audit"
	@echo "       check dependencies for known vulnerabilities with pip-audit"
	@echo "make docstrings"
	@echo "       check docstring coverage with interrogate (fails if below 95%)"
	@echo "make dead-code"
	@echo "       detect unused code with vulture"
	@echo "make check"
	@echo "       run all quality checks: lint, format, types, complexity,"
	@echo "       security, deps-audit, docstrings, dead-code and test"

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
	@$(POETRY) run pytest --durations=3 -v --cov=$(PWD)/findpapers --cov-report=term-missing $(PYTEST_ARGS)

test-integration:
	@$(POETRY) run pytest -v -m integration $(PYTEST_ARGS)

lint:
	@$(POETRY) run ruff check $(if $(FIX),--fix) $(TARGET)

format:
	@$(POETRY) run ruff format $(if $(FIX),,--check) $(TARGET)

types:
	@if [ "$(TARGET)" = "." ]; then \
		MYPYPATH=typings $(POETRY) run mypy findpapers tests/unit; \
	else \
		MYPYPATH=typings $(POETRY) run mypy $(TARGET); \
	fi

complexity:
	@$(POETRY) run xenon --max-absolute C --max-average B findpapers/

security:
	@$(POETRY) run bandit -r findpapers/ -c pyproject.toml

# PYSEC-2022-42969 (py): no fix available upstream; py is a transitive dep of
# interrogate and the vulnerable code path (py.path.svn) is never exercised here.
deps-audit:
	@$(POETRY) run pip-audit --ignore-vuln PYSEC-2022-42969

docstrings:
	@$(POETRY) run interrogate findpapers/

dead-code:
	@$(POETRY) run vulture findpapers/

check:
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory format
	@$(MAKE) --no-print-directory types
	@$(MAKE) --no-print-directory complexity
	@$(MAKE) --no-print-directory security
	@$(MAKE) --no-print-directory deps-audit
	@$(MAKE) --no-print-directory docstrings
	@$(MAKE) --no-print-directory dead-code
	@$(MAKE) --no-print-directory test
