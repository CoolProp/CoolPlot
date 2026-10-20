# -*- coding: utf-8 -*-
"""
Two-stage cycles: one split cycle, two closed loops, and an economizer
======================================================================


The same two-stage flash tank cycle is drawn as one split cycle and as two
closed loops, next to a cycle with an economizer (vapour injection).

Run with:  python examples/two_stage_cycles.py
Writes two_stage_cycles.png.
"""
from dataclasses import replace

import matplotlib
matplotlib.use("Agg")   # this example only writes a file
import matplotlib.pyplot as plt

from coolplot import PropertyDiagram
from coolplot.render.mpl import MatplotlibRenderer
from coolplot.thermo.cycles import two_stage

FLUID = "HEOS::R290"


def diagram_with(cycle, title, loops=None):
    diagram = PropertyDiagram(FLUID, "ph", units="engineering", tp_limits="ACHP")
    diagram.title = title
    diagram.set_lines("Q", num=11)
    diagram.set_lines("T", num=10, rounding=True, labels=True)
    diagram.add_cycle(cycle, loops=loops)
    # Three panels side by side: put each legend inside its plot area
    axes_style = diagram.theme.axes
    diagram.theme = diagram.theme.with_(axes=replace(axes_style, legend=replace(axes_style.legend,
                                                                                location="lower right")))
    return diagram


flash = two_stage(FLUID, T_evap_C=-30.0, T_cond_C=45.0, intermediate="flash_tank")
economizer = two_stage(FLUID, T_evap_C=-30.0, T_cond_C=45.0, intermediate="economizer")

fig, axes = plt.subplots(1, 3, figsize=(18, 6), layout="constrained")
panels = [
    diagram_with(flash, "Flash tank, one split cycle"),
    diagram_with(flash, "Flash tank, two closed loops", loops=[[1, 2, 7, 8, 1], [3, 4, 5, 6, 3]]),
    diagram_with(economizer, "Economizer (vapour injection)"),
]
for diagram, ax in zip(panels, axes):
    diagram.draw(MatplotlibRenderer(ax=ax))
fig.savefig("two_stage_cycles.png", dpi=110)

for name, cycle in (("flash tank", flash), ("economizer", economizer)):
    r = cycle.result
    print("{0}: p_mid = {1:.2f} bar, COP cooling = {2:.2f}, m_dot ratio = {3:.3f}".format(
        name, r["p_mid_Pa"] * 1e-5, r["COP_cooling"], r["m_dot_ratio"]))
