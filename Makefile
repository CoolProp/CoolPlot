# Makefile for CoolPlot
#

.PHONY: init test install docs build upload

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  init     to install development packages"
	@echo "  test     to run the tests for this package"
	@echo "  install  to install the package locally"
	@echo "  docs     to create the documentation"
	@echo "  build    shorthand notation for init, install, test, docs"
	@echo "  upload   to upload wheels to PyPI"

init:
	pip install -r requirements.txt
	pip install -r requirements_dev.txt

test:
	nosetests tests

install:
	python setup.py install

docs:
	cd docs && make html

build: init install test docs
	@echo "Build completed."

upload:
	python setup.py upload
