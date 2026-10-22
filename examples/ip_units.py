# -*- coding: utf-8 -*-
"""
An air conditioner in IP units (deg F, psi, Btu/lb)
===================================================

The same chart in the units of US practice: ``units="IP"`` shows
temperatures in deg F, pressures in psi (absolute), enthalpies in Btu/lb
and entropies in Btu/lb/R. Every value given to the chart is in these
units too, the line values and the states of the cycle alike; the chart
keeps SI values inside, so ``diagram.units = "engineering"`` would redraw
it in deg C and bar without computing anything again.

The cycle is an R134a air conditioner: the evaporator at 35 psi (about
23 deg F) with 7 F of superheat, the condenser at 170 psi (about 114 deg F)
with the liquid subcooled to 110 deg F, and a compressor with an
isentropic efficiency of 0.7.

Run with:  python examples/ip_units.py
Writes ip_units.svg.
"""
from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer

diagram = PropertyDiagram("HEOS::R134a", "ph", units="IP", tp_limits="ACHP")
diagram.title = "R134a air conditioner in IP units"
diagram.set_lines("Q", num=11, labels=True)
diagram.set_lines("T", values=list(range(-40, 241, 40)), labels=True)   # deg F
diagram.set_lines("s", num=8, rounding=True, labels=True)
diagram.add_cycle("Air conditioner", [
    {"p": 35.0, "T": 30.0},                               # 1 evaporator outlet, psi and deg F
    {"p": 170.0, "via": "compression", "eta_is": 0.7},    # 2 compressor outlet
    {"p": 170.0, "T": 110.0},                             # 3 condenser outlet, subcooled
    {"p": 35.0, "via": "isenthalpic"},                    # 4 after the expansion valve
])

states = diagram.cycle_states("Air conditioner", units="IP")
for number, state in states.items():
    print("{0}: T = {1:6.1f} F, p = {2:5.1f} psi, h = {3:6.1f} Btu/lb".format(
        number, state["T"], state["p"], state["h"]))
q_evap = states[1]["h"] - states[4]["h"]
w_comp = states[2]["h"] - states[1]["h"]
print("Cooling {0:.1f} Btu/lb, compressor {1:.1f} Btu/lb, COP cooling {2:.2f}, EER {3:.1f}".format(
    q_evap, w_comp, q_evap / w_comp, 3.412 * q_evap / w_comp))

diagram.draw(SvgRenderer(width=900, height=650)).save("ip_units.svg")
