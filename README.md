
![GitHub License](https://img.shields.io/github/license/coolprop/coolplot.svg)
![Coverage - Codecov](https://img.shields.io/codecov/c/gh/CoolProp/coolplot.svg)
![Coverage - Coveralls](https://img.shields.io/coveralls/github/CoolProp/coolplot.svg)
![PyPI - Version](https://img.shields.io/pypi/v/coolplot.svg)
![PyPI - Downloads](https://img.shields.io/pypi/dm/coolplot.svg)


CoolPlot
========

Property diagrams and psychrometric charts for engineering
thermodynamics, with [CoolProp] as the source of every property:
log(p)-h, T-s, h-s, p-s, p-rho, T-rho and p-T diagrams for pure fluids
and refrigerant blends, cycles drawn on top of them, and psychrometric
charts for humid air.

![A log(p)-h chart of propane with a heat pump cycle](https://raw.githubusercontent.com/CoolProp/CoolPlot/master/docs/_static/R290_ph.png)

```python
from coolplot import PropertyDiagram
from coolplot.thermo.cycles import simple_compression

diagram = PropertyDiagram("R290", "ph", units="engineering", tp_limits="ACHP")
diagram.set_default_lines(labels=True)
diagram.add_cycle(simple_compression("R290", T_evap_C=-5, T_cond_C=45, dT_sh_K=5))
diagram.save("R290_ph.png")           # or .pdf, .svg; show() opens a window
```

Cycles can be given state by state in the chart's units, by two
properties or by the process that leads to a state:

```python
diagram.add_cycle("Heat pump", [
    {"p": 3.0, "T": 0.0},                               # 1 compressor inlet, bar and deg C
    {"p": 15.0, "via": "compression", "eta_is": 0.7},   # 2 compressor outlet
    {"p": 15.0, "Q": 0.0},                              # 3 condenser outlet
    {"p": 3.0, "via": "isenthalpic"},                   # 4 after the valve
])
```

What else it does:

* Isoline labels sit at the edges of the chart, as on printed charts,
  and keep clear of the cycles.
* Blends: the dome from CoolProp's phase envelope, the temperature glide
  inside it, a chart in seconds.
* Units: SI, kPa and kJ, deg C and bar, or inch-pound; a change of units
  costs no new calculation.
* Output: PNG and PDF through matplotlib (fonts embedded, texts kept as
  text, several charts per file), SVG with no dependencies, plotly
  figures and HTML pages, live charts in a web page.
* Interactive: zoom, hover and dragging of cycle states in matplotlib
  and in a web page; only what changed is recomputed and redrawn;
  lines can be computed in the background.

The documentation (getting started, tutorials, how-to pages, the API
reference and a gallery of the examples) is built from `docs/` and
published on Read the Docs; `make docs` builds it locally.

The code was forked from the main [CoolProp repository] at v6.3.0 with
its history preserved, hence the old commits. Version 0.2 replaced the
legacy API (`from CoolPlot.Plot import PropertyPlot`); the upgrade guide
in the documentation gives the equivalents, and `pip install "coolplot<0.2"`
keeps the last legacy release. From 1.0 to 2.0 the public API is stable.

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
