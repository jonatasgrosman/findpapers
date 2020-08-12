.PHONY: help setup test

include .env
export $(shell sed 's/=.*//' .env)

VENV_NAME?=venv
PYTHON=${VENV_NAME}/bin/python3
COVERAGE=${VENV_NAME}/bin/coverage
TESTING_BASE_PATH=tests/

help:
	@echo "make setup"
	@echo "       prepare environment"
	@echo "make test"
	@echo "       run tests"

setup: $(VENV_NAME)/bin/activate
$(VENV_NAME)/bin/activate: setup.py
	test -d $(VENV_NAME) || python3 -m venv $(VENV_NAME)
	${PYTHON} -m pip install -U pip
	${PYTHON} -m pip install -e '.[test]'
	${PYTHON} -m pip install -e '.[documentation]'
	${PYTHON} -m pip install -e .
	touch $(VENV_NAME)/bin/activate

test: setup
	$(eval export FLASK_ENV=testing)
	${COVERAGE} run -m pytest ${TESTING_BASE_PATH} --junitxml=reports/tests.xml
	${COVERAGE} xml -o reports/coverage.xml
