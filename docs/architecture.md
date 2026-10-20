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

The legacy code (`CoolPlot/Plot`, `CoolPlot/Util`) was released one last
time as 0.1.7 and removed from the 0.2 code base; file references in
section 1 point into that release.


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
the numerics as well; the tracer is ported, not imported (section 10).


## 2. Decisions

| Decision | Status |
|----------|--------|
| CoolPlot is a separate package and owns everything, including the isoline numerics. `IsoLineTracer` is ported from CoolProp. | decided |
| Styling is a first-class layer: themes resolve to concrete, normalised styles in the scene; every backend must render them identically. | decided, implemented |
| Backends are accepted by passing a mechanical conformance kit. | decided, implemented |
| The legacy API gets one last release, 0.1.7 (works with CoolProp 6, 7 and 8 and NumPy 2), from a separate branch off master. | done, waiting for merge and upload |
| 0.2 replaces the legacy API: the import becomes `coolplot`, `CoolPlot.Plot` and `CoolPlot.Util` are removed. Users of the old API stay on 0.1.7. | decided |
| The package is restructured into layers with one responsibility each (section 4); the facade `PropertyDiagram` only delegates. | decided |
| One `Settings` value bundles calculation detail, styling, label placement and page hints (section 5). | decided |
| CoolPlot decides what makes a chart recognisable and correct (colours, styles, all texts, label placement); each backend keeps its own defaults for page geometry and tick positions (section 6). | decided |
| Minimum versions: Python 3.10; CoolProp 6.8, 7.x and 8.x, all tested in CI. | decided |
| Property calculations run in the foreground in 0.2; background execution follows in 0.3. | decided |
| 0.2 has a simple interface to overlay cycles on diagrams, including split and two-stage cycles, and cycle models that produce the same objects (section 7). | decided; interface proposed |


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
| Settings | `spec/` (`DiagramSpec`, `Settings`), held by `PropertyDiagram` in `diagram.py` | done |
| Plan | `engine/plan.py` (`plan(spec, domain)`), pure | done |
| Engine | `engine/engine.py` (`Engine`), `engine/background.py` (`BackgroundEngine`, 0.3), `engine/cache.py` (`CurveCache`), `thermo/` for the calculations | done |
| Compose | `compose/builder.py`: display units, theme styles, texts | done |
| Layout | `compose/layout.py`: labels for the reported plot size, keep-out zones | done |
| Sync | `render/base.py` and the backends | done |
| Events | `core/events.py`, `Renderer.connect`, `interaction.py` | done |


## 4. Package layout for 0.2

Before this step the layering existed in the new modules, but the package
as a whole had not been reworked: `diagram.py` stored settings, generated
isoline values, built cache keys, called the calculations, applied units
and styles, placed labels and opened matplotlib windows; the curve cache
lived in `thermo`; the legacy code and old tooling were still in the tree
(they are gone now, see the status below). 0.2 restructures the package explicitly, one responsibility per layer, listed
in dependency order:

```
src/coolplot/
  core/      quantities, units                      plain data, no CoolProp, no plotting
  style/     style values, themes
  scene.py                                          the contract to the backends
  spec/      FluidSpec, DiagramSpec, Settings       what the user asks for, as data
  thermo/    states, saturation, isolines, cycles   the only place that talks to CoolProp
  engine/    plan, cache                            which curves are needed; compute and cache them
  compose/   scene building, label layout           SI curves + spec + settings -> scene
  render/    base, testing, svg, mpl                paint the scene; may use only core, style, scene
  diagram.py                                        PropertyDiagram: thin facade for users
```

Each layer may only use the layers listed before it (the backends only
`core`, `style` and `scene`); `tests/test_architecture.py` enforces this
statically, including imports inside functions. The facade holds a
`DiagramSpec`, asks the engine for curves and hands the composed scene to
renderers; it contains no calculation, styling or layout logic of its own.

### Status of the move

Step 1 moved the modules into `core`, `style`, `scene`, `thermo`,
`engine` and `render`, and removed the legacy code and old tooling.
Step 2 added `spec` (`FluidSpec`, `DiagramSpec`, `Settings`) and
`compose`, and moved the plain data (`DiagramType`, `StatePoint`,
`TpLimits`) into `core`. The facade now only holds a `DiagramSpec`:

```
update_scene():
    domain = engine.domain(spec)                  # T-p box and quantity ranges, cached
    curves = engine.curves(spec, domain, plan(spec, domain))
    items, axes = compose(spec, domain, curves)   # units, styles, texts, labels
    scene.replace_all(items, axes)                # renderers redraw only what changed
```

`plan()` is pure: it lists the isolines with snapped values (12
significant digits, so -20 deg C and 253.15 K are the same line and the
same id) and, with `rounding=True`, round values in display units with an
even step (1, 2, 2.5 or 5 times a power of ten on linear axes, mantissas
1-2-5 and finer on log axes). A Fluid built from an `AbstractState` is a
snapshot of its fluid, fractions and interaction parameters, so later
changes to the user's state cannot leave stale curves in the cache; the
INCOMP backend takes mass fractions by default.

Step 3 added the numerics in `thermo`: `tracer.py` (the `IsoLineTracer`
ported from CoolProp 8), saturation states inserted where an isoline
meets the dome, the bubble and dew lines of mixtures from the phase
envelope, and diagnostics on every `Curve` (`n_failed`, `n_gaps`,
`n_fallback`, `n_inserted`, `method`). Package 0.7 of the 1.0 plan
replaced the fixed grid of points by adaptive stepping, see section 11.

Step 4 added `compose/layout.py`, the label layout (section 6): edge
labels just inside the frame where the lines leave the plot, keep-out
zones of `Settings.labels.keep_out_pt` around every process, one pass in
order of importance, earlier positions kept while they stay free (the
scene then sees the same item and nothing is redrawn), optional fallback
positions along the line, margin labels outside the frame, and the old
inline labels. Renderers report `plot_size_pt()`; `PropertyDiagram.draw`
re-runs the layout once if the plot area changed when the scene was
drawn. Tick label texts follow `coolplot.core.numbers.format_number`
in every backend; `Text` gained `offset_pt` and `clip` for margin labels.

Step 5 added cycles (section 7): `core/cycle.py` (`StateInput`,
`Cycle`), `CycleSpec` in the spec, `thermo/cycles/` (state resolution,
paths, models) and the engine cache for cycles; compose draws them.

Backends never see themes: the scene carries concrete styles on every
item, so a backend cannot apply its own idea of a default.


## 5. Settings

All tunable values live in one immutable `Settings` value, part of the
`DiagramSpec`, saved and loaded as JSON like themes. It is split by what a
change costs, because that decides what is recomputed:

| Part | Contents | A change costs |
|------|----------|----------------|
| `calc` | points per isoline, points and spacing on the saturation line, distance kept from the triple and critical point, solver (tracer or plain flash), failure tolerance | recalculation of the affected curves; part of the cache key |
| `look` | the theme: every colour, line, marker and font | restyling only |
| `labels` | mode (edge, margin, inline), keep-out margin around processes, density, number format and rounding of all values shown | new label layout only |
| `page` | hints for the backends: preferred canvas size, font scale (the legend position is part of the theme) | backend layout only |

Defaults come from presets (`screen`, `print`, `publication`,
`interactive`). An application that wants few points while the user drags
switches only the calculation part, `settings.with_(calc="interactive")`,
and back with `settings.with_(calc="screen")`; assigning a whole preset
would also replace the theme, labels and page. The number of points can
be overridden per isoline family.

Implemented in step 2 (`coolplot.spec.settings`):

* `calc`: `points`, `saturation_points`, `saturation_spacing`
  ("critical" or "linear"), `solver` ("auto", "tracer" or "flash", step
  3), `critical_margin` (1e-7 of the critical values) and
  `warn_failed_fraction` (warn once per curve with more failed points
  inside the line than this).
* `look`: a `Theme`.
* `labels`: `mode` ("edge", "margin" or "inline"), `keep_out_pt`,
  preferred `edges` per family, `margin_edges`, `fallback`, `every`
  (label every n-th line), `position` (inline mode), `digits` of the
  values shown, `show_units` and `tick_digits` (step 4).
* `page`: `width_pt`, `height_pt` (used when the diagram creates its own
  renderer) and `font_scale`, which compose applies to every font of the
  theme.

## 6. What is central and what backends decide

Charts do not have to be pixel-identical across plotting libraries. They
have to carry the same information in the same visual language, and each
library may lay out the page in its own idiomatic way.

| Decided centrally, every backend must follow | Left to the backend's defaults |
|----------------------------------------------|--------------------------------|
| colours, line widths, dashes, casings, markers, fonts (family, size, weight, style) | canvas size and plot-area margins (the `page` settings are hints) |
| every text: axis labels with units, title, legend entries, isoline label texts | tick positions and minor ticks |
| the number format of every value shown, including tick labels | exact text rendering and font fallback |
| position and angle of isoline labels, keep-out zones around processes | exact geometry of the legend box (corner or outside is central) |
| what is drawn, drawing order, visibility, axis scales and limits, grid on or off | interactive behaviour of the library (toolbars, zoom gestures) |

Label placement needs the size of the plot area, which only the backend
knows. Renderers report it (`plot_size_pt`); the layout uses the `page`
hint before the first draw and is re-run, without any property
calculation, when the reported size differs. The conformance kit checks
everything in the left column and nothing in the right one; for tick
labels it checks that the texts follow the central number format, not
where the ticks are.

## 7. Cycles on diagrams

Overlaying a cycle on a diagram has to take a few lines, whether the
states come from CoolPlot's own cycle models, from the user's own
calculation or from measurements.

### The interface (implemented in step 5)

```python
diagram.add_cycle("Heat pump", [
    {"p": 3.0, "T": 0.0},                                     # 1 compressor inlet, diagram units
    {"p": 15.0, "via": "compression", "eta_is": 0.7},         # 2 compressor outlet
    {"p": 15.0, "Q": 0.0},                                    # 3 condenser outlet
    {"p": 3.0, "via": "isenthalpic"},                         # 4 after the valve
])
diagram.add_cycle(simple_compression("R290", T_evap_C=-5, T_cond_C=45))   # from a model
diagram.add_cycle("measured", p=[...], h=[...])                           # from arrays
```

* States are given by any two properties in the diagram's units (or
  another unit system with `units=`), by `StatePoint` objects, or as
  arrays. A state given with `via` takes its missing property from the
  state before it in the cycle: "isenthalpic", "isentropic", "isobaric",
  "isothermal", "isochoric", or "compression" and "expansion" with an
  isentropic efficiency `eta_is` (the outlet pressure is the given
  property). The proposal used "polytropic" here; a pressure alone does
  not fix a compressor outlet, so "polytropic" is a path shape only.
* Paths between states follow the physics ("auto"): equal pressure gives
  an isobar (with the saturation states inserted, so heat exchangers bend
  exactly on the dome), equal enthalpy an isenthalp, equal entropy an
  isentrope, equal temperature an isotherm, anything else a polytropic
  path (linear in log p and s). Each connection can be set explicitly
  with `paths={(from, to): kind}`, including "straight".
* The cycle gets theme styles, markers, state numbers (shown by default,
  `numbers=False` hides them, moved around their marker so they do not
  cover each other), one legend entry and a keep-out zone for isoline
  labels. Several cycles get different styles. Without a zoom window the
  axes grow so that every state is inside the frame.
* Calling `add_cycle` again with the same name replaces that cycle; only
  it is recalculated and redrawn. Errors (a state CoolProp cannot
  compute, a chain referring to an unknown state) are raised by
  `add_cycle`, not at the next draw. `cycle_states(name)` returns the
  computed states.
* Values are stored in SI units in a `CycleSpec` inside the
  `DiagramSpec`, so a cycle survives unit changes and JSON round trips;
  the engine computes states and paths once per fluid and cycle.

### Split and two-stage cycles

A cycle is a set of numbered states plus routes, given as chains of state
numbers. Without `loops`, the states in order form one closed cycle.

```python
diagram.add_cycle("Two-stage, flash tank", states={
        1: {"p": 1.5, "T": -30.0}, 2: {"p": 5.0, "via": "compression", "eta_is": 0.7},
        3: {"p": 5.0, "Q": 1.0},   4: {"p": 18.0, "via": "compression", "eta_is": 0.7},
        5: {"p": 18.0, "Q": 0.0},  6: {"p": 5.0, "via": "isenthalpic"},
        7: {"p": 5.0, "Q": 0.0},   8: {"p": 1.5, "via": "isenthalpic"}},
    loops=[[1, 2, 3, 4, 5, 6, 7, 8, 1]])        # one split cycle
    # loops=[[1, 2, 7, 8, 1], [3, 4, 5, 6, 3]]  # or two closed cycles
```

* Each chain is one connected line; chains may share states, which
  covers split cycles, two overlapping closed loops and injection branches
  (economizer, vapour injection). A mixing point is an ordinary state.
* Each state number is drawn once, however many chains pass through it.
  Branches share the cycle's style unless restyled per chain.
* In the scene a cycle is one group: one line item per chain, one marker
  item, one text item per state number, so moving one state redraws only
  that cycle.

### Cycle models

Models live in `thermo/cycles/` and return the same `Cycle` object that
`add_cycle` accepts, with states, loops and results (COP, specific heat
flows and work per kg through the evaporator, and the flow ratio between
the stages, `m_dot_ratio`). For blends the evaporating and condensing
temperatures are dew points (EN 12900):

* simple vapour compression (`T_evap_C`, `T_cond_C`, `dT_sh_K`,
  `dT_sc_K`, `eta_is`);
* two-stage compression with `intermediate="flash_tank"` or
  `"economizer"`, intermediate pressure by default the geometric mean of
  evaporating and condensing pressure (the legacy `TwoStage` and
  `EconomizedCycle` functions are the starting point);
* simple Rankine cycle.

A cascade with two different fluids cannot share one diagram, because a
property diagram belongs to one fluid. A cascade model returns one cycle
per stage, each overlaid on the diagram of its fluid (for example two
panels side by side). A cascade with one fluid is two closed loops on one
diagram.

## 8. Styling

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


## 9. Backends and the conformance kit

Summary of `docs/backends.md`:

* A backend subclasses `Renderer` and implements hooks for axes, add,
  update, remove, reorder, legend and finish. The base class does the
  diffing; a backend never rebuilds the whole plot.
* Every backend implements read-back (`describe_item`, `describe_axes`)
  that reports what it actually drew, from its own objects.
* `coolplot.testing.run_conformance` (the package `coolplot.testing` holds
  the kit and the PDF reader; nothing a chart draws with imports it) draws a reference scene using
  every style feature and awkward data, reads it back, then changes it
  step by step (restyle, hide, restack, reorder, remove, new axes, legend,
  clear) and checks both the result and that only affected items were
  touched. For file backends it also checks deterministic, ASCII output.
* The SVG and matplotlib backends pass the kit. Read-back comes from the
  drawn geometry where the library exposes it: drawn positions as
  fractions of the plot area, marker size and shape from the drawn shape,
  text angle checked against the plot size in points, legend position
  from its bounding box. That makes it hard, not impossible, to pass by
  echoing the scene: a backend that reports the scene's drawing order
  instead of its own, for example, would still pass the order check.
  The kit is a strong safety net, not a proof.
* `tests/test_backend_conformance.py` plants 51 defects one at a time
  (casing without dash or alpha, grid above the items or on one axis
  only, ignored fonts, tick sizes or tick label format, legend in the
  wrong place, without samples or with the wrong text colour, text angle
  in data space or upside down, hidden items in autoscale, markers of the
  wrong size or shape or joined by a line, data drawn in the wrong place,
  items above the frame, ...) and checks that the kit catches each.

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


## 10. Plan

### 0.2: replace the legacy API

| Step | Content | Status |
|------|---------|--------|
| - | Layered skeleton, styling layer, backend guide, conformance kit, SVG and matplotlib backends | done |
| - | Legacy release 0.1.7 | done, waiting for merge and upload |
| 1 | Restructure into the package layout of section 4 (`src/coolplot`, `pyproject.toml`), remove the legacy code, CI on GitHub Actions with CoolProp 6.8, 7.x and 8.x | done |
| 2 | Specs and settings: `FluidSpec` (backend, components, fractions, interaction parameters), `DiagramSpec`, `Settings` with presets, pure `plan()`, scene building moved from the facade into `compose` | done |
| 3 | Numerics: port `IsoLineTracer`, isolines built from phase segments with the saturation states inserted, mixture dome from the phase envelope, per-curve diagnostics | done |
| 4 | Label layout: edge labels with keep-out zones around processes, margin labels as an option, stable placement while dragging; central number formats | done |
| 5 | Cycles on diagrams (section 7): `add_cycle` with states, `via`, automatic paths, loops for split and two-stage cycles, state numbers; models for simple compression, two-stage (flash tank, economizer) and Rankine | done |
| 6 | Close the findings of the second review of the conformance kit (drawn positions, honest read-back of caps, marker shapes and connecting lines, strict theme loading, XML sanitising); examples and user documentation | done |

### 0.3: background, events, more backends, psychrometric charts

| Step | Content | Status |
|------|---------|--------|
| 1 | Background calculation: curves computed in worker threads or processes, coarse first and then fine, outdated work cancelled; the diagram stays responsive and reports progress | done |
| 2 | Events back from the backends (hover, click, drag, view changes, resize) as plain data; an `Interaction` helper that turns them into diagram changes (zoom and pan re-layout labels, hover reads the state, dragging a cycle state moves it) | done |
| 3 | plotly backend, passing the conformance kit, with documented limitations where plotly cannot follow a requirement | done |
| 4 | Web backend: the SVG elements of the SVG backend streamed as patches to a small JavaScript client, events back from the browser, a dependency-free development server; conformance checked in a real browser (headless Chromium) | done |
| 5 | Psychrometric charts for humid air (CoolProp HAPropsSI): dry-bulb temperature over humidity ratio, lines of relative humidity, wet-bulb temperature, enthalpy and specific volume, air processes on top | done |
| 6 | Examples, user documentation, adversarial review of the 0.3 work | done |
| 7 | PDF as a first-class output: TrueType fonts, texts stay text, theme colours, title, reproducible files, several charts per file, a PDF check in the kit | done |

#### Background calculation (step 1)

* `PropertyDiagram(..., background="threads" | "processes" | None)`.
  `update_scene()` never waits for a curve: it returns the scene from the
  curves that are ready and queues the missing ones. When queued work
  finishes, `on_ready(diagram)` is called (from a worker thread; GUI
  applications pass it on to their event loop) and the application calls
  `update_scene()` again.
* Coarse then fine: a missing curve is first computed with
  `Settings.calc.preview_points` and then with full resolution; the
  preview is drawn in the meantime and replaced in place (same item id).
* Every `update_scene()` starts a new generation. Queued work that the
  latest plan no longer needs is cancelled; work already running finishes
  and stays in the cache.
* Threads share the process; each worker uses its own copy of the fluid
  (CoolProp states are not thread safe). CoolProp keeps the interpreter
  lock during every call, so there is one worker thread by default:
  more threads cannot compute in parallel and only slow down the
  application. For blends, whose calls are long, use processes. Processes compute in parallel;
  workers receive only plain data (`FluidSpec`, request, region,
  calculation settings) and return `Curve` values.
* `diagram.progress` gives (ready, total) for the current plan.

#### Psychrometric charts (step 5)

Humid air goes through the same pipeline as a fluid (since 0.4): the
spec is a `DiagramSpec` with a `HumidAirSpec` as fluid, the diagram type
`WT` and a `Region` of T and W bounds; the engine builds a `HumidAir`
property provider (`thermo/humid_air.py`: states and lines with
HAPropsSI; lines are cut at saturation, where fog would begin, and start
exactly on it) instead of a `Fluid`; `compose` styles the lines by their
family (`core/diagram_type.py`); air processes are cycles with straight
paths. `psychrometric.py` only holds the constructor and the air
constructor over `Chart`. Lines are cached
like every other curve, by provider fingerprint, region, family, value
and point count. docs/contracts.md describes the records.

Lines are sampled in dry-bulb temperature. Wet-bulb lines are found
with a regula falsi search on HAPropsSI(Twb; T, W), which is fast and
smooth, because asking HAPropsSI for W from Twb directly is slow (it
iterates inside) and has gaps near 0 deg C in CoolProp 8. Falling lines
(Twb, h, v) end exactly at W = 0; above the boiling point at the chart
pressure there is no saturation limit, and lines of relative humidity
end where the vapour would exceed the total pressure. Near 0 deg C
HAPropsSI switches between an ice and a water wet bulb, so wet-bulb
lines just above 0 deg C all end at the same dry-air temperature. The
view (`set_view`, used by `Interaction` for zoom and pan) only changes
the axes; lines are computed over the full temperature range once.

#### Events (step 2)

Events are plain data in display units, defined in `core/events.py`, so
an application handles them the same way for every backend: `Hover(x,
y)`, `Click(x, y, item_id)`, `DragStart`/`Drag`/`DragEnd(item_id, index,
x, y)`, `ViewChanged(x_limits, y_limits)`, `Resized(width_pt,
height_pt)`. Backends that can produce them declare the capability
"events" and deliver them to callbacks registered with
`renderer.connect(callback)`. `coolplot.interaction.Interaction(diagram,
renderer)` handles the common cases; dragging a state of a cycle replaces
that state by the two axis properties at the new position.
### Open findings from the reviews

* Fixed in step 2: stale curves after a caller changed a passed-in
  `AbstractState` (the Fluid is now a snapshot), dropped fractions for
  `INCOMP::MEG[0.3]`, colliding item ids, unevenly spaced rounded values,
  and a failing line warning again on every update (now once per curve).
* Fixed in step 3: lines of constant T or p cutting diagonally across the
  two-phase region (saturation states are now inserted where any isoline
  meets the dome), the kink at the top of the dome of tabular backends
  (the dome is drawn with the underlying equation of state), and the
  polygonal dome of mixtures (it comes from the refined phase envelope).
* Fixed in step 6: the findings of the second review of the conformance kit (drawn positions, honest read-back of caps, marker shapes and connecting lines, strict theme loading, XML sanitising, vertical text, stacking, wrongly rejected valid axes).

* Fixed in 0.3 step 6, from the adversarial review of the 0.3 work: the
  web development server (snapshot race, Host and Origin checks, input
  limits and validation, bounded queues, stop without start), web zoom
  and pan on log axes, plotly quotes and honest axis read-back, the
  background engine (close, failures retried then reported, one engine
  per diagram, on_ready threading, LRU order), matplotlib pointer events
  (finite coordinates, left-button drags, lost releases, one ViewChanged
  per zoom), and psychrometric lines (above boiling, the CoolProp 8 gap
  in wet-bulb lines, exact W = 0 ends, bounded default line counts,
  failure warnings, pressure and temperature checks, zoom and dragging).
  A second review of these fixes found more, also fixed: a crashing
  worker process made every line in flight count a failed attempt (jobs
  lost with a crashed pool now run again each in a process of its own),
  charts with a foggy edge lost default lines, wait() could still return
  while a plan was being worked out, on_ready ran after close(), a sync
  before the repaint swallowed a matplotlib zoom, dropped browsers waited
  30 s to reconnect, huge JSON numbers raised OverflowError, -100 deg C
  was refused by rounding, and a garbage collected diagram kept its
  background engine claimed.

#### PDF output (0.3 step 7)

PDF is a checked capability ("pdf_output"). The matplotlib backend embeds
TrueType fonts, falls back to the next TrueType family for fonts it can
only find as CFF OpenType (embedding those as TrueType gives damaged
files), writes the chart title and no dates, and draws text halos as a
second text artist so labels stay text. `export.save_pdf` puts several
charts into one file. `testing/pdf_reader.py` reads PDF files back without
external tools, for the conformance kit (fonts, texts, painted colours,
title, reproducibility), and rewrites document information for the plotly
backend, which prints through kaleido and Chrome.

Known limits of PDF output, from its adversarial review: the reader is
meant for files of plotting libraries, not for every PDF (it refuses
object streams, encryption and unreadable content, and reports images,
shadings, patterns and other colour spaces as unchecked); `replace_info`
keeps only the catalogue and the information in the trailer and refuses
objects of other generations than 0; EPS and PS written to a file object
(not a file name) keep matplotlib's date line; fonts that only supply
single missing characters are not listed by `fonts_used`.

Known trade-offs, from the adversarial review of the 0.3 work:

* Conformance limitations are declared by the backend itself. With
  `text_order`, ranks are compared among texts and among other items
  separately, so the kit does not check that texts are drawn above lines.
* Process workers are started with the platform default (fork on Linux
  before Python 3.14); forking a GUI application that already runs other
  threads can deadlock. Start the diagram first.
* Every pan step in `Interaction` redraws the scene with a new label
  layout; there is no throttling.
* The development server of `examples/web_app` bound to a public address
  has no authentication, and patch listeners run while the renderer is
  locked.
* Input in the wrong unit (W in kg/kg on an "engineering" chart, a wet-bulb
  temperature in K) is only caught when it is far outside what HAPropsSI
  covers.

Known trade-offs, from the adversarial review of the 0.2 work:

* Global CoolProp settings are not part of the `FluidSpec`. Curve cache
  keys carry the fluid's fingerprint (CoolProp version, configuration,
  reference state), and a changed `set_config_*` makes the engine build the
  fluid, its domains and its cycles again. After `set_reference_state` or
  `set_mixture_binary_pair_data`, call `diagram.refresh()`. The path of a
  REFPROP library is not part of the fingerprint.
* `CLOSED_ENVELOPE_MARGIN` (0.5 %) is safe on the 104 predefined blends
  with a closed envelope (envelope maximum within about 0.3 K of the
  critical point, no two-phase state found above it). A user blend whose
  envelope stops early but still counts as closed (densities up to 35 %
  apart) could have points just above the margin accepted unchecked.
* The flash tank model assumes that vapour and liquid leaving the tank
  have the circulating composition; for strongly zeotropic blends that
  is an approximation.
* Isoline labels and state numbers are not tested against each other
  (the keep-out zone usually separates them), and inline labels have no
  overlap or keep-out checks at all; edge mode is the default.

Calculation speed after step 3: pure fluids are fast (a full ph chart of
R290 in about 0.1 s). For zeotropic blends the isolines are traced
(`Settings.calc.solver`, "auto" traces mixtures on CoolProp 8 and later):
one line of constant entropy for an R32/R125 blend takes about 1 s
instead of 15 to 20 s, and a full default ph chart about 14 s instead of
several minutes. What remains are near-critical points the tracer hands
back to a plain flash, at up to 2 s each; the 0.3 background engine
addresses that. Before CoolProp 8 the tracer is switched off, because
some of its saturation calls abort the Python process there.


## 11. Numerics (0.7)

How one isoline is computed, in `thermo/isolines.py`,
`thermo/stepping.py` and `thermo/tracer.py`. Nothing here knows about
units, styles or plotting libraries; the result is a `Curve` in SI units
(docs/contracts.md, section 2).

**Stepping.** A line of constant property is parametrised by the
quantity that is stepped along it (temperature or pressure, chosen per
family in `core/diagram_type.py`), mapped to a parameter u in 0..1,
logarithmically for pressure. `stepping.trace` walks u from one end to
the other with steps chosen from the shape of the line in *normalised
plot coordinates* (each axis range mapped to 0..1, the logarithm taken
for log axes): a step is accepted when the drawn segment is shorter than
`STEP_FACTOR / points` and turns by less than `MAX_ANGLE_DEG` against
the segment before; otherwise it is halved and tried again. The next
step is aimed at four fifths of those limits, so that a rejected step
(which costs an evaluation) is rare. A straight line across the chart
gets about `points / 2` points, a bend as many as its curvature
needs. The axis ranges come from the engine's `Domain` (the ranges of
the axis quantities over the T-p box), so the same line is stepped the
same way in every unit system and the curve cache stays valid.

**The domain.** A point outside the area the axes show is never drawn,
so it is not computed either, except to locate where the line leaves or
enters that area: the exit point is found by bisection (to 1e-3 of the
parameter range) and the line continues outside in doubling steps only
to see whether it comes back. `Curve.n_outside` counts those points;
the sweeps in `tests/numerics` check that they stay below a tenth of
the evaluations. A line that touches the area at one point only (a
value at the very edge of a range, which the default line values
produce) is left out silently, with `Curve.reason` saying so.

**Points.** A pure fluid is flashed: CoolProp's flashes of pure fluids
are fast and reliable, and the inverse flash confirms every point to
about 1e-9. A mixture is traced (`tracer.IsoLineTracer`): each
single-phase point is a two-by-two Newton iteration in (T, rho) started
from the previous point, each two-phase point a one-dimensional solve
for the vapour quality between the saturation states at its temperature
or pressure. The 0.7 changes to the tracer are a secant iteration for
the quality that starts from the previous point's quality and settles
in two or three saturation calls (a regula falsi over the whole dome is
kept for the first point and as the fallback), solving densities on the
specific volume (which is nearly linear in the quality), and judging a
root near the critical point, where the saturation solver stops
answering, by the densities of the phase envelope at its temperature:
a root well outside them cannot be in the dome and is accepted, the
rest is handed to a flash as before. Those three changes took the
default R410A p-h chart from 23 s to 5 s; a cold h,p flash of a blend
costs up to 0.5 s, so every avoided fallback counts.

**The phase boundary.** An isotherm or isobar meets the dome at one
temperature or pressure: its single-phase parts are stepped up to the
bubble and dew states (known exactly, from the saturation solver or,
near the critical point of a mixture, interpolated on the phase
envelope), and the part between them is stepped in vapour quality with
the same stepping rule, which draws the temperature glide of a blend
and the exact tie line of a pure fluid. Every other line crosses the
boundary where the phase of its points changes; the saturation state
there is found on the saturation curve (pure fluids, a regula falsi
along it) or interpolated on the phase envelope (mixtures) and inserted,
so the kink sits on the dome. A step that crosses the boundary is
accepted whatever its turn: the kink is real.

**Quality lines.** Pure fluids: saturation states on a temperature grid
that is denser towards the critical point, which is appended. Mixtures:
the bubble and dew lines are the two branches of CoolProp's phase
envelope (about 300 points, through the critical region); a line of
intermediate quality is stepped in temperature up to the top of a
closed envelope (the critical point, appended as its last point), and
the saturation solver's occasional failures in the last kelvins are
left out rather than left as gaps.

**Acceptance (docs/v1_plan.md, 0.7)**, measured on this machine: every
pure-fluid line of R290 and CO2 round-trips through CoolProp's inverse
flash to 1e-8 and every traced point of R410A and R32/R125 is confirmed
by an independent p,T or p,Q flash to 1e-6 (`tests/numerics`); no line
spends more than a tenth of its evaluations outside the axes; the
default R410A p-h chart draws in 5 s; the 5 bar isobar of R407C in a
T-s chart has 44 points inside the dome.
