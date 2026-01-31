.PHONY: help clean setup test test_report lint format

VENV ?= venv
VENV_BIN = $(VENV)/bin
PYTHON = $(VENV_BIN)/python
PIP = $(VENV_BIN)/pip
POETRY = $(VENV_BIN)/poetry

include .env
export $(shell sed 's/=.*//' .env)

help:
	@echo "make clean"
	@echo "       clean project removing unnecessary files"
	@echo "make setup"
	@echo "       prepare environment"
	@echo "make lint"
	@echo "       run lint and formatting checks"
	@echo "make format"
	@echo "       auto-fix formatting and lint issues"
	@echo "make test"
	@echo "       run tests"
	@echo "make test_report"
	@echo "       run tests and save tests and coverag reports"

setup:
	@python -m venv $(VENV)
	@$(PIP) install --upgrade pip poetry
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) install --with dev --no-interaction --no-ansi -vvv
	@touch poetry.lock

clean:
	@rm -rf build dist .eggs *.egg-info
	@rm -rf .benchmarks .coverage reports htmlcov .tox
	@find . -type d -name '.mypy_cache' -exec rm -rf {} +
	@find . -type d -name '__pycache__' -exec rm -rf {} +
	@find . -type d -name '*pytest_cache*' -exec rm -rf {} +
	@find . -type f -name "*.py[co]" -exec rm -rf {} +

test:
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) run pytest --durations=3 -v --cov=${PWD}/findpapers 

test_report:
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) run pytest --durations=3 -v --cov=${PWD}/findpapers --cov-report xml:reports/coverage.xml --junitxml=reports/tests.xml

lint:
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) run ruff check .
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) run isort --check-only .
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) run black --check .
	@MYPYPATH=typings POETRY_VIRTUALENVS_CREATE=false $(POETRY) run mypy findpapers tests/unit

format:
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) run ruff check . --fix
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) run isort .
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) run black .

publish:
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) config pypi-token.pypi ${FINDPAPERS_PYPI_API_TOKEN}
	@POETRY_VIRTUALENVS_CREATE=false $(POETRY) publish --build
