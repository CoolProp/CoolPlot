# Type annotations

CoolPlot ships its type annotations: the package carries the marker file
`src/coolplot/py.typed` (PEP 561), so a type checker such as mypy or
pyright reads the types of CoolPlot when it checks an application that
uses it. Type safety is the main topic of the 1.3 releases; this page
says what is checked and how the checks grow.

## What is checked

`tests/test_typing.py` runs mypy three times:

1. **The package**, with the settings of `[tool.mypy]` in
   `pyproject.toml`. Every function is checked, also the ones without
   annotations (`check_untyped_defs`), and an unused
   `# type: ignore` is an error. The modules applications work with
   (`coolplot`, `coolplot.chart`, `coolplot.diagram`,
   `coolplot.psychrometric`, `coolplot.export`) are fully annotated, and
   mypy keeps them so (`disallow_untyped_defs`).
2. **The public API as an application sees it**:
   `tests/typing_checks/public_api.py` uses the charts the way a script
   does, with `assert_type` for what each call returns, and lists
   mistakes mypy has to report (each with the `# type: ignore[code]` of
   its error). It is checked in strict mode, with the settings of a
   project that uses CoolPlot (`tests/typing_checks/mypy.ini`): mypy then
   finds coolplot as an installed package, which it only reads with the
   `py.typed` marker.
3. **The examples** in `examples/`, as code a user would write.

```bash
pip install -e ".[test,typing]"
make typecheck                # or: python -m pytest -v tests/test_typing.py
python -m mypy                # only the package, with its own settings
```

Without mypy installed the three tests are skipped; the `typing` job of
the tests workflow runs them with a pinned mypy. The `build` job checks
that the wheel and the sdist carry `py.typed`.

## Writing annotations

* Annotate what a function takes from its callers and what it returns.
  Use the aliases for what users give in several forms:
  `coolplot.core.units.UnitsLike` (a unit system or its name),
  `coolplot.core.limits.TpLimitsLike`, `coolplot.chart.Numbers` (a list,
  a tuple or a numpy array of numbers) and `coolplot.diagram.FluidLike`.
* A state given as a dict is typed `Any` (`coolplot.chart.StateEntry`):
  to a type checker, a dict that mixes numbers and texts, or a list that
  mixes dicts and StatePoints, holds plain objects. The chart checks
  every state when it gets it.
* The scene holds three kinds of items; code that reads `x`, `y` or
  `style` takes `coolplot.scene.SceneItem` (one of `Line`, `Markers`,
  `Text`) and tells them apart with `isinstance`.
* `Optional[X]` for a value that may be None, and a test for None before
  the value is used. Where the code knows better than the checker (a
  value set together with another one), an `assert value is not None`
  with a comment that says why.
* `# type: ignore[code]` only with the error code and a comment, and only
  where the checker cannot follow (a C extension without stubs, a check
  the code does itself). Unused ones fail the check.
* Classes and modules that answer unknown names through `__getattr__`
  (old names that say what to write instead) define it under
  `if not TYPE_CHECKING:`; otherwise a checker accepts every misspelt
  name.
* `coolplot/__init__.py` loads its names on first access; under
  `if TYPE_CHECKING:` it imports the same names for type checkers, as
  `from .module import Name as Name`. A new name goes into both lists
  (`tests/test_typing.py` compares them).

## Growing the checks

During 1.x more modules join the fully annotated list in
`pyproject.toml`, layer by layer from the bottom (`core`, `style`,
`scene`, `spec`), until the whole package passes `mypy --strict`. A
module joins the list in the change that completes its annotations, so
that it cannot lose them again.
