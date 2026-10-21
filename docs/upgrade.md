# Upgrade guide

## Stability from 1.0

From 1.0 to 2.0 the public API is stable. It is:

* the names importable from `coolplot` and the methods and properties of
  the charts, with their keyword arguments (the names are frozen in
  tests/test_api_vocabulary.py);
* the renderers in `coolplot.render` and the cycle models in
  `coolplot.thermo.cycles`, as the API reference documents them;
* the records of {doc}`reference/contracts`: a spec, curve or scene saved
  by 1.x reads in every later 1.x.

A name that has to change in 1.x keeps working with a
`DeprecationWarning` and goes in 2.0. Not part of the promise: names
starting with an underscore, the helpers in `coolplot.core`,
`coolplot.engine`, `coolplot.compose` and `coolplot.corelib`,
`coolplot.testing`, the scene item ids, and the exact coordinates of a
chart (better numerics may move points).

## From 1.1 to 1.2

Nothing to change. 1.2 adds `"via": "sensible"`, `PsychrometricChart.mix`,
`PsychrometricChart.add_zone`, `Chart.state`, state labels
(`add_cycle(..., labels=...)`) and the Mollier h,x chart
(`PsychrometricChart(..., style="mollier")`). Humid-air states gain the
quantity `Thx`; a state saved by 1.1 gets it computed when it is read. Cycle records gain an optional `labels`
list, left out when a cycle has none, so records of 1.1 read and write
unchanged. The other way round is not covered: CoolPlot 1.1 reading a 1.2
record ignores its labels and refuses a state given with via "sensible". A
coolplot-core older than 1.2 still composes a 1.2 chart unless it has state
labels; then the Python composer draws it, with a warning.

One visible change: new charts draw the saturation curve also when no lines
of constant quality (or relative humidity) include it. Set
`chart.show_saturation = False` to draw a chart without it. Specs saved by
1.1 keep their look.

## From 1.0 to 1.1

Nothing to change. 1.1 adds `set_lines(..., at_saturation=...)` and a
cache of traced lines on disk (off unless asked for, see the how-to on
caching). Spec records gain an `anchor` field per family and theme
records an `isoline_label_color` field (labels in the colour of their
lines); records of 1.0 read unchanged. A coolplot-core older than 1.1
still composes a 1.1 chart unless it uses lines labelled by their
saturation state or labels in line colours; then the Python composer
draws it, with a warning.

## From 0.9 to 1.0

The names deprecated since 0.5 are removed (the table under "From 0.4 to
0.5" lists their replacements). A removed chart method raises an
AttributeError that names its replacement, for example
`PropertyDiagram.set_process() was removed in CoolPlot 1.0; use add_cycle
...`. In detail:

* the chart methods `set_isolines`, `set_default_isolines`,
  `remove_isolines`, `isoline_sets`, `set_isoline_style`, `savefig`,
  `set_process`, `remove_process`, and on psychrometric charts
  `add_process`, `move_process_state`, `process_states`;
* the unit system name `"EUR"` in calls such as `units="EUR"` (use
  `"engineering"`);
* the keywords `eta_turbine=` and `eta_pump=` of `rankine` (use
  `eta_is_turbine=` and `eta_is_pump=`).

Saved specs still read: those that hold processes (written by
`set_process`) still draw them, and those saved by 0.4 with
`"units": "EUR"` read as engineering units.

The constant `coolplot.EUR` did not warn before 1.0, so it stays through
1.x as an old name of `coolplot.ENGINEERING`, now with a
`DeprecationWarning`, and goes in 2.0.

If your code ran under 0.9 without a `DeprecationWarning`, it runs under
1.0 unchanged.

## From 0.8 to 0.9

0.9 is the deprecation release: nothing is removed, and every name that
goes in 1.0 warns with a `DeprecationWarning` that names its replacement
(the table under "From 0.4 to 0.5"). Run your code with
`python -W error::DeprecationWarning` to find the calls to change; with
none left, 1.0 changes nothing for you.

* One setting chooses between the Python code and the C++ ports:
  `coolplot.set_native_mode("auto" | "on" | "off")`, with the environment
  variable `COOLPLOT_NATIVE` as the starting value. "auto" (the default)
  computes lines with CoolProp's port when it is installed and composes
  in Python; "on" also composes and writes SVG with coolplot-core; "off"
  is Python everywhere. All three give the same charts.
* `COOLPLOT_NATIVE=auto` now means the default mode. Before, any value but
  "0" switched coolplot-core on.

## From 0.6 to 0.7

* CoolProp 8.0 or later is required.
* Lines have a different number of points: the resolution
  (`Settings.calc.points`) sets the point spacing: a straight line that
  crosses the whole chart gets about `points / 2` points, bends get more.
  Code that relied on 250 points per line reads `len(curve.x)` instead.
* Lines are cut at the edges of the axes instead of continuing outside;
  a line whose value sits at the very edge of its range is left out.
* Fluid states carry `v` (specific volume); `STATE_KEYS` has eight
  entries. A state saved before 0.7 is completed when it is loaded.
* `Unit` has a fourth field, the label of a difference; the three-field
  form still reads.
* `PropertyError` has `reason` and `limits`; the message says what is
  wrong before CoolProp's own words.

## From 0.4 to 0.5

The chart vocabulary is one verb per operation. The old names warn and
go in 1.0:

| Old | New |
|---|---|
| `set_isolines`, `set_default_isolines`, `remove_isolines` | `set_lines`, `set_default_lines`, `remove_lines` |
| `isoline_sets`, `set_isoline_style` | `line_sets`, `set_line_style` |
| `set_process(name, line_states, marker_states)` | `add_cycle(name, states)`, which computes the paths between the states itself |
| `remove_process` | `remove_cycle` |
| psychrometric `add_process`, `move_process_state`, `process_states`, `remove_process` | `add_cycle(..., closed=False)`, `move_cycle_state`, `cycle_states`, `remove_cycle` |
| `savefig` | `save` |
| `units="EUR"` | `units="engineering"` |
| `rankine(eta_turbine=..., eta_pump=...)` | `rankine(eta_is_turbine=..., eta_is_pump=...)` |

## From 0.1 (the legacy API) to 0.2 and later

Version 0.2 replaced the legacy API (`from CoolPlot.Plot import
PropertyPlot`). The table gives the equivalents:

| Legacy | Now |
|---|---|
| `PropertyPlot("HEOS::R290", "ph", unit_system="EUR", tp_limits="ACHP")` | `PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")` |
| `plot.calc_isolines(CoolProp.iQ, num=11)` | `diagram.set_lines("Q", num=11)` |
| `plot.calc_isolines()` | `diagram.set_default_lines()` |
| `plot.draw_process(states)` | `diagram.add_cycle("name", states)` |
| `plot.show()`, `plot.savefig("x.png")` | `diagram.show()`, `diagram.save("x.png")` |
| `plot.axis`, `plot.figure` | `MatplotlibRenderer(ax=ax)` and `renderer.sync(diagram.update_scene())` |

If you depend on the legacy API, stay on the last legacy release with
`pip install "coolplot<0.2"`.
