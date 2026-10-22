# -*- coding: utf-8 -*-
"""
A steam turbine on the Mollier h-s chart
========================================

The h-s chart of water, the Mollier chart of steam, is the chart of turbine
design: the work of a turbine is the drop of enthalpy, a vertical distance,
and the losses show as the step to the right in entropy. The chart is
zoomed in (``set_view``) on the region of superheated and slightly wet
steam where turbines work.

Live steam at 100 bar and 500 deg C expands to 0.1 bar. The isentropic
expansion (dashed, 1 to 2s) is the ideal; the real one with an isentropic
efficiency of 0.85 (``"via": "expansion"``) ends at 2, at a higher enthalpy
and a higher quality. The difference of the two enthalpy drops is the loss.

Run with:  python examples/steam_turbine_hs.py
Writes steam_turbine_hs.svg.
"""
from coolplot import LineStyle, MarkerStyle, PropertyDiagram
from coolplot.render.svg import SvgRenderer

eta_is = 0.85
live_steam = {"p": 100.0, "T": 500.0}   # bar, deg C

diagram = PropertyDiagram("HEOS::Water", "hs", units="engineering", tp_limits=[290.0, 870.0, 3e3, 2.5e7])
diagram.title = "Steam turbine, 100 bar and 500 deg C to 0.1 bar"
diagram.set_lines("Q", values=[0.8, 0.85, 0.9, 0.95, 1.0], labels=True)
diagram.set_lines("p", values=[0.05, 0.1, 0.5, 1, 5, 10, 50, 100], labels=True)
diagram.set_lines("T", values=[100, 200, 300, 400, 500, 600], labels=True)
diagram.set_view(x_limits=(5.8, 8.6), y_limits=(1900, 3700))   # kJ/kg/K and kJ/kg

real = [live_steam, {"p": 0.1, "via": "expansion", "eta_is": eta_is}]
diagram.add_cycle("Turbine", real, closed=False)
# The ideal expansion: dashed grey, its end labelled 2s, no state numbers
diagram.add_cycle("Isentropic", [live_steam, {"p": 0.1, "via": "isentropic"}], closed=False, numbers=False,
                  labels={2: "2s"}, line_style=LineStyle(color="#52514e", width_pt=1.5, dash="dashed"),
                  marker_style=MarkerStyle(size_pt=5.0, face_color="#52514e", edge_color="white"))

start, end = diagram.cycle_states("Turbine").values()
end_s = diagram.cycle_states("Isentropic")[2]
dh_kJ_kg = (start.h - end.h) * 1e-3
dh_s_kJ_kg = (start.h - end_s.h) * 1e-3
print("Isentropic enthalpy drop {0:6.1f} kJ/kg, exhaust quality {1:.3f}".format(dh_s_kJ_kg, end_s.Q))
print("Real enthalpy drop       {0:6.1f} kJ/kg, exhaust quality {1:.3f}".format(dh_kJ_kg, end.Q))
print("Loss                     {0:6.1f} kJ/kg".format(dh_s_kJ_kg - dh_kJ_kg))
# Added again under its name, it is replaced, now with a label at its end
diagram.add_cycle("Turbine", real, closed=False,
                  labels={2: "x = {0:.3f}, dh = {1:.0f} kJ/kg".format(end.Q, dh_kJ_kg)})

diagram.draw(SvgRenderer(width=800, height=800)).save("steam_turbine_hs.svg")
