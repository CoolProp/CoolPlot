# Contributing

Pull requests are welcome. This page has the rules that keep the package
in shape; the design and its history are in {doc}`architecture`, the
decisions of the road to 1.0 in {doc}`v1_plan` and the review that led
to them in {doc}`v1_review`.

## Set up

```bash
git clone https://github.com/CoolProp/CoolPlot
cd CoolPlot
pip install -e ".[test,typing,matplotlib,plotly]"
pip install -r docs/requirements.txt    # Sphinx and its extensions, for make docs
make test                      # about four minutes
make test-all                  # also the browser and Kaleido tests
make test-slow                 # the numerics sweeps, minutes per fluid
make typecheck                 # mypy: the package, the public API, the examples
make docs                      # sphinx-build -W, runs the examples
```

## Layers

The package is a pipeline of layers ({doc}`../explanation/pipeline`),
and each layer may only import the layers before it:

| Layer | May use | Talks to |
|---|---|---|
| `core` (quantities, units, states, errors) | nothing | |
| `style` | core | |
| `scene` | core, style | |
| `spec` | core, style, scene | |
| `thermo` | core | CoolProp, the only layer that does |
| `engine` | core, spec, thermo | |
| `compose` | core, style, scene, spec, engine | |
| `corelib` (the bridge to coolplot-core) | core, style, scene | the `coolplot_core` module, when installed |
| `render` | core, style, scene, corelib | matplotlib (`render.mpl` only), plotly (`render.plotly` only) |
| `chart`, `diagram`, `psychrometric`, `export`, `interaction` | everything | |
| `testing` | everything; no backend may import it when a chart is drawn | |

`tests/test_architecture.py` checks these rules; a change that breaks
one fails there first.

## Conventions

* Physical quantities are named symbol, qualifier, unit:
  `T_cond_sat_C`, `p_evap_out_bar`, `m_dot_kg_s`, `dT_sh_K`. Rates take
  `_dot`, differences `d`, units are always an explicit suffix.
* Source files are ASCII. No em dashes, no curved quotes, no emoji.
* Code is kept simple and legible; the readers are engineers and
  thermodynamicists. An advanced construct gets a comment that says why.
* Every public name has a docstring; the docs build checks it
  (`numpydoc`).
* The package ships its type annotations and mypy checks them
  ({doc}`typing`): new code is annotated, and `make typecheck` passes.
* Behaviour changes are listed in the changelog under *Unreleased*.
* Every function stays below a cyclomatic complexity of 15
  (`radon cc -n C src/coolplot`).

## Numerics

A change to `coolplot.thermo` runs the sweeps in `tests/numerics`
(`pytest --run-slow tests/numerics`): every line family of every diagram
type for R290, CO2, R410A and R32/R125, checking that every point is a
state at the line's constant, that lines have no gaps or reversals, and
that almost nothing is computed outside the chart.

## Types

{doc}`typing` says what mypy checks (the package, the public API as an
application sees it, the examples) and how annotations are written.

## Writing a backend

{doc}`writing_a_backend` lists what a plotting backend has to do, and
`coolplot.testing` has the conformance kit that checks it.

## Releasing

A version tag publishes a release to PyPI through GitHub Actions; the
steps and the one-time setup are in {doc}`releasing`.

```{toctree}
:maxdepth: 1
:hidden:

typing
writing_a_backend
core
releasing
architecture
v1_plan
v1_review
review_checklist
```
