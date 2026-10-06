# CoolPlot architecture

This document reviews the code CoolPlot inherited from CoolProp 6.3 and
describes the layered architecture that replaces it. The goals are:

1. Separate property calculations from plotting completely.
2. Make matplotlib one rendering backend among several.
3. Support interactive applications, where a small change (a slider, a
   new isoline, a unit switch) must only recompute and redraw what it
   affects.

The new layers live next to the legacy code (`CoolPlot/Plot`,
`CoolPlot/Util`), which stays until the new API covers all of its
features.


## 1. Review of the legacy code

### It does not run

* `PropertyPlot('R290', 'ph')` raises a `TypeError` with CoolProp 8.
  `EnhancedState` subclasses `CoolProp.AbstractState` and calls
  `CoolProp.AbstractState.__init__(backend, fluid)` without `self`
  (`CoolPlot/Util/EnhancedState.py:93`). With the old Cython bindings this
  call happened to be a silent no-op; the pybind11 bindings of CoolProp 8
  reject it. Subclassing a compiled class of
  another project is fragile in any case.
* The cycle classes import `BasePlot`, `PropertyDict` and `SIunits` from
  `CoolProp.Plots.Common` (`CoolPlot/Plot/SimpleCycles.py:11`), so CoolPlot
  mixes its own class hierarchy with the one shipped inside CoolProp.
* The test suite tests nothing: `test_basic.py` asserts `True`,
  `test_advanced.py` calls a template placeholder `hmm()`. It still used
  nose and Travis, both defunct.
* `six` is imported but not declared as a dependency.

### Calculation, units and matplotlib are interleaved

`BasePlot` (`CoolPlot/Plot/Common.py:402`) is at the same time the fluid
model, the unit converter, the owner of the matplotlib `Figure` and
`Axes`, and the place where isolines are computed. Consequences:

* Results of calculations depend on matplotlib state.
  `get_axis_limits` reads and writes the autoscale flags of the axes
  (`Common.py:667-711`); `calc_isolines` derives its ranges from it.
* Label placement reads the figure size in inches (`Common.py:734-758`).
* Nothing can be computed or tested without matplotlib, and no other
  plotting library can be used.

### No notion of what is drawn

* `draw()` appends new artists on every call and never removes old ones.
  Both `show()` and `savefig()` call `draw()` (`Plots.py:82-88`), so
  saving after showing draws every line twice.
* There is no bookkeeping that maps an isoline to its artist, so a
  partial update is impossible; the only way to change something is to
  clear the axes and redraw everything, including all property
  calculations.
* The figure is created as a bare `matplotlib.figure.Figure`
  (`Common.py:458`) while `show()` calls `plt.show()` (`Common.py:856`),
  which does not know about that figure, so nothing appears.

### Shared mutable state

* `UNIT_SYSTEMS` and `LINE_PROPS` are class attributes holding mutable
  instances (`Common.py:417-430`). Changing `plot.system.P.unit` changes
  it for every plot in the process.
* `set_Tp_limits` mutates the list it is given; `TP_LIMITS` entries are
  shared lists.

### Fragile encodings and magic numbers

* Diagram types are encoded as `y_index * 10 + x_index`
  (`Common.py:49-56`). CoolProp parameter indices have two digits
  (iT=19, iP=20, iHmass=41), so the code is ambiguous in principle and
  only works because no colliding pair is used.
* A T or p limit below 10 is interpreted as a factor, anything above as
  an absolute value (`ID_FACTOR`, `Common.py:432`).

### Isoline calculation chooses poor input pairs

Isolines are computed by stepping along one plot axis
(`IsoLine.XY_SWITCH`). This forces input pairs such as `HmassSmass`
(constant h in a T-s chart) or `HmassT` (constant h in a p-T chart),
which are slow or unsupported for many fluids. Measured with CoolProp
8.0.0 for water, 4 lines of 250 points:

| Diagram, isoline | Legacy approach        | New approach (T or p sweep) |
|------------------|------------------------|-----------------------------|
| T-s, constant h  | 35 s, 37 % points fail | 0.54 s for the whole chart, 0 failures |
| p-T, constant h  | 100 % points fail      | 0 failures                  |

Failed points are then hidden by `sanitize_data`, which interpolates
over them, so the plot shows invented data instead of a gap. Every failed
point also emits its own warning, thousands per chart.

### Smaller defects

* `draw_isolines` computes a new alpha and discards it
  (`Plots.py:174`).
* In `calc_sat_range` the near-critical rescue is immediately overwritten
  with NaN (`Common.py:293-307`); this was fixed in CoolProp (#3409) but
  not here.
* Bare `except:` clauses throughout, which also swallow
  `KeyboardInterrupt`.

### Fork drift

`CoolProp/wrappers/Python/CoolProp/Plots` has moved on since the fork:
it has the #3409 fix and a new `IsoLineTracer` (warm-started Newton
iterations with saturation brackets, robust near the critical point and
for zeotropic blends). CoolPlot is frozen at the 2020 state. Two
diverging copies of the same code is the most important organisational
issue; see the open decisions in section 6.


## 2. The new layers

```
  +-----------------------------------------------------------+
  |  quantities   units   scene   style                       |  plain data
  |  (no CoolProp, no plotting library)                       |
  +-----------------------------------------------------------+
        ^                  ^                       ^
        |                  |                       |
  +-------------+    +-------------+         +-------------+
  |   thermo    |--->|   diagram   |-------->|   render    |
  | CoolProp,   |    | Property-   |  Scene  | base, mpl,  |
  | SI units    |    | Diagram     |         | svg, ...    |
  +-------------+    +-------------+         +-------------+
   only layer that    turns settings          only render.mpl
   imports CoolProp   into a scene            imports matplotlib
```

An arrow means "may import". `tests/test_architecture.py` checks these
rules in fresh interpreters, so a stray import fails the test suite.

| Module | Responsibility |
|--------|----------------|
| `quantities.py` | The quantities CoolPlot can plot (T, p, h, s, rho, u, Q): key, CoolProp name, symbol, label, default log scale. |
| `units.py` | Immutable `Unit` and `UnitSystem` (SI, KSI, EUR, custom). Conversion only. |
| `scene.py` | Backend-neutral drawable items (`Line`, `Markers`, `Text`), styles, `AxesSpec`, and the `Scene` container with value-based change detection. |
| `style.py` | `Theme`: default styles per isoline family, saturation dome, processes. |
| `thermo/fluid.py` | `Fluid` wraps (does not inherit) an `AbstractState`, caches the critical point and fluid limits, provides `model_key` for caching and `clone()` for worker threads. |
| `thermo/diagram_type.py` | `DiagramType`: which quantities are on the axes, which isolines make sense and how to compute them. |
| `thermo/limits.py` | `TpLimits` with explicit `Relative(factor)` bounds instead of the "below 10 means factor" rule; derives axis ranges. |
| `thermo/isolines.py` | Pure functions returning a `Curve` (SI arrays, NaN for failed points), and the `CurveCache`. |
| `thermo/process.py` | `StatePoint`, `state_point()` and `process_path()`. Cycle models go here. |
| `diagram.py` | `PropertyDiagram`: stores user settings in SI, builds the scene from cached calculations. |
| `render/base.py` | `Renderer` base class: diffs the scene against what it drew and calls backend hooks only for changes. |
| `render/mpl.py` | Matplotlib backend; updates artists in place. |
| `render/svg.py` | Dependency-free SVG backend; also the reference for new backends. |

### Principles

* **SI inside, display units at the edges.** Values entering through the
  API are converted to SI at once; the scene is converted to display units
  when it is built. Nothing in between knows about units.
* **Settings are declarative.** Setters only store. `update_scene()`
  describes the complete plot from the current settings. Caching and
  diffing make that cheap; the caller never has to say what changed.
* **Immutable values.** Units, themes, styles, items, curves and state
  points are frozen. A change means a new value, so equality is a reliable
  test for "did this change".
* **Failures are visible.** A point CoolProp cannot compute is NaN and
  shows up as a gap. A line with fewer than two valid points is skipped
  with a single warning.

### Isoline computation

Every isoline holds one quantity constant and steps through temperature or
pressure, whichever is not the constant, over the T-p region of the plot.
Both axis values are read from each state. This uses only the input pairs
PT, HmassP, PSmass and DmassT, which are the fast and reliable ones. Lines
of constant x or y would be straight lines parallel to an axis and are not
offered as isolines (use the grid). Lines of constant quality step through
saturation temperatures, denser towards the critical point, and for pure
fluids end at the critical point so that the dome closes.


## 3. How selective updates work

Two mechanisms work together.

**Calculation cache.** Each curve is stored in a `CurveCache` under a key
holding everything it depends on: fluid model, diagram type, quantity,
value, T-p region and number of points. Rebuilding the scene asks the cache
first, so only curves with new inputs are computed.

**Scene diff.** Each item has a stable id, for example `iso/T/273.15` or
`process/cycle/line`. `Scene.replace_all()` keeps the existing object for
any item that compares equal (arrays by value), and `Renderer.sync()`
compares the scene with what it drew last time. Backends receive only
`_add`, `_update` and `_remove` calls for the items that changed.

What a change costs:

| Change | Property calculations | Items redrawn |
|--------|----------------------|---------------|
| Unit system | none | all coordinates, axes |
| Isoline colour or width | none | that family only |
| Add one isoline value | that line | that line |
| Move a cycle state | none for isolines | the cycle line and markers |
| Zoom or pan (`set_view`) | none | axes only |
| T-p limits, fluid, diagram type | all lines (cache misses) | all |
| Unit system with `rounding=True` | lines whose rounded value changed | those lines |

`tests/test_diagram.py` asserts each of these rows. In the interactive
example, moving a slider updates 2 matplotlib artists and leaves 38
untouched.


## 4. Interactive applications

The pattern is the same for every GUI toolkit or web framework:

```python
diagram = PropertyDiagram("HEOS::R290", "ph", units="EUR", tp_limits="ACHP")
diagram.set_isolines("Q", num=11)
renderer = MatplotlibRenderer(ax=my_embedded_axes, use_pyplot=False)

def on_user_input(...):
    diagram.set_process("cycle", path_states, corner_states)  # or any setter
    renderer.sync(diagram.update_scene())                    # minimal redraw
```

* **Hover readouts:** `diagram.state_at(x, y)` turns a cursor position in
  display units into a full `StatePoint`.
* **Zoom:** `diagram.set_view(...)` changes only the visible window. The
  calculation domain (`tp_limits`) is a separate setting, so zooming never
  recomputes.
* **Several views:** one scene can be synchronised to several renderers,
  for example an on-screen matplotlib canvas and an SVG export. Each
  renderer keeps its own record of what it drew.
* **Web front ends:** item ids are stable, so a server can send only the
  changed items (the `SyncReport` lists them) and a browser can patch an
  SVG or a plotly figure in place.
* **Labels** carry a direction in data coordinates instead of a fixed
  angle; the backend converts it to a screen angle. In matplotlib this uses
  `transform_rotates_text`, so labels stay aligned after zooming and
  resizing.

Not yet done, and the main open item for interactivity: **calculations in
the background.** Pure fluids are fast (a full ph chart of R290 in about
0.2 s), but a zeotropic blend is not: with plain flash calls, one line of
constant entropy for an R32/R125 blend takes about 15 s for 50 points. The
design is prepared for this (pure calculation functions, hashable cache
keys, `Fluid.clone()` for worker threads); what is missing is a small job
API on `PropertyDiagram` that computes cache misses in a worker, possibly
coarse first and refined later, and notifies the UI.


## 5. Writing a new backend

Subclass `CoolPlot.render.base.Renderer` and implement:

| Hook | Called when |
|------|-------------|
| `_set_axes(axes)` | labels, scales or limits changed |
| `_add(item)` | an item appeared |
| `_update(old, new)` | an item changed (default: remove and add) |
| `_remove(item)` | an item disappeared |
| `_finish(report)` | once per sync, e.g. to request a repaint |

Sketches for the obvious next candidates:

* **plotly:** keep a `FigureWidget`; `_add` appends a trace with
  `uid=item.id`, `_update` assigns `trace.x`, `trace.y` and `trace.line`
  inside `fig.batch_update()`, `_remove` filters `fig.data`.
* **bokeh:** one `ColumnDataSource` per item; `_update` assigns
  `source.data`, which bokeh streams to the browser.

No other part of CoolPlot changes when a backend is added.


## 6. Status and next steps

Implemented in this step: all modules in the table of section 2, tests
for each layer, `examples/quickstart.py` and
`examples/interactive_cycle.py`.

Compared with the legacy API, still missing:

* Cycle models (`SimpleCompressionCycle`, `SimpleRankineCycle`) as pure
  `thermo` functions returning `StatePoint`s. The interactive example
  shows the shape of such a function.
* A saturation dome for mixtures built from the phase envelope.
* Label collision avoidance; labels are currently at the middle of the
  visible part of each line.
* Psychrometric charts (`psy.py`, `PsychChart.py`). They would be a second
  `thermo` module and diagram class; `scene` and `render` are reused as
  they are.

Open decisions:

1. **Where the canonical code lives.** Either CoolPlot becomes the home
   of property plots and `CoolProp.Plots` turns into a thin compatibility
   layer that depends on it, or CoolPlot is retired in favour of
   `CoolProp.Plots`. Keeping two diverging copies is the worst option.
2. **Port `IsoLineTracer`** from CoolProp into `thermo/isolines.py` (or
   depend on it). It addresses exactly the slow blend case above.
3. **Background calculation API**, see section 4.
4. **Remove the legacy packages** (`CoolPlot/Plot`, `CoolPlot/Util`,
   `CoolPlot/Calc`, `mains/`, `plots/`) once the points above are done.
   `ConsistencyPlots.py` is a CoolProp development tool and does not
   belong in CoolPlot at all.
5. **Package name.** PEP 8 prefers `coolplot`. A rename is only safe
   after the legacy directories are gone, because `CoolPlot/Plot` and a
   new `plot` module would collide on case-insensitive file systems (the
   same reason the calculation package is called `thermo` and not `calc`).
6. **CI.** Replace Travis with GitHub Actions running `pytest`.
