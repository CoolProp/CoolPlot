# CoolPlot architecture

This document reviews the code CoolPlot inherited from CoolProp 6.3 and
describes the architecture that replaces it. The goals are:

1. Separate property calculations from plotting completely.
2. Make matplotlib one rendering backend among several, with identical
   styling in every backend.
3. Support interactive applications, where a small change (a slider, a
   new isoline, a unit switch) only recomputes and redraws what it
   affects.

Related documents: `docs/styling.md` (themes and styles for users) and
`docs/backends.md` (requirements for new backends).

The new modules live next to the legacy code (`CoolPlot/Plot`,
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
  (`Common.py:47-54`). CoolProp parameter indices have two digits
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
diverging copies of the same code was the most important organisational
issue. Decision (October 2026): CoolPlot stays a separate package and owns
the numerics as well; the tracer is ported, not imported (section 7).


## 2. Decisions

| Decision | Status |
|----------|--------|
| CoolPlot is a separate package and owns everything, including the isoline numerics. `IsoLineTracer` is ported from CoolProp. | decided |
| Styling is a first-class layer: themes resolve to concrete, normalised styles in the scene; every backend must render them identically. | decided, implemented |
| Backends are accepted by passing a mechanical conformance kit. | decided, implemented |
| Rename the import to `coolplot`, remove the legacy packages, release as v1.0. | proposed, open |
| Minimum versions CoolProp 8.0 and Python 3.10. | proposed, open |
| Property calculations run synchronously by default; background execution is opt-in for applications. | proposed, open |


## 3. The pipeline

```
DiagramSpec --plan--> CurveRequests --engine--> Curves --compose--> Scene --layout--> Scene --sync--> backend
(all settings,        (hashable,                (SI, cached)    (display     (labels,          (mpl, svg,
 one value)            cheap to make)                            units,       needs viewport)   plotly, web)
                                                                 styles)
     ^                                                                                              |
     +------------------------- events: zoom, hover, pick, drag <-----------------------------------+
```

Each stage is a plain function of the stage before it. Every stage either
caches its results (curves) or compares them with the previous ones
(scene items), so a change only flows through the parts it affects.

| Stage | Module | Status |
|-------|--------|--------|
| Settings | `diagram.py` (`PropertyDiagram`); an immutable `DiagramSpec` is planned | partly |
| Plan | inside `PropertyDiagram.update_scene` today; a pure `plan(spec)` is planned | partly |
| Engine | `thermo/isolines.py` (`compute_isoline`, `CurveCache`), synchronous | partly |
| Compose | `PropertyDiagram.update_scene`: display units and theme styles | done |
| Layout | label placement inside compose today; a viewport-aware pass is planned | planned |
| Sync | `render/base.py` and the backends | done |
| Events | backend-neutral events back into the diagram | planned |


## 4. Layers and import rules

```
  +---------------------------------------------------------------+
  |  quantities  units  style  theme  scene                       |  plain data
  |  (no CoolProp, no plotting library)                           |
  +---------------------------------------------------------------+
        ^                     ^                         ^
  +-------------+       +-------------+           +---------------+
  |   thermo    |       |   diagram   |           |    render     |
  | CoolProp,   |       | settings -> |           | base, svg,    |
  | SI units    |       | scene       |           | mpl, testing  |
  +-------------+       +-------------+           +---------------+
        ^                     |                         ^
        +---------------------+  diagram uses thermo    |
                                 and hands scenes to ---+
```

| Module | May import | Must not import |
|--------|------------|-----------------|
| `quantities`, `units` | numpy | CoolProp, matplotlib, thermo, diagram, scene, render |
| `style`, `theme` | numpy, quantities | CoolProp, matplotlib, thermo, diagram, scene, render |
| `scene` | numpy, style | CoolProp, matplotlib, thermo, diagram, theme, render |
| `thermo` | CoolProp, numpy, quantities, units | matplotlib, scene, style, theme, diagram, render |
| `diagram` | everything above | matplotlib, render (one documented exception: `draw()` creates a MatplotlibRenderer for scripts) |
| `render.base`, `render.svg`, `render.testing` | scene, style | CoolProp, matplotlib, thermo, diagram, theme |
| `render.mpl` | matplotlib, scene, style | CoolProp, thermo, diagram, theme |

`tests/test_architecture.py` checks these rules by reading every import
statically, including imports inside functions, and confirms at run time
that building and drawing a scene with the SVG backend never loads
matplotlib.

Backends never see themes: the diagram resolves the theme into concrete
styles on every item, so a backend cannot apply its own idea of a
default, and all backends look the same.


## 5. Styling

Summary of `docs/styling.md`:

* Style values (`LineStyle`, `MarkerStyle`, `Font`, `TextStyle`,
  `AxesStyle`, `LegendStyle`) are immutable and normalised when created:
  colours to `#rrggbb` plus alpha, all lengths in points, dashes resolved
  by one function (`dash_pattern_pt`) that every backend uses.
* A `Theme` maps element kinds to styles. Presets: `default`, `dark`,
  `print`, `classic`. Themes serialise to JSON.
* Isoline colours are assigned per diagram type from three hues that stay
  distinguishable in every pairing, also for colour vision deficiencies;
  the assignment depends on what a diagram offers, so hiding a family
  never repaints the others. The saturation dome and cycles use ink,
  weight and casing, not a fourth hue.
* Scene items carry a semantic `role` and a legend text; items sharing a
  legend text form one composite legend entry.
* Changing the theme restyles items only; no property is recalculated.


## 6. Backends and the conformance kit

Summary of `docs/backends.md`:

* A backend subclasses `Renderer` and implements hooks for axes, add,
  update, remove, reorder, legend and finish. The base class does the
  diffing; a backend never rebuilds the whole plot.
* Every backend implements read-back (`describe_item`, `describe_axes`)
  that reports what it actually drew, from its own objects.
* `CoolPlot.render.testing.run_conformance` draws a reference scene using
  every style feature and awkward data, reads it back, then changes it
  step by step (restyle, hide, restack, reorder, remove, new axes, legend,
  clear) and checks both the result and that only affected items were
  touched. For file backends it also checks deterministic, ASCII output.
* The SVG and matplotlib backends pass the kit. Planted bugs (dropped
  dashes, missing halos, no restacking, wrong marker shape) are caught.

What a change costs today:

| Change | Property calculations | Items redrawn |
|--------|----------------------|---------------|
| Unit system | none | all coordinates, axes |
| Theme | none | every item whose resolved style differs, axes |
| One isoline family's style | none | that family |
| Add one isoline value | that line | that line |
| Move a cycle state | none | the cycle line and markers |
| Zoom (`set_view`) | none | axes, and labels (their position depends on the view) |
| T-p limits, fluid, diagram type | all lines | all |

`tests/test_diagram.py` and `tests/test_style.py` assert the rows for
units, styles, one added line, cycles, zoom and themes.


## 7. Plan

Work is split into phases, each a separate commit with tests.

| Phase | Content | Status |
|-------|---------|--------|
| 0 | Layered skeleton: units, scene, renderer diffing, first thermo layer | done |
| 1 | Styling and backends: style model, themes, backend guide, conformance kit, SVG and matplotlib to spec | done |
| 2 | Fluid and diagram as data: `FluidSpec` (backend, components, fractions, interaction parameters), immutable `DiagramSpec`, pure `plan()` | next |
| 3 | Numerics: port `IsoLineTracer`, isolines built from phase segments with the saturation states inserted, mixture dome from the phase envelope, per-curve diagnostics | |
| 4 | Engine: background execution (threads or processes), cancellation, coarse-then-fine, keep old lines until new ones arrive, optional disk cache | |
| 5 | Viewport, layout and events: renderers report their size and visible window; label placement with collision avoidance; neutral events (zoom, hover, pick, drag) | |
| 6 | More backends: plotly `FigureWidget`, JSON deltas for web clients | |
| 7 | Cycles as pure models, packaging (`src` layout, `pyproject.toml`, CI), removal of the legacy code | |

Findings from the review of phase 0 that are still open, by phase:

* Phase 2: cached curves can go stale when a caller changes a passed-in
  `AbstractState` (fractions, interaction parameters), because the cache
  key does not capture them; fractions given for a single fluid string
  (`INCOMP::MEG[0.3]`) are dropped.
* Phase 3: lines of constant T or p cut diagonally across the two-phase
  region, because no saturation states are inserted; the dome of tabular
  backends closes with a kink.
* Phase 2: item ids are built from values with 12 significant digits and
  can collide; `nice_values` can space rounded isolines unevenly.
* Phase 3: a line that fails warns again on every `update_scene`; this
  becomes per-curve diagnostics.

Calculation speed today: pure fluids are fast (a full ph chart of R290 in
about 0.2 s). Zeotropic blends are not: one line of constant entropy for
an R32/R125 blend takes about 15 s for 50 points with plain flash calls,
which phases 3 and 4 address.
