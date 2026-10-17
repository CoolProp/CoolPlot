# -*- coding: utf-8 -*-
"""
A zeotropic refrigerant blend: R32/R125 (70/30 by mole)
=======================================================


For mixtures the isolines are traced point by point (with CoolProp 8),
the saturation dome comes from CoolProp's phase envelope, and isotherms
show the temperature glide inside the dome. Expect a few seconds (a
line of a blend costs about a second); pure fluids take a fraction of
a second.

Run with:  python examples/refrigerant_blend.py
Writes R32_R125_ph.svg.
"""
import time

from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer

diagram = PropertyDiagram("HEOS::R32[0.7]&R125[0.3]", "ph", units="engineering", tp_limits="ACHP")
diagram.title = "R32/R125 (0.7/0.3)"
diagram.set_lines("Q", num=6, labels=True)
diagram.set_lines("T", num=6, rounding=True, labels=True)
diagram.set_lines("s", num=5, rounding=True, labels=True)
# Every point along a path is a flash of the blend (about 0.1 s each), so
# the paths get fewer steps than the default of 20.
diagram.add_cycle("Heat pump", [
    {"p": 5.0, "Q": 1.0},
    {"p": 25.0, "via": "compression", "eta_is": 0.7},
    {"p": 25.0, "Q": 0.0},
    {"p": 5.0, "via": "isenthalpic"},
], steps=6)

start = time.time()
renderer = diagram.draw(SvgRenderer(width=900, height=650))
renderer.save("R32_R125_ph.svg")
print("drawn in {0:.1f} s".format(time.time() - start))
