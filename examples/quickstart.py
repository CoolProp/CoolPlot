# -*- coding: utf-8 -*-
"""The same diagram drawn by two different backends.

Run with:  python examples/quickstart.py
Writes R290_ph.png (matplotlib) and R290_ph.svg (no dependencies).
"""
from CoolPlot import PropertyDiagram
from CoolPlot.render.svg import SvgRenderer

diagram = PropertyDiagram("HEOS::R290", "ph", units="EUR", tp_limits="ACHP")
diagram.set_isolines("Q", num=11)
diagram.set_isolines("T", num=12, rounding=True, labels=True)
diagram.set_isolines("s", num=10, rounding=True)
scene = diagram.update_scene()

svg = SvgRenderer(width=900, height=650)
svg.sync(scene)
svg.save("R290_ph.svg")

try:
    from CoolPlot.render.mpl import MatplotlibRenderer
except ImportError:
    print("matplotlib is not installed, only the SVG was written.")
else:
    mpl = MatplotlibRenderer(use_pyplot=False)
    mpl.sync(scene)
    mpl.save("R290_ph.png", dpi=150)
