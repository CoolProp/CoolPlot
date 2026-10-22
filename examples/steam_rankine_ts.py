# -*- coding: utf-8 -*-
"""
A steam power plant: the Rankine cycle on a T-s chart
=====================================================

A simple Rankine cycle with superheat, as in a small steam power plant: the
feed pump (1 to 2) raises the condensate to 100 bar, the boiler heats,
evaporates and superheats it to 500 deg C (2 to 3), the turbine expands the
live steam to the condenser pressure of 0.1 bar (3 to 4), and the condenser
turns the wet exhaust steam back into liquid (4 to 1).

On the T-s chart the heat the boiler takes in is the area under 2-3, the
heat the condenser gives off the area under 4-1; the net work is the area
inside the cycle. The cycle model :func:`coolplot.thermo.cycles.rankine`
computes the states with isentropic efficiencies of 0.85 for the turbine
and 0.75 for the pump.

Run with:  python examples/steam_rankine_ts.py
Writes steam_rankine_ts.svg.
"""
from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer
from coolplot.thermo.cycles import rankine

# T from 17 to 597 deg C, p from 0.03 to 250 bar, in SI units (K and Pa)
diagram = PropertyDiagram("HEOS::Water", "Ts", units="engineering", tp_limits=[290.0, 870.0, 3e3, 2.5e7])
diagram.title = "Steam Rankine cycle, 100 bar and 500 deg C"
diagram.set_lines("Q", num=11, labels=True)
diagram.set_lines("p", values=[0.1, 1, 10, 100], labels=True)
diagram.set_lines("h", values=[1000, 2000, 3000], labels=True)

cycle = rankine(diagram.fluid, p_high_Pa=100e5, p_low_Pa=0.1e5, T_live_C=500.0)
diagram.add_cycle(cycle, labels={3: "live steam", 4: "turbine exhaust"})

r = cycle.result
print("Heat in   {0:7.1f} kJ/kg".format(r["q_in_J_kg"] * 1e-3))
print("Turbine   {0:7.1f} kJ/kg".format(r["w_turbine_J_kg"] * 1e-3))
print("Pump      {0:7.1f} kJ/kg".format(r["w_pump_J_kg"] * 1e-3))
print("Efficiency {0:6.1f} %".format(r["eta_th"] * 100))
exhaust = cycle.state(4)
print("Exhaust steam: {0:.1f} deg C, quality {1:.3f}".format(exhaust.T - 273.15, exhaust.Q))

diagram.draw(SvgRenderer(width=900, height=650)).save("steam_rankine_ts.svg")
