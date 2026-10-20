# Getting started

## Install

```bash
pip install coolplot                # SVG files and web pages, with no further dependencies
pip install "coolplot[matplotlib]"  # also PNG, PDF and interactive windows
pip install "coolplot[plotly]"      # also plotly figures
```

Four ways of drawing come with CoolPlot and give the same picture: the
SVG writer and the web page writer (no dependencies), matplotlib and
plotly. `save` picks one by the file extension.

CoolPlot needs Python 3.10 or later (tested up to 3.14) and CoolProp 8.0 or later.

## A first chart

```python
from coolplot import PropertyDiagram

diagram = PropertyDiagram("R290", "ph", units="engineering", tp_limits="ACHP")
diagram.set_lines("Q", num=11, labels=True)                 # vapour quality, every 0.1
diagram.set_lines("T", num=12, rounding=True, labels=True)  # isotherms at round temperatures
diagram.set_lines("s", num=10, rounding=True, labels=True)  # isentropes
diagram.save("R290_ph.png")
```

Line by line:

* `"R290"` is a CoolProp fluid name; `"HEOS::R32[0.7]&R125[0.3]"` is a
  blend with mole fractions, `"INCOMP::MEG[0.3]"` a brine.
* `"ph"` is the diagram type, vertical axis first: `"ph"`, `"Ts"`,
  `"hs"`, `"ps"`, `"prho"`, `"Trho"`, `"pT"`.
* `units="engineering"` means deg C, bar and kJ/kg for everything you
  pass in and read out; `"SI"`, `"KSI"` (kPa, kJ) and `"IP"` are the
  other choices.
* `tp_limits="ACHP"` chooses the temperature and pressure region the
  lines cover, here the one of refrigeration practice.
* `save` writes SVG or HTML without any plotting library, PNG, PDF and
  the other formats through matplotlib, by the file extension; `show()`
  opens a window.

## A cycle on the chart

```python
diagram.add_cycle("Heat pump", [
    {"p": 3.0, "T": 0.0},                               # 1 compressor inlet, bar and deg C
    {"p": 15.0, "via": "compression", "eta_is": 0.7},   # 2 compressor outlet
    {"p": 15.0, "Q": 0.0},                              # 3 condenser outlet
    {"p": 3.0, "via": "isenthalpic"},                   # 4 after the valve
])
print(diagram.cycle_states("Heat pump", units="engineering")[2])
```

Each state is two properties in the chart's units, or one property and
the process (`"via"`) that leads to it from the state before. The
condenser path bends on the saturation dome, because CoolPlot follows the
isobar instead of drawing a straight line. {doc}`how_to/cycles` has the
whole vocabulary, and `coolplot.thermo.cycles` has ready-made models
(`simple_compression`, `two_stage`, `rankine`).

## A psychrometric chart

```python
from coolplot import PsychrometricChart

chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))   # deg C and g/kg, sea level
chart.set_default_lines()
chart.add_cycle("Cooling coil", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}], closed=False)
chart.save("psychro.png")
```

## What to read next

The {doc}`tutorials/index` take one task each from start to finish. The
{doc}`how_to/index` pages answer one question each. If something does
not work, {doc}`how_to/troubleshooting` lists the messages CoolPlot gives
and what they mean.
