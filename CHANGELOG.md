Changelog
=========

0.6.0 (unreleased)
------------------

Scope and shape (docs/v1_plan.md, package 0.6):

* `coolplot.testing` holds the conformance kit (`coolplot.testing.kit`,
  before `coolplot.render.testing`) and the PDF reader
  (`coolplot.testing.pdf_reader`, before `coolplot.render.pdf_reader`).
  No backend imports it when a chart is drawn; the plotly backend loads
  the PDF reader only while it writes a PDF.
* The development web server moved to `examples/web_app/server.py`
  (`examples/web_app/app.py` runs it); `WebRenderer` stays in
  `coolplot.render.web`. An application connects the renderer to its own
  web framework.
* The large functions of the library are split into small named steps
  (every function outside the test tooling and the numerics due for 0.7
  has a cyclomatic complexity below 11): `Chart.add_cycle`,
  `BackgroundEngine`, the spec validation, the label layout and the
  read-back of the three backends among them. Nothing drawn changes;
  where two inputs are wrong at once the error named first can differ.
* The matplotlib backend keeps the data angle of a text itself instead
  of reading a private attribute; the private attributes the read-back
  of the conformance kit uses are fenced by a test.
* Tests that need a browser (Playwright) or Kaleido run only with
  `pytest --run-browser --run-kaleido`; the default suite runs in about
  three minutes. The regression tests of the 0.2 review live in the
  modules they belong to. The blend example draws fewer lines.

0.5.0 (unreleased)
------------------

Vocabulary, units and errors (docs/v1_plan.md, package 0.5):

* One verb per operation on every chart: `set_lines`, `set_default_lines`,
  `remove_lines`, `line_sets`, `set_line_style`, `add_cycle` (with
  `closed=False` for an open process), `remove_cycle`, `move_cycle_state`,
  `cycle_states`, `set_view`, `state_at`, `update_scene`, `draw`, `save`.
  The old names (`set_isolines`, `set_default_isolines`, `remove_isolines`,
  `isoline_sets`, `set_isoline_style`, `savefig`, `set_process`,
  `remove_process`, `add_process`, `move_process_state`, `process_states`)
  still work and raise a `DeprecationWarning`; they go in 1.0.
  `tests/test_api_vocabulary.py` freezes the public names.
* `set_lines` takes `rounding` and `labels` defaults from the chart kind
  (off for property diagrams, on for psychrometric charts) and, like
  `set_view`, `state_at`, `move_cycle_state` and `cycle_states`, a
  `units=` for the values of that call.
* Unit systems: `"engineering"` (deg C, bar, kJ, g/kg, %) replaces the
  name `"EUR"`, which warns; `"IP"` (deg F, psi, Btu/lb, grains per lb,
  ft3/lb) is new; `UnitSystem` values are hashable with their units.
  `StatePoint.describe(units)` and `StatePoint.in_units(units)` print and
  convert a state.
* `PropertyError` (a `ValueError`) names the fluid, the inputs in the
  chart's units and where the state was asked for, e.g. "State 2 of
  the cycle 'hp': no state of HEOS::R290 at p = 300000 bar, s = 2.48
  kJ/kg/K (...)". A misspelt fluid fails in the `PropertyDiagram`
  constructor, in `from_spec` and in the `fluid` setter, which then
  leaves the diagram unchanged.
* `rankine(eta_is_turbine=, eta_is_pump=)`; the old keyword names warn.
* Behaviour changes: `PsychrometricChart.set_lines` and
  `set_default_lines` have the positional order of `Chart.set_lines`
  now (`key, values, num, range, rounding, labels, points, units`); pass
  `labels=` by name. The psychrometric constructor's `units` default
  reads "engineering".

0.4.0 (unreleased)
------------------

One chart model (docs/v1_plan.md, package 0.4):

* `Chart` is the facade; `PropertyDiagram` and `PsychrometricChart` are
  its two constructors and share every method. A psychrometric chart is
  a `DiagramSpec` with `HumidAirSpec` as fluid, diagram type `"WT"` and
  a `Region` of T and W bounds; it is computed by the one `Engine`
  through a `HumidAir` property provider and composed by the one
  `compose`. `spec/psychro.py` and `compose/psychro.py` are gone.
* One quantity table (`W`, `RH`, `Twb`, `Tdp`, `v` added) and one unit
  table per unit system; `"EUR"` shows g/kg, % and deg C for humid air.
* Line families per chart kind (`coolplot.core.diagram_type.FAMILIES`)
  carry the sweep quantity, the preferred label edges, the default
  number of lines and the phase boundary values; `Settings.labels.edges`
  is now empty by default and only overrides them.
* `StatePoint` holds whichever quantities its provider computes;
  humid-air states (`AirState` before) are `StatePoint` values too.
* Air processes are cycles with straight paths: item ids are
  `cycle/<name>/...`, `Interaction` needs no special case, and
  `add_cycle`, `cycle_states` and `move_cycle_state` work on them.
  `add_process`, `process_states` and `move_process_state` remain as
  the air vocabulary.
* `Scene.to_dict` / `Scene.from_dict`, and docs/contracts.md with the
  spec, curve and scene records.
* Psychrometric charts use `settings.calc.points` (250 by default,
  100 before); `points=` on the constructor still overrides it.
* Behaviour changes: a `PsychroSpec` JSON file of 0.3 is not read by
  `DiagramSpec.from_dict` (no upgrade path; such files were saved for
  one minor release); `set_lines("RH", [0])` raises instead of drawing
  a line on the axis; a chart region that lies entirely in the fog
  raises at `update_scene` instead of drawing nothing; a complete
  state of the other chart kind is refused by `add_cycle` and
  `add_process`; `cycle_states` lists the states by ascending number.

0.3.0
-----

* Background calculation: `PropertyDiagram(..., background="threads"` or
  `"processes")` never waits for a line; coarse previews first, then the
  final lines, with `on_ready`, `progress`, `wait()` and `close()`.
  Failed lines are tried again and then reported.
* Events from the backends (hover, click, drag, view changes, resizes)
  in the axes' units, and `Interaction` for zoom, hover and dragging the
  states of cycles, in matplotlib and in the browser.
* New backends: plotly, and a browser backend that streams small patches
  to a JavaScript client, with a dependency-free development server
  (localhost only, input checked).
* Psychrometric charts (`PsychrometricChart`): lines of relative
  humidity, wet-bulb temperature, enthalpy and specific volume cut at
  saturation, air processes on top, any total pressure.
* PDF as a first-class output: fonts embedded as TrueType, texts kept as
  text (labels with halos included), theme colours, the chart title as
  PDF title, reproducible files, `save_pdf` for several charts in one
  file, `Font(files=...)`, `strict_fonts` and `fonts_used()`. A PDF check
  in the conformance kit reads files back without external tools. plotly
  writes PDF through kaleido (extra "images").
* The wet-bulb search of psychrometric charts reports no convergence
  instead of returning the last estimate.
* The physics fixes of 0.2.0 (mixture states, mixture limits, blends on
  CoolProp 6 and 7, incompressibles, cache fingerprint) are part of this
  release as well.
* Texts are always plain text: "$5 or $6" is never typeset as math.

0.2.0
-----

A new package layout and API; the legacy API (`from CoolPlot.Plot import
PropertyPlot`) is gone. Stay on `pip install "coolplot<0.2"` if you need it.

* Layers with one job each: specs (what to plot), thermo (CoolProp
  calculations), engine (caching), compose (styles, texts and label
  layout) and render (plotting backends). `tests/test_architecture.py`
  enforces the import rules.
* matplotlib is one backend among several: a dependency-free SVG backend
  is included, and backends follow a written contract
  (docs/backends.md) checked by a conformance kit.
* Interactive applications redraw only what changed: a backend-neutral
  scene with item ids, synchronised selectively; changing units or the
  theme recalculates nothing.
* `PropertyDiagram`: log(p)-h, T-s, h-s, p-s, p-rho, T-rho and p-T
  diagrams for pure fluids and blends, with one `Settings` value for
  point counts, margins, labels and page size, and JSON round trips of
  the whole diagram.
* Styling is first class: themes ("default", "dark", "print",
  "classic"), validated style values and a styling guide.
* Isoline labels sit at the edges of the chart and keep clear of cycles
  (keep-out zones); one central number format for all labels.
* Cycles on diagrams, given state by state in the diagram's units or from
  cycle models, including split and two-stage cycles.
* Works with CoolProp 6.8, 7.2 and 8. With CoolProp 6 and 7, lines of
  constant s, h, u or rho of a blend are skipped with a warning that says
  so (their flashes do not support mixtures there); isotherms, isobars
  and quality lines work.
* Every state CoolProp returns for a mixture is checked against the
  saturated densities at its temperature: CoolProp 8's T,rho flash
  answers some inputs inside the two-phase region with a "gas" at a
  wrong pressure, and such points are left out instead of drawn.
* Blends start at the highest triple-point temperature of their
  components, not at CoolProp's mole-weighted average, below which one
  component is solid.
* Incompressibles (`INCOMP::...`) plot with absolute limits; relative
  limits and quality lines give a clear error at once.
* Cache keys carry a fingerprint of CoolProp's version, configuration and
  reference state; a changed configuration rebuilds the states, and
  `diagram.refresh()` does the same after `set_reference_state`.
