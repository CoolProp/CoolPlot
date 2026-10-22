# -*- coding: utf-8 -*-
"""
A transcritical CO2 heat pump
=============================

CO2 (R744) has its critical point at 31 deg C and 74 bar, below the
temperatures a heat pump for hot water delivers. The compressor therefore
lifts the gas above the critical pressure, and the heat is given off in a
gas cooler instead of a condenser: there is no condensation, and the
temperature of the CO2 falls all the way through it (2 to 3), which suits
water heated from cold to hot. The isotherms above the dome show this: they
bend near the critical point but never run flat.

States: 1 evaporator outlet at 30 bar and 0 deg C (evaporating at
-5.6 deg C), 2 compressor outlet at 100 bar (isentropic efficiency 0.7),
3 gas cooler outlet at 35 deg C, 4 after the expansion valve.

Run with:  python examples/co2_transcritical.py
Writes co2_transcritical.svg.
"""
from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer

m_dot_kg_s = 0.05   # CO2 through the cycle

# T from -53 to 147 deg C, p from 5 to 140 bar, in SI units (K and Pa)
diagram = PropertyDiagram("HEOS::CO2", "ph", units="engineering", tp_limits=[220.0, 420.0, 5e5, 1.4e7])
diagram.title = "CO2 heat pump, gas cooler at 100 bar"
diagram.set_lines("Q", num=11, labels=True)
diagram.set_lines("T", values=list(range(-30, 151, 20)), labels=True)
diagram.set_lines("s", num=8, rounding=True, labels=True)

states = [
    {"p": 30.0, "T": 0.0},                                # 1 evaporator outlet
    {"p": 100.0, "via": "compression", "eta_is": 0.7},    # 2 compressor outlet
    {"p": 100.0, "T": 35.0},                              # 3 gas cooler outlet
    {"p": 30.0, "via": "isenthalpic"},                    # 4 after the expansion valve
]
diagram.add_cycle("Heat pump", states)
s = diagram.cycle_states("Heat pump")
Q_dot_gc_kW = m_dot_kg_s * (s[2].h - s[3].h) * 1e-3
Q_dot_evap_kW = m_dot_kg_s * (s[1].h - s[4].h) * 1e-3
W_dot_kW = m_dot_kg_s * (s[2].h - s[1].h) * 1e-3
diagram.add_cycle("Heat pump", states, labels={
    2: "{0:.0f} deg C".format(s[2].T - 273.15),
    3: "gas cooler {0:.1f} kW".format(Q_dot_gc_kW),
    4: "evaporator {0:.1f} kW".format(Q_dot_evap_kW)})

print("Gas cooler {0:5.2f} kW, evaporator {1:5.2f} kW, compressor {2:5.2f} kW".format(
    Q_dot_gc_kW, Q_dot_evap_kW, W_dot_kW))
print("COP heating {0:.2f}".format(Q_dot_gc_kW / W_dot_kW))
print("Evaporating at {0:.1f} deg C".format(s[4].T - 273.15))

diagram.draw(SvgRenderer(width=900, height=650)).save("co2_transcritical.svg")
