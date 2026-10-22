# -*- coding: utf-8 -*-
"""
An organic Rankine cycle (ORC) with R245fa
==========================================

An ORC turns heat at moderate temperatures (geothermal water, waste heat,
solar heat) into work. It is a Rankine cycle, see the steam example, with
an organic fluid that boils at a lower temperature than water; here R245fa
evaporating at 20 bar (about 122 deg C) and condensing at 2 bar (about
33 deg C).

R245fa is a dry fluid: the saturated vapour line leans to the right on the
T-s chart, so the expansion from saturated vapour (3) stays in the
superheated gas and the turbine needs no superheat. The exhaust (4) is
still well above the condensing temperature; many ORC plants pass it
through a recuperator that preheats the liquid after the pump. The preset
``tp_limits="ORC"`` covers 0 to 400 deg C.

Run with:  python examples/orc_ts.py
Writes orc_ts.svg.
"""
from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer
from coolplot.thermo.cycles import rankine

diagram = PropertyDiagram("HEOS::R245fa", "Ts", units="engineering", tp_limits="ORC")
diagram.title = "ORC with R245fa, 20 bar to 2 bar"
diagram.set_lines("Q", num=11, labels=True)
diagram.set_lines("p", values=[1, 2, 5, 10, 20, 30], labels=True)

cycle = rankine(diagram.fluid, p_high_Pa=20e5, p_low_Pa=2e5)   # saturated vapour into the turbine
exhaust = cycle.state(4)
T_cond_C = cycle.state(1).T - 273.15
diagram.add_cycle(cycle, labels={4: "exhaust {0:.0f} deg C".format(exhaust.T - 273.15)})

r = cycle.result
print("Evaporating {0:.1f} deg C, condensing {1:.1f} deg C".format(cycle.state(3).T - 273.15, T_cond_C))
print("Exhaust {0:.1f} deg C, {1:.1f} K above the condensing temperature".format(
    exhaust.T - 273.15, exhaust.T - 273.15 - T_cond_C))
print("Efficiency {0:.1f} %".format(r["eta_th"] * 100))

diagram.draw(SvgRenderer(width=900, height=650)).save("orc_ts.svg")
