
![GitHub License](https://img.shields.io/github/license/coolprop/coolplot.svg)
![Coverage - Codecov](https://img.shields.io/codecov/c/gh/CoolProp/CoolPlot.svg)
![Coverage - Coveralls](https://img.shields.io/coveralls/github/CoolProp/CoolPlot.svg)
![PyPI - Version](https://img.shields.io/pypi/v/coolplot.svg)
![PyPI - Downloads](https://img.shields.io/pypi/dm/coolplot.svg)


CoolPlot
========

This repository contain code for a Python module to create property plots
for engineering thermodynamics applications using [CoolProp].

It focusses on refrigeration and heat pumping applications and the enthalpy-
pressure diagrams (logp,h) are considered to be more mature than others.
However, entropy-temperature diagrams (T,s) have also been implemented and
should work for most fluids.

We are in the process of separating the calculations from the plotting
routines - expect some breaking changes until v1.0.0 is released. The code
has been forked from the main [CoolProp repository] at v6.3.0 and the history
was preserved, thus the old commits.

The new API keeps property calculations, the description of the plot and
the plotting library apart, so that matplotlib is one backend among
several and interactive applications only redraw what changed. See
[docs/architecture.md](docs/architecture.md) for the design.

```python
from CoolPlot import PropertyDiagram
from CoolPlot.render.mpl import MatplotlibRenderer   # or render.svg.SvgRenderer

diagram = PropertyDiagram("HEOS::R290", "ph", units="EUR", tp_limits="ACHP")
diagram.set_isolines("Q", num=11)
diagram.set_isolines("T", num=12, rounding=True, labels=True)

renderer = MatplotlibRenderer()
renderer.sync(diagram.update_scene())
renderer.show()

diagram.units = "SI"                     # no new property calculations,
renderer.sync(diagram.update_scene())    # existing lines are updated in place

diagram.theme = "print"                  # "default", "dark", "print", "classic"
renderer.sync(diagram.update_scene())    # only styles change
```

Every backend renders themes identically; see
[docs/styling.md](docs/styling.md) for themes and
[docs/backends.md](docs/backends.md) for adding a backend.

The legacy API in `CoolPlot.Plot` is deprecated and will be removed.

Pull requests are encouraged!


Installation
------------

The project gets published on [PyPi] as `coolplot` and you can install it
using pip

```bash
pip install coolplot              # core, includes the SVG backend
pip install coolplot[matplotlib]  # with the matplotlib backend
```


License
-------

This Python package is released under the terms of the MIT license. 


  [CoolProp]: http://coolprop.sourceforge.net/
  [CoolProp repository]: https://github.com/CoolProp/CoolProp
  [PyPi]: https://docs.python.org/3/distutils/packageindex.html
