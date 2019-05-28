@ECHO OFF

REM Command file for CoolPlot

if "%1" == "" goto help

if "%1" == "help" (
	:help
	echo.Please use `make ^<target^>` where ^<target^> is one of
	echo.  init     to install development packages
	echo.  test     to run the tests for this package
	echo.  install  to install the package locally
	echo.  docs     to create the documentation
	echo.  build    shorthand notation for init, install, test, docs
	echo.  upload   to upload wheels to PyPI
	goto end
)

if "%1" == "init" (
	for /d %%i in (%BUILDDIR%\*) do rmdir /q /s %%i
	del /q /s %BUILDDIR%\*
	goto end
)


if "%1" == "init" (
	pip install -r requirements.txt
	pip install -r requirements_dev.txt
	goto end
)

if "%1" == "test" (
	nosetests -v --with-coverage --cover-package=CoolPlot
	goto end
)

if "%1" == "install" (
	python setup.py install
	goto end
)

if "%1" == "docs" (
	cd docs && make html
	goto end
)

if "%1" == "build" (
	CALL make.bat init 
	CALL make.bat install
	CALL make.bat test
	CALL make.bat docs
	@echo "Build completed."
	goto end
)

if "%1" == "upload" (
	python setup.py upload
	goto end
)

:end
