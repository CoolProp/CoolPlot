# -*- coding: utf-8 -*-
"""
A CoolPack chart, for old times' sake
=====================================

Before CoolProp there was CoolPack: a free collection of refrigeration
programs from the Technical University of Denmark (DTU), first released in
1996. Its "Refrigeration Utilities" drew the log(p),h-diagrams that a
generation of refrigeration engineers printed, annotated and pinned above
their desks. The ``"coolpack"`` theme brings that look back:

* Times on a white sheet with a dense light grey grid and no legend.
* A black saturation curve, red isotherms, blue isentropes, green
  isochores and navy lines of constant vapour quality, in the colours of
  the 16 colour Windows palette.
* Every value label in the colour of its line, so the families can be
  told apart without a legend.

The chart is the R290 diagram of the CoolPack tutorial, with a simple
refrigeration cycle on top. Only the look is old: the properties come from
CoolProp. CoolPack is a program of DTU; the theme only imitates the look
of its charts and is not connected to DTU or the CoolPack authors.

Run with:  python examples/coolpack.py
Writes coolpack.svg.
"""
from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer
from coolplot.thermo.cycles import simple_compression

diagram = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP", theme="coolpack")
diagram.set_lines("Q", num=11, labels=True)
diagram.set_lines("T", num=16, rounding=True, labels=True)
diagram.set_lines("s", num=12, rounding=True, labels=True)
diagram.set_lines("rho", num=8, rounding=True, labels=True)

cycle = simple_compression(diagram.fluid, T_evap_C=-10.0, T_cond_C=35.0, dT_sh_K=10.0, dT_sc_K=2.0, eta_is=0.7)
COP_cooling = cycle.result["COP_cooling"]
diagram.add_cycle(cycle)
diagram.title = "R290, one stage cycle, COP {0:.2f}".format(COP_cooling)

diagram.draw(SvgRenderer(width=900, height=650)).save("coolpack.svg")
print("COP cooling: {0:.2f}".format(COP_cooling))
