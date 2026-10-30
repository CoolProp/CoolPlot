# Upgrade guide

## Coming from 0.1.7 on PyPI

The release before 1.0 on PyPI is 0.1.7, the legacy API. The versions 0.2
to 0.9 in between were development versions and were not published, so
the sections for them below (deprecated names, the native numerics) do
not concern you. What changes for you:

* the package is imported as `coolplot`, not `CoolPlot`, and the legacy
  classes are gone: the table in
  [From 0.1 to 0.2](#from-01-the-legacy-api-to-02-and-later) gives the
  equivalent of each call;
* CoolPlot needs Python 3.11 or later (1.0 and 1.1: 3.10) and CoolProp
  8.0 or later.

To stay on the legacy API, pin it: `pip install "coolplot<0.2"`.

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

## From 1.4 to 1.5

Nothing to change in your code, but charts in the `default` and `dark`
themes look different. Every quantity now has a colour of its own, the
same on every chart: temperature red, pressure wine, enthalpy orchid,
entropy blue, density teal, internal energy purple (1.4 gave the colours
out by position: blue, orange, aqua). Why is in
{doc}`explanation/accessibility`. For the colours of 1.4:

```python
from coolplot.style.theme import DEFAULT
diagram.theme = DEFAULT.with_(categorical=("#2a78d6", "#eb6834", "#1baf7a", "#eda100"), isoline_colors=None)
```

For the dark theme of 1.4, use `DARK` with
`("#3987e5", "#d95926", "#199e70", "#c98500")`. A theme of your own
derived from `DEFAULT` or `DARK` with new `categorical` colours needs
`isoline_colors=None` as well, or the pinned colours win.

The `classic` theme is gone; its idea, one colour per quantity, is now
the default. Code that asks for `theme="classic"` gets a `ValueError`;
a chart saved with it keeps its colours, since a saved chart holds its
whole theme.

## From 1.3 to 1.4

Nothing to change in your code. Axis titles, legends and labels of new
charts write symbols and units with their own characters: "Density
&rho; / kg/m&sup3;" instead of "Density rho / kg/m3", "T=20 &deg;C"
instead of "T=20 deg C", and &phi; for the relative humidity on both
humid air charts. For the plain letters of 1.3:

```python
chart.settings = chart.settings.with_(labels={"symbols": "ascii"})
```

Specs saved by 1.3 or earlier keep the plain letters. Code that reads
label texts from the scene of a new chart finds the new characters.
What you write in code stays the same: quantities are still `"rho"`
and `"RH"`, units `Unit("deg C", ...)`, and `UnitSystem.describe`
still writes "25 deg C". A coolplot-core older than 1.4 cannot write the
new characters; the Python composer then draws the chart, with a warning.

The badge references of a mixture start with a line naming it and its
composition ("R407C: R32 23 %, R125 25 %, R134a 52 % by mass"), see the
how-to on branding.

A chart checks a cycle against its fluid by the model of the fluid
(`Cycle.fluid_model`, filled in by the cycle models), not by its name. A
cycle of a mixture given by mass fractions, with interaction parameters
or as an AbstractState now draws on its own chart, where 1.3 refused it;
a cycle with other interaction parameters than the chart's is now
refused, where 1.3 drew it. `Cycle` has a new last field, `fluid_model`;
a cycle built with only a `fluid` name is checked by the name, as before.

## From 1.2 to 1.3

Nothing to change in your code to run it. CoolPlot now ships its type
annotations (the package carries `py.typed`), so a type checker such as
mypy or pyright checks your calls to CoolPlot instead of taking every
CoolPlot name as unknown. Code that passed the checker before may now
get reports where it passes a value of the wrong kind, for example a
number for a unit system. A range (`range=` of `set_lines`, `"range"` of
`at_saturation`, `T_range` and `W_range` of a psychrometric chart) that
is not two values is refused with a ValueError that says so.

`set_line_style("Q", ...)` (or `"RH"`) restyles the quality (humidity)
lines now; it was ignored before, so a chart or a saved spec that set it
draws those lines differently. `set_line_style("saturation", ...)` is
new, for the saturation curve.

## From 1.1 to 1.2

1.2 needs Python 3.11 or later; on Python 3.10, pip keeps installing
1.1. Nothing to change in your code. 1.2 adds `"via": "sensible"`, `PsychrometricChart.mix`,
`PsychrometricChart.add_zone`, `Chart.state`, state labels
(`add_cycle(..., labels=...)`) and the Mollier h,x chart
(`PsychrometricChart(..., style="mollier")`). Humid-air states gain the
quantity `Thx`; a state saved by 1.1 gets it computed when it is read. Cycle records gain an optional `labels`
list, left out when a cycle has none, so records of 1.1 read and write
unchanged. The other way round is not covered: CoolPlot 1.1 reading a 1.2
record ignores its labels and refuses a state given with via "sensible". A
coolplot-core older than 1.2 still composes a 1.2 chart unless it has state
labels; then the Python composer draws it, with a warning.

Two visible changes. New charts draw the saturation curve also when no
lines of constant quality (or relative humidity) include it; set
`chart.show_saturation = False` to draw a chart without it. And labels
sit on rails, showing bare values with symbol and unit in the legend,
which moves inside the plot area into the emptiest corner. For the look
of 1.1:

```python
chart.settings = chart.settings.with_(labels={"mode": "edge"})
legend = chart.theme.axes.legend.with_(location="outside right")
chart.theme = chart.theme.with_(axes=chart.theme.axes.with_(legend=legend))
```

Specs saved by 1.1 hold their label mode and their theme (legend
location included), so they draw as before. Code that reads label texts
from the scene of a new chart finds bare numbers ("20" instead of
"T=20 deg C") unless it asks for edge labels.

A coolplot-core older than 1.2 refuses rails and the automatic legend;
the Python composer then draws the chart, with a warning.

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
