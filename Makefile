.PHONY: help clean setup test test_report run_sample

include .env
export $(shell sed 's/=.*//' .env)

help:
	@echo "make clean"
	@echo "       clean project removing unnecessary files"
	@echo "make setup"
	@echo "       prepare environment"
	@echo "make test"
	@echo "       run tests"
	@echo "make test_report"
	@echo "       run tests and save tests and coverag reports"
	@echo "make run_sample sample_file=name_of_sample.py"
	@echo "       run a script contained in samples folder"
	@echo "       e.g. make run_sample sample_file=some_research.py"

setup: poetry.lock
poetry.lock: pyproject.toml
	poetry install
	touch poetry.lock

clean:
	@rm -rf build dist .eggs *.egg-info
	@rm -rf .benchmarks .coverage coverage.xml htmlcov report.xml .tox
	@find . -type d -name '.mypy_cache' -exec rm -rf {} +
	@find . -type d -name '__pycache__' -exec rm -rf {} +
	@find . -type d -name '*pytest_cache*' -exec rm -rf {} +
	@find . -type f -name "*.py[co]" -exec rm -rf {} +

test: setup
	poetry run pytest --durations=3 -v --cov=${PWD}/findpapers 

test_report: setup
	poetry run pytest --durations=3 -v --cov=${PWD}/findpapers --cov-report xml:reports/coverage.xml --junitxml=reports/tests.xml

run_sample: setup
	poetry run python samples/${sample_file}
