.PHONY: help setup test

include .env
export $(shell sed 's/=.*//' .env)

VENV_NAME?=venv
PYTHON=${VENV_NAME}/bin/python3
PYTEST=${VENV_NAME}/bin/pytest

help:
	@echo "make setup"
	@echo "       prepare environment"
	@echo "make test"
	@echo "       run tests"
	@echo "make test_report"
	@echo "       run tests and save tests and coverag reports"
	@echo "make run_sample sample_file=name_of_sample.py"
	@echo "       run a script contained in samples folder"
	@echo "       e.g. make run_sample sample_file=some_research.py"

setup: $(VENV_NAME)/bin/activate
$(VENV_NAME)/bin/activate: setup.py
	test -d $(VENV_NAME) || python3 -m venv $(VENV_NAME)
	${PYTHON} -m pip install -U pip
	${PYTHON} -m pip install -e '.[test]'
	${PYTHON} -m pip install -e '.[documentation]'
	${PYTHON} -m pip install -e .
	touch $(VENV_NAME)/bin/activate

test: setup
	${PYTEST} --durations=3 -v --cov=${PWD}/findpapers 

test_report: setup
	${PYTEST} --durations=3 -v --cov=${PWD}/findpapers --cov-report xml:reports/coverage.xml --junitxml=reports/tests.xml

run_sample: setup
	${PYTHON} samples/${sample_file}
