.PHONY: help clean setup test test_report lint

include .env
export $(shell sed 's/=.*//' .env)

help:
	@echo "make clean"
	@echo "       clean project removing unnecessary files"
	@echo "make setup"
	@echo "       prepare environment"
	@echo "make lint"
	@echo "       run lint and formatting checks"
	@echo "make test"
	@echo "       run tests"
	@echo "make test_report"
	@echo "       run tests and save tests and coverag reports"

setup: poetry.lock
poetry.lock: pyproject.toml
	@poetry install -vvv
	@touch poetry.lock

clean:
	@rm -rf build dist .eggs *.egg-info
	@rm -rf .benchmarks .coverage reports htmlcov .tox
	@find . -type d -name '.mypy_cache' -exec rm -rf {} +
	@find . -type d -name '__pycache__' -exec rm -rf {} +
	@find . -type d -name '*pytest_cache*' -exec rm -rf {} +
	@find . -type f -name "*.py[co]" -exec rm -rf {} +

test: setup
	@poetry run pytest --durations=3 -v --cov=${PWD}/findpapers 

test_report: setup
	@poetry run pytest --durations=3 -v --cov=${PWD}/findpapers --cov-report xml:reports/coverage.xml --junitxml=reports/tests.xml

lint:
	@python -m pip install --upgrade pip
	@pip install ruff mypy isort black
	@poetry install --no-interaction --no-ansi
	@ruff check .
	@isort --check-only .
	@black --check .
	@mypy findpapers tests/unit --exclude 'tests/integration|_ignore' --ignore-missing-imports --allow-untyped-defs --allow-untyped-globals --follow-imports=silent || true

publish: setup
	@poetry config pypi-token.pypi ${FINDPAPERS_PYPI_API_TOKEN}
	@poetry publish --build
