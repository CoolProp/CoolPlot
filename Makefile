# Makefile for CoolPlot

.PHONY: help install test build

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  install  to install the package for development, with test tools"
	@echo "  test     to run the tests"
	@echo "  build    to build the source and wheel distributions"

install:
	python -m pip install -e ".[test]"

test:
	python -m pytest -v

build:
	python -m build
