# -*- coding: utf-8 -*-
"""
Three refrigerants in the same heat pump
========================================

The same single-stage heat pump, evaporating at -5 deg C and condensing at
45 deg C with 5 K of superheat, 2 K of subcooling and an isentropic
efficiency of 0.7, computed for propane (R290), R32 and R1234yf with
:func:`coolplot.thermo.cycles.simple_compression` and drawn side by side
with matplotlib.

The charts and the table below show the differences: R32 works at almost
twice the pressures of propane and leaves the compressor hottest, about
110 deg C; R1234yf has the smallest enthalpy differences, so more than
twice as much of it has to flow for the same heating duty as of propane,
which has the best COP of the three in this cycle.

Run with:  python examples/refrigerant_comparison.py
Writes refrigerant_comparison.png.
"""
import matplotlib
matplotlib.use("Agg")   # this example only writes a file
import matplotlib.pyplot as plt

from coolplot import PropertyDiagram
from coolplot.render.mpl import MatplotlibRenderer
from coolplot.thermo.cycles import simple_compression

FLUIDS = ["R290", "R32", "R1234yf"]
Q_dot_cond_kW = 10.0   # heating duty, for the mass flow

fig, axes = plt.subplots(1, 3, figsize=(18, 6), layout="constrained")
print("{0:8s} {1:>8s} {2:>8s} {3:>10s} {4:>11s} {5:>8s}".format(
    "Fluid", "p_evap", "p_cond", "T_out", "m_dot", "COP"))
print("{0:8s} {1:>8s} {2:>8s} {3:>10s} {4:>11s} {5:>8s}".format("", "bar", "bar", "deg C", "kg/s", "heating"))
for fluid, ax in zip(FLUIDS, axes):
    diagram = PropertyDiagram("HEOS::" + fluid, "ph", units="engineering", tp_limits="ACHP")
    diagram.set_lines("Q", num=11)
    diagram.set_lines("T", values=list(range(-40, 121, 20)), labels=True)
    cycle = simple_compression(diagram.fluid, T_evap_C=-5.0, T_cond_C=45.0, dT_sh_K=5.0, dT_sc_K=2.0, eta_is=0.7)
    diagram.add_cycle(fluid, cycle)   # the computed cycle, under the name of the fluid
    r = cycle.result
    diagram.title = "{0}: COP heating {1:.2f}".format(fluid, r["COP_heating"])
    diagram.draw(MatplotlibRenderer(ax=ax))
    m_dot_kg_s = Q_dot_cond_kW * 1e3 / r["q_cond_J_kg"]
    print("{0:8s} {1:8.2f} {2:8.2f} {3:10.1f} {4:11.4f} {5:8.2f}".format(
        fluid, r["p_evap_Pa"] * 1e-5, r["p_cond_Pa"] * 1e-5, r["T_comp_out_K"] - 273.15, m_dot_kg_s,
        r["COP_heating"]))
fig.savefig("refrigerant_comparison.png", dpi=110)
plt.close(fig)   # the file is the result; the gallery shows it once
