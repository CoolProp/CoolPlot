# -*- coding: utf-8 -*-
"""
Four ways to label the lines
============================

``Settings.labels.mode`` decides where the values of the lines go. The same
chart in the four modes:

* ``"rails"`` (the default): the bare values of each family in a row along
  one edge, with the symbol and unit in the legend.
* ``"edge"``: the full label, symbol, value and unit, just inside the
  frame where a line leaves the chart, turned along the line.
* ``"margin"``: outside the frame like a second set of tick labels; the
  plot area stays free of text.
* ``"inline"``: on the line itself, at ``position`` along it (0.5, the
  middle, by default).

In rails and edge mode the labels keep clear of the cycle and of each
other, and a label that does not fit is left out.

Run with:  python examples/label_modes.py
Writes label_modes.png.
"""
import matplotlib
matplotlib.use("Agg")   # this example only writes a file
import matplotlib.pyplot as plt

from coolplot import PropertyDiagram
from coolplot.render.mpl import MatplotlibRenderer
from coolplot.thermo.cycles import simple_compression

fig, axes = plt.subplots(2, 2, figsize=(14, 10), layout="constrained")
for mode, ax in zip(("rails", "edge", "margin", "inline"), axes.flat):
    diagram = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    diagram.set_lines("Q", num=11, labels=True)
    diagram.set_lines("T", num=10, rounding=True, labels=True)
    diagram.set_lines("s", num=8, rounding=True, labels=True)
    diagram.settings = diagram.settings.with_(labels={"mode": mode})
    diagram.add_cycle(simple_compression(diagram.fluid, T_evap_C=-5.0, T_cond_C=45.0))
    diagram.title = 'labels={{"mode": "{0}"}}'.format(mode)
    diagram.draw(MatplotlibRenderer(ax=ax))
fig.savefig("label_modes.png", dpi=90)
plt.close(fig)   # the file is the result; the gallery shows it once
print("Wrote label_modes.png")
