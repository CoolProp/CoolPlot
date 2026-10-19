# -*- coding: utf-8 -*-
"""A log(p)-h chart of propane with a heat pump cycle, drawn by two backends.

Run with:  python examples/quickstart.py
Writes R290_ph.svg (no dependencies) and R290_ph.png (needs matplotlib).
"""
from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer
from coolplot.thermo.cycles import simple_compression

diagram = PropertyDiagram("HEOS::R290", "ph", units="EUR", tp_limits="ACHP")
diagram.title = "R290 heat pump"
diagram.set_isolines("Q", num=11, labels=True)
diagram.set_isolines("T", num=12, rounding=True, labels=True)
diagram.set_isolines("s", num=10, rounding=True, labels=True)

cycle = simple_compression(diagram.fluid, T_evap_C=-5.0, T_cond_C=45.0, dT_sh_K=5.0, dT_sc_K=2.0, eta_is=0.7)
diagram.add_cycle(cycle)
print("COP heating: {0:.2f}".format(cycle.result["COP_heating"]))

# draw() lays out the labels for the size of the renderer's plot area
svg = diagram.draw(SvgRenderer(width=900, height=650))
svg.save("R290_ph.svg")

try:
    from coolplot.render.mpl import MatplotlibRenderer
except ImportError:
    print("matplotlib is not installed, only the SVG was written.")
else:
    png = diagram.draw(MatplotlibRenderer(use_pyplot=False))
    png.save("R290_ph.png", dpi=150)
