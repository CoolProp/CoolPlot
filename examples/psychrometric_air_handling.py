# -*- coding: utf-8 -*-
"""
Summer and winter operation of an air handling unit
===================================================

An air handling unit supplies 2.0 kg/s of dry air to a room; 30 % of it is
outdoor air, the rest is air returned from the room. Both seasons are drawn
on one chart, each as one process with the states numbered 1 to 5, over a
comfort zone of 20 to 26 deg C and 30 to 60 % relative humidity.

Summer: outdoor air (1) mixes with return air (2) to (3), the cooling coil
cools and dries it to (4), and a reheater warms it at the same humidity ratio
to the supply state (5). In the room the supply air takes up heat and
moisture and becomes room air again (5 to 2); the sensible heat ratio of that
load is the share of the heat that raises the temperature.

Winter: the mixed air (3) is heated at the same humidity ratio (4), and a
steam humidifier adds water at about the same temperature (5), up to the
humidity ratio of the room.

The labels give the duty of each component; with ``chart.mix`` the mixed
state follows from the two air flows.

Run with:  python examples/psychrometric_air_handling.py
Writes psychrometric_air_handling.svg.
"""
from coolplot import LineStyle, MarkerStyle, PsychrometricChart
from coolplot.render.svg import SvgRenderer

m_dot_supply_kg_s = 2.0     # dry air through the unit
outdoor_share = 0.3         # share of outdoor air in the supply, by mass of dry air
m_dot_outdoor_kg_s = outdoor_share * m_dot_supply_kg_s
m_dot_return_kg_s = m_dot_supply_kg_s - m_dot_outdoor_kg_s

chart = PsychrometricChart(T_range=(-10, 40), W_range=(0, 20))   # sea level, deg C and g/kg
chart.title = "Air handling unit, summer and winter"
chart.set_default_lines()
chart.add_zone("Comfort zone", T_range=(20, 26), RH_range=(30, 60), label="comfort zone",
               line_style=LineStyle(color="#7f8c8d", width_pt=1.5, dash="dashed"))


def kW(m_dot_kg_s, dh_J_kg):
    """The heat flow in kW of a mass flow of dry air whose enthalpy changes by dh."""
    return m_dot_kg_s * dh_J_kg * 1e-3


def season_style(color):
    """A line and markers in one colour, with a white casing that lifts them off the chart's lines."""
    return dict(line_style=LineStyle(color=color, width_pt=2.0, casing_color="white", casing_width_pt=1.5),
                marker_style=MarkerStyle(size_pt=6.0, face_color=color, edge_color="white"))


# Summer ----------------------------------------------------------------------
outdoor, room = {"T": 32, "RH": 40}, {"T": 25, "RH": 50}
summer = {
    1: outdoor,
    2: room,
    3: chart.mix(outdoor, room, m_dot_outdoor_kg_s, m_dot_return_kg_s),
    4: {"T": 13, "RH": 95},              # leaving the cooling coil
    5: {"T": 17, "via": "sensible"},     # after the reheater, the supply air
}
# Outdoor and return air into the mixing box, then through the unit and the room
summer_loops = [[1, 3], [2, 3, 4, 5, 2]]
summer_style = season_style("#c0392b")
chart.add_cycle("Summer", summer, loops=summer_loops, **summer_style)
summer_states = chart.cycle_states("Summer")
# The coil duty leaves out the enthalpy of the condensate, about 0.5 % here
Q_dot_coil_kW = kW(m_dot_supply_kg_s, summer_states[4].h - summer_states[3].h)
Q_dot_reheat_kW = kW(m_dot_supply_kg_s, summer_states[5].h - summer_states[4].h)
# Room load: the sensible part warms the supply air at its own humidity ratio
# to the room temperature, the rest is the latent part (moisture)
supply, room_air = summer_states[5], summer_states[2]
dh_sensible_J_kg = chart.state({"T": room_air.T, "W": supply.W}, units="SI").h - supply.h
SHR = dh_sensible_J_kg / (room_air.h - supply.h)
chart.add_cycle("Summer", summer, loops=summer_loops, **summer_style, labels={
    2: "room, SHR {0:.2f}".format(SHR),
    3: "mixed, {0:.0f} % outdoor air".format(outdoor_share * 100),
    4: "cooling coil {0:.1f} kW".format(Q_dot_coil_kW),
    5: "reheat {0:+.1f} kW".format(Q_dot_reheat_kW)})

# Winter ----------------------------------------------------------------------
outdoor, room = {"T": -5, "RH": 80}, {"T": 21, "RH": 40}
W_room_g_kg = chart.state(room).W * 1e3
winter = {
    1: outdoor,
    2: room,
    3: chart.mix(outdoor, room, m_dot_outdoor_kg_s, m_dot_return_kg_s),
    4: {"T": 28, "via": "sensible"},                   # after the heating coil
    5: {"W": W_room_g_kg, "via": "isothermal"},        # after the steam humidifier, the supply air
}
# The supply air reaches the humidity ratio of the room: no latent load in winter
winter_loops = [[1, 3], [2, 3, 4, 5, 2]]
winter_style = season_style("#1f4e9c")
chart.add_cycle("Winter", winter, loops=winter_loops, **winter_style)
winter_states = chart.cycle_states("Winter")
Q_dot_heating_kW = kW(m_dot_supply_kg_s, winter_states[4].h - winter_states[3].h)
m_dot_steam_kg_h = m_dot_supply_kg_s * (winter_states[5].W - winter_states[4].W) * 3600.0
chart.add_cycle("Winter", winter, loops=winter_loops, **winter_style, labels={
    4: "heating coil {0:+.1f} kW".format(Q_dot_heating_kW),
    5: "steam {0:.1f} kg/h".format(m_dot_steam_kg_h)})

for season, states in (("Summer", summer_states), ("Winter", winter_states)):
    print(season)
    for number, state in states.items():
        print("  {0}: T = {1:5.1f} deg C, RH = {2:5.1f} %, W = {3:5.2f} g/kg, h = {4:5.1f} kJ/kg".format(
            number, state.T - 273.15, state.RH * 100, state.W * 1e3, state.h * 1e-3))
print("Cooling coil {0:.1f} kW, reheat {1:.1f} kW, room SHR {2:.2f}".format(Q_dot_coil_kW, Q_dot_reheat_kW, SHR))
print("Heating coil {0:.1f} kW, steam {1:.1f} kg/h".format(Q_dot_heating_kW, m_dot_steam_kg_h))

chart.draw(SvgRenderer(width=1000, height=700)).save("psychrometric_air_handling.svg")
