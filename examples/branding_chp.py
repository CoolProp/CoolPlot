# -*- coding: utf-8 -*-
"""
A company chart: Clean Heat Partners
====================================

The charts of the free property chart tool of Clean Heat Partners
(tools.cleanheatpartners.com) are drawn with CoolPlot. This is one of
them: a company theme and the company's branding on a log(p)-h chart of
R290 with a heat pump cycle.

* The theme is CoolPlot's default with the company colours for the line
  families: teal for the isotherms, rust for the isentropes, dark teal for
  the isochores (ochre would colour a fourth family; the lines of constant
  quality keep their grey). The default pins one colour per quantity;
  ``isoline_colors=None`` drops those, so that the families of each chart
  take the company colours in turn. ``Theme.with_`` changes only what is
  given, so every line width, font and the legend stay CoolPlot's.
* The saturation line is drawn without its casing (the band in the
  background colour along it), as on the company's charts.
* The badge holds the company logo, the reference of the equation of state
  of R290, the CoolProp and CoolPlot versions and the company's web
  address; the company's brandmark is the faint watermark behind the
  lines. Both pictures are SVG files in the folder ``data`` next to this
  script (``examples/data`` in the repository): a copy of the script
  downloaded from this page needs that folder beside it. The matplotlib
  backend would need PNG variants of the pictures as well.

The logo and the brandmark are trademarks of Clean Heat Partners ApS. They
are not covered by the MIT licence of CoolPlot (see ``examples/data/NOTICE``)
and are shown here as an example of branding; use your own pictures for your
charts.

Run with:  python examples/branding_chp.py
Writes branding_chp.svg.
"""
import os

from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer
from coolplot.style.theme import DEFAULT
from coolplot.thermo.cycles import simple_compression

# The pictures are next to this script. A plain run may start in any folder and
# finds them through __file__; Sphinx-Gallery runs the script in its own folder
# and defines no __file__
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
DATA = os.path.join(HERE, "data")
LOGO = os.path.join(DATA, "chp_logo.svg")
BRANDMARK = os.path.join(DATA, "chp_brandmark_grey.svg")

# The company colours: teal and dark teal differ in lightness, rust and ochre in hue
CHP_THEME = DEFAULT.with_(name="chp", categorical=("#00998B", "#AB4729", "#0E4D45", "#A08C00"), isoline_colors=None)

diagram = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
diagram.theme = CHP_THEME
diagram.set_line_style("saturation", casing_width_pt=0)
diagram.set_lines("Q", num=11, labels=True)
diagram.set_lines("T", num=10, rounding=True, labels=True)
diagram.set_lines("s", num=8, rounding=True, labels=True)
diagram.set_lines("rho", num=6, rounding=True, labels=True)

cycle = simple_compression(diagram.fluid, T_evap_C=-5.0, T_cond_C=45.0, dT_sh_K=5.0, dT_sc_K=2.0, eta_is=0.7)
COP_heating = cycle.result["COP_heating"]
diagram.add_cycle(cycle)
diagram.title = "R290 heat pump, COP {0:.2f} (heating)".format(COP_heating)

diagram.settings = diagram.settings.with_(branding={
    "logo": (LOGO,),
    "logo_width_pt": 80,
    "references": "short",
    "versions": True,
    "lines": ("cleanheatpartners.com",),
    "watermark": (BRANDMARK,),
})

diagram.draw(SvgRenderer(width=900, height=650)).save("branding_chp.svg")
print("COP heating: {0:.2f}".format(COP_heating))
