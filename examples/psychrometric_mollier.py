# -*- coding: utf-8 -*-
"""
An air handling unit on the Mollier h,x chart
=============================================

The Mollier chart is the usual psychrometric chart in Europe (DIN 1946,
VDI 4670): the humidity ratio x runs across, and up runs a temperature scale
that is linear in the specific enthalpy h, so the lines of constant enthalpy
are straight and fall to the right, and the isotherms rise slightly with x.
The relative humidity is called phi. ``style="mollier"`` draws it; the
states, processes and labels are given as on the psychrometric chart, with
the same keys (``W`` for x, ``RH`` for phi).

Summer operation of an air handling unit for 2.0 kg/s of dry air with 30 %
outdoor air: outdoor air (1) mixes with return air (2) to (3), the cooling
coil cools and dries it to (4), and a reheater warms it at the same x to the
supply state (5). Mixing is a straight line on this chart too, since h and x
are both linear in it.

Run with:  python examples/psychrometric_mollier.py
Writes psychrometric_mollier.svg.
"""
from coolplot import LineStyle, MarkerStyle, PsychrometricChart
from coolplot.render.svg import SvgRenderer

m_dot_supply_kg_s = 2.0     # dry air through the unit
outdoor_share = 0.3         # share of outdoor air in the supply, by mass of dry air
m_dot_outdoor_kg_s = outdoor_share * m_dot_supply_kg_s
m_dot_return_kg_s = m_dot_supply_kg_s - m_dot_outdoor_kg_s

# T_range is the range of the vertical temperature scale, W_range that of x
chart = PsychrometricChart(T_range=(0, 40), W_range=(0, 20), style="mollier")
chart.title = "Air handling unit in summer, Mollier h,x chart"
chart.set_default_lines()
chart.add_zone("Comfort zone", T_range=(20, 26), RH_range=(30, 60), label="comfort zone",
               line_style=LineStyle(color="#7f8c8d", width_pt=1.5, dash="dashed"))

outdoor, room = {"T": 32, "RH": 40}, {"T": 25, "RH": 50}
summer = {
    1: outdoor,
    2: room,
    3: chart.mix(outdoor, room, m_dot_outdoor_kg_s, m_dot_return_kg_s),
    4: {"T": 13, "RH": 95},              # leaving the cooling coil
    5: {"T": 17, "via": "sensible"},     # after the reheater, the supply air
}
loops = [[1, 3], [2, 3, 4, 5, 2]]        # outdoor and return air into the mixing box, then on
style = dict(line_style=LineStyle(color="#c0392b", width_pt=2.0, casing_color="white", casing_width_pt=1.5),
             marker_style=MarkerStyle(size_pt=6.0, face_color="#c0392b", edge_color="white"))
chart.add_cycle("Summer", summer, loops=loops, **style)
states = chart.cycle_states("Summer")
Q_dot_coil_kW = m_dot_supply_kg_s * (states[4].h - states[3].h) * 1e-3
Q_dot_reheat_kW = m_dot_supply_kg_s * (states[5].h - states[4].h) * 1e-3
chart.add_cycle("Summer", summer, loops=loops, **style, labels={
    3: "mixed, {0:.0f} % outdoor air".format(outdoor_share * 100),
    4: "cooling coil {0:.1f} kW".format(Q_dot_coil_kW),
    5: "reheat {0:+.1f} kW".format(Q_dot_reheat_kW)})

print("Summer, Mollier h,x chart")
for number, state in states.items():
    print("  {0}: T = {1:5.1f} deg C, phi = {2:5.1f} %, x = {3:5.2f} g/kg, h = {4:5.1f} kJ/kg".format(
        number, state.T - 273.15, state.RH * 100, state.W * 1e3, state.h * 1e-3))
print("Cooling coil {0:.1f} kW, reheat {1:.1f} kW".format(Q_dot_coil_kW, Q_dot_reheat_kW))

chart.draw(SvgRenderer(width=800, height=900)).save("psychrometric_mollier.svg")
