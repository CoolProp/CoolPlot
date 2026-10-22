# Makefile for CoolPlot

.PHONY: help install test test-all test-slow typecheck docs build

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  install  to install the package for development, with test tools"
	@echo "  test     to run the tests"
	@echo "  typecheck to run mypy over the package, the public API and the examples"
	@echo "  build    to build the source and wheel distributions"

install:
	python -m pip install -e ".[test,typing]"

test:
	python -m pytest -v

test-all:   ## also the tests that need a browser and Kaleido
	python -m pytest -v --run-browser --run-kaleido

test-slow:  ## the numerics sweeps over every line of every diagram type
	python -m pytest -v --run-slow tests/numerics

typecheck:  ## mypy, as in tests/test_typing.py (needs the typing extra)
	python -m pytest -v tests/test_typing.py

docs:       ## build the documentation (warnings are errors; runs the examples)
	python -m sphinx -W --keep-going -b html docs docs/_build/html

build:
	python -m build
