
![GitHub License](https://img.shields.io/github/license/coolprop/coolplot.svg)
![Coverage - Codecov](https://img.shields.io/codecov/c/gh/CoolProp/coolplot.svg)
![Coverage - Coveralls](https://img.shields.io/coveralls/github/CoolProp/coolplot.svg)
![PyPI - Version](https://img.shields.io/pypi/v/coolplot.svg)
![PyPI - Downloads](https://img.shields.io/pypi/dm/coolplot.svg)


CoolPlot
========

This repository contain code for a Python module to create property plots
for engineering thermodynamics applications using [CoolProp].

It focusses on refrigeration, heat pumping and power cycles: log(p)-h,
T-s, h-s, p-s, p-rho, T-rho and p-T diagrams for pure fluids and blends,
with cycles drawn on top, and psychrometric charts for humid air.
Property calculations, the description of the plot and the plotting
library are kept apart, so matplotlib is one backend among several (SVG
without dependencies, plotly, and a browser backend with a small
development server) and interactive applications only redraw what
changed. Lines can be calculated in the background, and zoom, hover and
dragging cycle states work in matplotlib and in the browser. PDF output
is print-ready: fonts embedded as TrueType, texts kept as text, the
theme colours exactly, and several charts per file with `save_pdf`.

The code was forked from the main [CoolProp repository] at v6.3.0 with its
history preserved, hence the old commits. Expect some breaking changes
until v1.0.0.

```python
from coolplot import PropertyDiagram
from coolplot.thermo.cycles import simple_compression

diagram = PropertyDiagram("HEOS::R290", "ph", units="EUR", tp_limits="ACHP")
diagram.set_isolines("Q", num=11, labels=True)
diagram.set_isolines("T", num=12, rounding=True, labels=True)
diagram.add_cycle(simple_compression("R290", T_evap_C=-5, T_cond_C=45))
diagram.savefig("R290_ph.png")           # matplotlib; SvgRenderer needs nothing extra
```

Cycles can also be given state by state in the diagram's units,
including split and two-stage cycles:

```python
diagram.add_cycle("Heat pump", [
    {"p": 3.0, "T": 0.0},                               # 1 compressor inlet, bar and deg C
    {"p": 15.0, "via": "compression", "eta_is": 0.7},   # 2 compressor outlet
    {"p": 15.0, "Q": 0.0},                              # 3 condenser outlet
    {"p": 3.0, "via": "isenthalpic"},                   # 4 after the valve
])
```

Isoline labels sit at the edges of the chart and keep clear of the
cycles. In an interactive application, changing units, the theme or a
cycle recalculates and redraws only what changed:

```python
from coolplot.render.mpl import MatplotlibRenderer
renderer = MatplotlibRenderer()
renderer.sync(diagram.update_scene(renderer.plot_size_pt()))
diagram.units = "SI"                     # no new property calculations
renderer.sync(diagram.update_scene())    # existing lines are updated in place
```

* [docs/user_guide.md](docs/user_guide.md): how to use CoolPlot
* [docs/styling.md](docs/styling.md): themes and styles
* [docs/backends.md](docs/backends.md): writing a plotting backend
* [docs/architecture.md](docs/architecture.md): the design
* [examples/](examples): quick start, two-stage cycles, a refrigerant
  blend, an interactive chart with sliders and dragging, a browser app,
  a psychrometric chart

Version 0.2 replaces the legacy API (`from CoolPlot.Plot import PropertyPlot`).
If you depend on it, stay on the last legacy release with
`pip install "coolplot<0.2"`.

Pull requests are encouraged!


Installation
------------

The project gets published on [PyPi] as `coolplot` and you can install it
using pip

```bash
pip install coolplot                # core, includes the SVG backend
pip install "coolplot[matplotlib]"  # with the matplotlib backend
```


License
-------

This Python package is released under the terms of the MIT license. 


  [CoolProp]: https://coolprop.org/
  [CoolProp repository]: https://github.com/CoolProp/CoolProp
  [PyPi]: https://pypi.org/project/CoolPlot/
