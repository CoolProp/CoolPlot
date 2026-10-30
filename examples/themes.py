# -*- coding: utf-8 -*-
"""
One chart in the four themes
============================

Every colour, line width and font of a chart comes from its theme, and
``diagram.theme = ...`` switches it without computing a line again. The
same R290 chart is written in the four themes that come with CoolPlot:

* ``"default"``: for the screen, one colour per quantity, checked for
  colour vision deficiencies; isolines thin and in colour, the dome and the
  cycle in ink.
* ``"dark"``: the same on a dark background.
* ``"print"``: black and white, the families told apart by their dash
  patterns.
* ``"coolpack"``: the look of the CoolPack charts of the late 1990s.

How to derive a theme of your own is in the how-to guide on themes.

Run with:  python examples/themes.py
Writes theme_default.svg, theme_dark.svg, theme_print.svg and theme_coolpack.svg.
"""
from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer
from coolplot.thermo.cycles import simple_compression

diagram = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
diagram.set_lines("Q", num=11)
diagram.set_lines("T", num=8, rounding=True, labels=True)
diagram.set_lines("s", num=8, rounding=True)
diagram.set_lines("rho", num=6, rounding=True)
diagram.add_cycle(simple_compression(diagram.fluid, T_evap_C=-5.0, T_cond_C=45.0))

for theme in ("default", "dark", "print", "coolpack"):
    diagram.theme = theme
    diagram.title = 'R290, theme="{0}"'.format(theme)
    diagram.draw(SvgRenderer(width=700, height=500)).save("theme_{0}.svg".format(theme))
# Restyling computed nothing: every line came from the cache after the first theme
print("Lines computed for the last theme:", diagram.uncached_curves())
