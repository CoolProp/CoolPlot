# -*- coding: utf-8 -*-
"""Type checking: the package ships its annotations (``src/coolplot/py.typed``).

mypy checks three things here:

1. the package itself, with the settings of ``[tool.mypy]`` in pyproject.toml;
2. ``tests/typing_checks/public_api.py`` in strict mode: the types an
   application sees when it uses the public API, and mistakes it is told
   about;
3. the gallery examples (``examples/``), as code a user would write.

The last two use the settings of a project that uses CoolPlot
(``tests/typing_checks/mypy.ini``), so mypy finds coolplot as an installed
package, which it only reads when the package carries the py.typed marker.
The package has to be installed (``pip install -e .``) for them.

The mypy runs need mypy (``pip install -e ".[typing]"``) and are skipped
without it; the tests workflow runs them in its ``typing`` job.
"""
import ast
import glob
import os
import subprocess
import sys
import tomllib

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PACKAGE = os.path.join(ROOT, "src", "coolplot")
CHECKS = os.path.join(ROOT, "tests", "typing_checks")


def _mypy(*args):
    """Run mypy in the repository; returns its report. Fails the test when mypy finds an error."""
    pytest.importorskip("mypy")
    run = subprocess.run([sys.executable, "-m", "mypy", *args], cwd=ROOT, capture_output=True, text=True)
    report = run.stdout + run.stderr
    assert run.returncode == 0, report
    return report


def test_the_package_carries_the_py_typed_marker():
    assert os.path.isfile(os.path.join(PACKAGE, "py.typed"))
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        package_data = tomllib.load(f)["tool"]["setuptools"]["package-data"]
    assert "py.typed" in package_data["coolplot"]   # so that the wheel and the sdist carry it


def test_type_checkers_see_every_lazily_loaded_name():
    """coolplot/__init__.py loads its names on first access; under TYPE_CHECKING
    it imports the same names from the same modules, for type checkers."""
    tree = ast.parse(open(os.path.join(PACKAGE, "__init__.py"), encoding="utf-8").read())
    lazy = next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "_LAZY")
    block = next(node for node in tree.body
                 if isinstance(node, ast.If) and getattr(node.test, "id", None) == "TYPE_CHECKING")
    imported = {}
    for node in block.body:
        assert isinstance(node, ast.ImportFrom) and node.level == 1, ast.dump(node)
        for alias in node.names:
            assert alias.asname == alias.name, "re-export {0} as {0}".format(alias.name)
            imported[alias.name] = "." + node.module
    assert imported == lazy


def test_the_package_type_checks():
    """mypy with the package's own settings ([tool.mypy] in pyproject.toml)."""
    report = _mypy()
    assert "Success" in report


def test_the_public_api_as_an_application_sees_it():
    _mypy("--config-file", os.path.join(CHECKS, "mypy.ini"), "--strict", os.path.join(CHECKS, "public_api.py"))


def test_the_examples_type_check():
    examples = sorted(glob.glob(os.path.join(ROOT, "examples", "*.py")))
    web_app = sorted(glob.glob(os.path.join(ROOT, "examples", "web_app", "*.py")))
    assert examples and web_app
    _mypy("--config-file", os.path.join(CHECKS, "mypy.ini"), *examples, *web_app)
