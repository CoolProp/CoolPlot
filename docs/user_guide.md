# CoolPlot user guide

CoolPlot draws thermodynamic property diagrams (log(p)-h, T-s, h-s and
more) with [CoolProp](https://coolprop.org) as the source of all property
data, and puts cycles on top of them. This guide shows how to use it. The
design is described in [architecture.md](architecture.md), themes in
[styling.md](styling.md) and writing a new plotting backend in
[backends.md](backends.md).

## 1. Installation

```bash
pip install coolplot                # core, with the SVG backend
pip install "coolplot[matplotlib]"  # with the matplotlib backend
```

CoolPlot needs Python 3.10 or later and CoolProp 6.8 or later; it is
tested with CoolProp 6.8, 7.2 and 8.0. Refrigerant blends are much faster
with CoolProp 8 (section 8).

## 2. A first diagram

```python
from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer

diagram = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
diagram.set_lines("Q", num=11, labels=True)                 # vapour quality
diagram.set_lines("T", num=12, rounding=True, labels=True)  # isotherms
diagram.set_lines("s", num=10, rounding=True, labels=True)  # isentropes

diagram.draw(SvgRenderer()).save("R290_ph.svg")
```

`diagram.draw()` without a renderer uses matplotlib; `diagram.show()` and
`diagram.save("R290_ph.png")` are shortcuts for scripts.

Three backends come with CoolPlot and draw the same scene:
`coolplot.render.svg.SvgRenderer` (no dependencies),
`coolplot.render.mpl.MatplotlibRenderer` (`pip install
"coolplot[matplotlib]"`) and `coolplot.render.plotly.PlotlyRenderer`
(`pip install "coolplot[plotly]"`; `renderer.figure` is the plotly
figure, `save("chart.html")` writes a page). plotly cannot set line caps
and always draws texts above lines; everything else looks the same.

### Fluids

Any CoolProp fluid string works: `"R290"`, `"HEOS::R290"`,
`"HEOS::R32[0.7]&R125[0.3]"` (mole fractions), `"REFPROP::R32"`, and
incompressibles such as `"INCOMP::MEG[0.3]"` (mass fractions, as CoolProp
reads them), which have no saturation curve and therefore need absolute
limits: `tp_limits=[260, 370, 1e5, 1e6]` (K and Pa), see section 9.
A `CoolProp.AbstractState` is accepted as well; CoolPlot copies its fluid,
fractions and binary interaction parameters, so later changes to your
state do not affect the diagram.

### Diagram types

Vertical axis first: `"ph"`, `"Ts"`, `"hs"`, `"ps"`, `"prho"`, `"Trho"`,
`"pT"`. Pressure and density axes are logarithmic.

### Units

`"SI"` (K, Pa, J/kg), `"KSI"` (K, kPa, kJ/kg), `"engineering"` (deg C,
bar, kJ/kg; g/kg and % for humid air) and `"IP"` (deg F, psi, Btu/lb,
grains per lb). Every value you pass to a chart method is in its units,
or in the system you name with `units=` on that call, and the chart
stores everything in SI. Changing `diagram.units` later costs no
property calculations. `"EUR"` is the old name of `"engineering"` and
still works with a warning. A custom system:

```python
from coolplot import ENGINEERING, Unit
units = ENGINEERING.with_unit("p", Unit("MPa", 1e-6), name="engineering-MPa")
diagram.units = units
```

States are SI values; `state.describe("engineering")` writes one out in
a unit system, `state.in_units("IP")` gives a dict, and
`diagram.cycle_states("hp", units="engineering")` does that for a whole
cycle. An error about a state that cannot be computed names the fluid
and the inputs in the chart's units:

```
PropertyError: State 2 of cycle 'hp': no state of HEOS::R290 at p = 300000 bar, T = 20 deg C (...).
```

### The region covered

`tp_limits` sets the temperature and pressure region in which isolines
are calculated: `"NONE"`, `"DEF"`, `"ACHP"` (refrigeration), `"ORC"`, or a
`TpLimits` value whose bounds can be absolute (SI) or relative to the
saturation range:

```python
from coolplot import TpLimits, Relative
diagram.tp_limits = TpLimits(T_min=233.15, T_max=Relative(1.2), p_min=1e5, p_max=Relative(2.0))
```

`diagram.set_view(x_limits, y_limits)` zooms (in display units) without
any new calculation; `set_view()` resets.

## 3. Isolines

```python
diagram.set_lines("T", values=[-20, 0, 20, 40])        # explicit values
diagram.set_lines("T", num=8)                          # 8 lines, evenly over the region
diagram.set_lines("T", num=8, rounding=True)           # round values: -50, 0, 50, 100 deg C
diagram.set_lines("s", num=6, range=(1.0, 2.5))        # 6 lines between 1.0 and 2.5 kJ/kg/K
diagram.set_default_lines()                            # every family that fits the diagram
diagram.remove_lines("p")
```

With `rounding=True` the values are round numbers in display units with
an even step (25 deg C steps, or 1-2-5 per decade on log axes); the number
of lines comes as close to `num` as round values allow. Lines of constant
x or y quantity (isobars in a ph chart) are straight lines parallel to an
axis and are not offered; use the grid.

Where an isoline enters or leaves the two-phase region, the saturation
state is inserted, so the kink sits exactly on the dome; an isobar in a
T-s chart runs horizontally through the dome.

`diagram.set_line_style("T", color="#000000", width_pt=1.0)` overrides
the theme for one family.

## 4. Labels

```python
diagram.settings = diagram.settings.with_(labels={"mode": "edge"})
```

| mode | Where labels go |
|------|-----------------|
| `"edge"` (default) | just inside the frame where each line leaves the plot, rotated along the line, as printed refrigerant charts do |
| `"margin"` | outside the frame, like a second set of tick labels (vertical on top), never touching the data |
| `"inline"` | at `position` along each line, as in older versions |

In edge mode every cycle keeps a zone of `keep_out_pt` points free of
labels, no two labels overlap, and a label that does not fit is left out.
Labels keep their position between updates while it stays free, so they
do not jump while a cycle is dragged. More options of `LabelSettings`:
`edges` (preferred frame edges per family), `fallback` (allow positions
further along the line), `every` (label every n-th line), `digits`,
`show_units`, `tick_digits`.

Labels are placed for the size of the plot area, which `diagram.draw()`
takes from the renderer. If you call the renderer yourself, pass it:
`renderer.sync(diagram.update_scene(renderer.plot_size_pt()))`.

## 5. Cycles

### From states

```python
diagram.add_cycle("Heat pump", [
    {"p": 3.0, "T": 0.0},                               # 1 compressor inlet
    {"p": 15.0, "via": "compression", "eta_is": 0.7},   # 2 compressor outlet
    {"p": 15.0, "Q": 0.0},                              # 3 condenser outlet
    {"p": 3.0, "via": "isenthalpic"},                   # 4 after the valve
])
```

Each state is given by two properties in the diagram's units, or by one
property and `"via"`, which takes the second property from the state
before it in the cycle:

| via | The state keeps / follows |
|-----|---------------------------|
| `"isenthalpic"` | the enthalpy (a throttling valve) |
| `"isentropic"`, `"isobaric"`, `"isothermal"`, `"isochoric"` | entropy, pressure, temperature or density |
| `"compression"`, `"expansion"` | the outlet pressure with the isentropic efficiency `eta_is` |

States can also be `StatePoint` objects, or arrays of two properties:
`diagram.add_cycle("measured", p=[...], h=[...])`. Use `units="SI"` for
values in another unit system.

The paths between states follow the process: equal pressure gives an
isobar that bends on the dome, equal enthalpy an isenthalp, equal entropy
an isentrope, anything else a polytropic path. Set a path explicitly with
`paths={(1, 2): "straight"}`.

### Split and two-stage cycles

States are numbered (list order, or the keys of a dict); `loops` gives
chains of state numbers, each drawn as one line. Chains may share states:

```python
states = {1: {"p": 1.5, "T": -25.0}, 2: {"p": 5.0, "via": "compression", "eta_is": 0.7},
          3: {"p": 5.0, "Q": 1.0},   4: {"p": 18.0, "via": "compression", "eta_is": 0.7},
          5: {"p": 18.0, "Q": 0.0},  6: {"p": 5.0, "via": "isenthalpic"},
          7: {"p": 5.0, "Q": 0.0},   8: {"p": 1.5, "via": "isenthalpic"}}
diagram.add_cycle("Two-stage", states)                                       # one split cycle
diagram.add_cycle("Two-stage", states, loops=[[1, 2, 7, 8, 1], [3, 4, 5, 6, 3]])  # two closed loops
```

### From models

```python
from coolplot.thermo.cycles import simple_compression, two_stage, rankine

cycle = simple_compression("R290", T_evap_C=-5, T_cond_C=45, dT_sh_K=5, dT_sc_K=2, eta_is=0.7)
cycle.result["COP_heating"]          # results in SI units
diagram.add_cycle(cycle)

diagram.add_cycle(two_stage("R290", -30, 45, intermediate="economizer"))
diagram.add_cycle(rankine("Water", p_high_Pa=40e5, p_low_Pa=0.1e5, T_live_C=400))
```

For blends the models take the evaporating and condensing temperatures
as dew points (EN 12900).

Calling `add_cycle` again with the same name replaces the cycle and
redraws only it. `cycle_states(name)` returns the computed states,
`remove_cycle(name)` removes it. Without a zoom window the axes grow so
that every state is inside the frame. `numbers=False` hides the state
numbers; `line_style` and `marker_style` override the theme.

`set_process(name, line_states, marker_states)` draws any sequence of
states you computed yourself, for example with
`coolplot.thermo.process_path`.

## 6. Settings, themes and saving

All tuning lives in one `Settings` value with four parts, split by what
a change costs:

| Part | Examples | A change costs |
|------|----------|----------------|
| `calc` | `points`, `saturation_points`, `solver`, `critical_margin` | recalculating the affected lines |
| `look` | the theme | restyling only |
| `labels` | `mode`, `keep_out_pt`, `digits` | new label layout only |
| `page` | `width_pt`, `height_pt`, `font_scale` | page layout only |

```python
PropertyDiagram("R290", "ph", settings="publication")    # "screen", "print", "publication", "interactive"
diagram.settings = diagram.settings.with_(calc={"points": 100}, look="dark", page={"font_scale": 1.2})
diagram.settings = diagram.settings.with_(calc="interactive")   # few points while dragging, rest unchanged
diagram.theme = "print"                                   # "default", "dark", "print", "classic"
```

The whole diagram (fluid, axes, units, isolines, cycles, settings) is an
immutable `DiagramSpec` in `diagram.spec`, which saves to and loads from
JSON:

```python
import json
from coolplot import DiagramSpec
text = json.dumps(diagram.spec.to_dict())
diagram.spec = DiagramSpec.from_dict(json.loads(text))
```

### PDF for papers, reports and print

```python
diagram.settings = diagram.settings.with_(page={"width_pt": 252, "height_pt": 190})   # one journal column
diagram.save("R290_ph.pdf")                        # vector PDF, fonts embedded as TrueType

from coolplot import save_pdf
save_pdf("report.pdf", [diagram, other_diagram, chart], metadata={"Author": "Heat pump team"})
```

PDF is a first-class output of the matplotlib backend:

* The page has the size of `settings.page`, and font sizes are in points,
  so a figure placed at 100 % in a document has exactly the type sizes
  of the theme. Set the page to the column or text width of the document
  instead of scaling the figure there.
* Fonts are embedded as TrueType (or `save(..., pdf_fonts="type3")`),
  as journals and print shops expect. Texts stay text: they can be
  selected, searched and edited, labels with a halo included.
* Matplotlib cannot embed fonts installed as CFF OpenType (many .otf
  files, often Inter) as TrueType. Such fonts are left out of the family
  lists in the PDF (matplotlib falls back character by character through
  the whole list), so a text whose first font is CFF uses the next
  TrueType font of its list there, with a warning naming both; the
  window keeps the original. Install the .ttf files of the font, or name
  them with `Font(files=...)`, to keep it. Font collections (.ttc, as on
  macOS) are checked face by face and embed fine.
* `MatplotlibRenderer(strict_fonts=True)` raises instead of falling back
  when a font is missing, also when saving would have to replace a CFF
  font. `renderer.fonts_used()` lists the fonts on screen and
  `renderer.fonts_used(pdf=True)` those a PDF gets: for print work, where a
  replaced font must not slip through.
* Colours are exactly those of the theme, as sRGB. There is no CMYK and
  no colour profile; print shops convert sRGB, or convert the PDF
  yourself (for example with Ghostscript) if a CMYK file is required.
* The same chart gives the same file (no date, no version strings), and
  the chart title becomes the PDF title. `save_pdf` writes one chart per
  page, each at its own page size.
* EPS and PS embed TrueType fonts the same way, and carry no date when
  saved to a file name. `PlotlyRenderer` writes
  PDF too when kaleido is installed (`pip install "coolplot[images]"`,
  plus Chrome); SVG and web renderers write only their own formats.

## 7. Interactive applications

A diagram only computes what changed and a renderer only redraws what
changed. The usual loop:

```python
renderer = MatplotlibRenderer(ax=ax)            # or any other backend
def on_change():
    diagram.add_cycle(simple_compression(diagram.fluid, T_evap.val, T_cond.val, name="Heat pump"))
    report = renderer.sync(diagram.update_scene(renderer.plot_size_pt()))
    # report.added, report.updated, report.unchanged say what was touched
```

Moving a cycle recalculates no isoline and redraws only the cycle (and
labels it pushes away). Changing units or the theme recalculates nothing.
`diagram.state_at(x, y)` gives the full state under the mouse. Several
diagrams of the same fluid can share their caches:
`PropertyDiagram(..., engine=other.engine)`, or with background
calculation `PropertyDiagram(..., background="threads", cache=other.cache)`
(a background engine serves one diagram). `examples/interactive_cycle.py`
shows a complete matplotlib application with sliders.

### Zoom, hover and drag

Backends with events (matplotlib, and the web backend) report what the
user does. `Interaction` handles the usual cases:

```python
from coolplot.interaction import Interaction
Interaction(diagram, renderer, on_hover=lambda state, event: print(state))
```

Zooming and panning with the toolbar lay out the labels for the new
window, and dragging a state marker of a cycle moves that state (it is
then given by the two axis quantities; states that follow it with
`"via"` move along). `diagram.move_cycle_state(name, number, x, y)` does
the same from code. For other behaviour, handle the events yourself:
`renderer.connect(callback)` delivers `Hover`, `Click`, `DragStart`,
`Drag`, `DragEnd`, `ViewChanged` and `Resized` from
`coolplot.core.events`, in the units of the axes.

### In the browser

`coolplot.render.web.WebRenderer` draws the same SVG as the SVG backend
but sends only what changed to a small JavaScript client, and turns the
browser's pointer input into the same events as matplotlib (dragging
empty space pans, the wheel zooms). `WebServer` serves it without any
web framework:

```python
from coolplot.render.web import WebRenderer, WebServer
renderer = WebRenderer(width=1000, height=700)
Interaction(diagram, renderer)
renderer.sync(diagram.update_scene(renderer.plot_size_pt()))
server = WebServer(renderer)
print("Open", server.url)
server.serve_forever()
```

For your own web application, send the messages from
`renderer.listen(callback)` to the browser (for example over a
websocket), feed the client's input to `renderer.receive(message)`, and
serve `renderer.page(stream=..., input=...)`. `receive` checks every
message and raises `ValueError` for a malformed one; answer that with an
error instead of passing it on. `save("chart.html")` writes a static
page. See `examples/web_app.py`.

`WebServer` is meant for development and small tools on your own
machine. It binds to 127.0.0.1, only answers requests that name it in
their `Host` header and only takes input from its own page, so other web
sites open in the browser cannot drive it. Bound to another address
(`host="0.0.0.0"`) it serves anyone who can reach it, without
authentication; put a real web server in front of it for that.

### Calculating in the background

```python
diagram = PropertyDiagram("HEOS::R32[0.7]&R125[0.3]", "ph", background="processes",
                          on_ready=lambda d: app.call_soon(redraw))   # your GUI's way to run on its thread
renderer.sync(diagram.update_scene())   # returns at once: previews first, then the final lines
diagram.progress                         # (ready, needed)
```

With `background="threads"` or `"processes"`, `update_scene()` never
waits for a line. Missing lines are queued, first coarse
(`Settings.calc.preview_points`) and then at full resolution, and
`on_ready(diagram)` is called from a worker when more is ready; call
`update_scene()` again then. Work the latest scene no longer needs is
cancelled. Threads keep pure-fluid charts responsive; for blends use
processes, which compute in parallel and never block the application.
`diagram.wait()` blocks until all work is done, `diagram.close()` stops
the workers (the diagram then takes no more updates), and `draw()`,
`show()` and `save()` wait for the complete picture. A line whose
calculation fails is tried once more and then skipped with a warning
naming the error. On Linux, worker processes are started by forking the
application; start the diagram before your GUI starts other threads.

## 8. Psychrometric charts

```python
from coolplot import PsychrometricChart

chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))   # deg C and g/kg, sea level
chart.set_default_lines()            # RH every 10 %, Twb every 5 deg C, h every 10 kJ/kg, v every 0.02 m3/kg
chart.add_cycle("Air conditioning", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}, {"T": 20, "W": 8.9}],
                closed=False)                # an open process: heating, cooling and reheating
chart.cycle_states("Air conditioning")[2].h  # J/kg dry air; units="engineering" gives kJ/kg
chart.save("psychro.png")                     # or chart.draw(any renderer)
```

A psychrometric chart shows humid air at one total pressure (`p=` in
bar, default sea level), with dry-bulb temperature over humidity ratio
and lines of relative humidity (`"RH"`, in %), wet-bulb temperature
(`"Twb"`), specific enthalpy (`"h"`) and specific volume (`"v"`), both
per kg of dry air. `set_lines(key, values)` chooses the values. Air
states are given by any two of `T`, `W`, `RH`, `Twb`, `Tdp`, `h`, `v`
and joined by straight lines (`closed=False` leaves the chain open). Labels,
themes, settings and every backend work as for property diagrams; the
properties come from CoolProp's `HAPropsSI`, which covers about -100 to
350 deg C and 0.1 to 100 bar. Without values, `set_lines` picks round
values (about 9 to 13 lines per family; `num=` changes that).

`chart.set_view(x_limits, y_limits)` zooms without new calculations, and
`Interaction(chart, renderer)` gives zoom, hover (`chart.state_at`) and
dragging of process states (`chart.move_cycle_state`), as for property
diagrams. `chart.spec.to_dict()` saves a chart and
`PsychrometricChart.from_spec(DiagramSpec.from_dict(data))` restores it.
A psychrometric chart is a `Chart` like a property diagram: an air
process is a cycle (`add_cycle`, `cycle_states`, `move_cycle_state`
work on it), its items are `iso/RH/0.5` and `cycle/<name>/states`, and
its lines come from `set_lines` with rounding and labels on by default.

## 9. Refrigerant blends and other mixtures

For mixtures CoolPlot traces isolines point by point, starting each point
from the previous one (`Settings.calc.solver = "auto"`). That needs
CoolProp 8: the flashes that CoolProp 6 and 7 offer for mixtures cover
only p,T and saturation inputs, so with those versions a blend chart gets
its isotherms, isobars, quality lines and the dome, and lines of constant
s, h, u or rho are skipped with a warning that says so. With CoolProp 8 a
default chart of R32/R125 takes seconds. The bubble and dew lines come
from CoolProp's phase envelope, so the dome closes properly through the
critical region, and isotherms show the temperature glide. A blend chart
starts at the highest triple-point temperature of its components (R32 is
solid below -137 deg C whatever it is mixed with).

Every state CoolProp returns for a mixture is checked against the
saturated densities at its temperature: CoolProp 8 answers some inputs
inside the two-phase region with a "gas" at a wrong pressure, and such
points are left out instead of drawn (with the flash solver they show as
gaps; the tracer gets them right).

Incompressible fluids (`"INCOMP::..."`) have no saturation curve: give
absolute limits, `tp_limits=[T_min_K, T_max_K, p_min_Pa, p_max_Pa]`, and
leave out quality lines. Isotherms, isobars and lines of h, s and u work.

### CoolProp's global settings

Changing CoolProp's configuration (`set_config_bool` and friends) is
noticed: the next update computes with fresh states. A changed reference
state (`CoolProp.CoolProp.set_reference_state`) is not visible from
outside; call `diagram.refresh()` after it, otherwise the diagram keeps
the enthalpy and entropy offsets it started with. Curves are cached with
a fingerprint of CoolProp's version, configuration and reference state,
so a curve made under other settings is never served.

## 10. When something goes wrong

* A warning "Skipping the line ..." or "... has gaps" names the line and
  how many points CoolProp could not compute. Each line warns once.
* `add_cycle` raises right away, naming the state, if a state cannot be
  computed (for example a pressure above the critical pressure with
  `"Q": 0.0`), and refuses a cycle a model computed for another fluid.
* The cycle models check their inputs: the condensing temperature has to
  be above the evaporating one, live steam above its saturation
  temperature.
* CoolProp's own messages are passed on; the fluid string and the inputs
  are usually enough to reproduce them with CoolProp directly.
