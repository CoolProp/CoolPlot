# -*- coding: utf-8 -*-
"""
Evaporative cooling in a hot, dry climate
=========================================

Outdoor air at 38 deg C and 15 % relative humidity is cooled by evaporating
water, in two ways, and compared with a summer comfort zone (23 to 27 deg C,
30 to 60 %):

* Direct: the air flows through a wetted pad and follows its line of
  constant enthalpy (``"via": "isenthalpic"``) towards its wet-bulb
  temperature. A pad with a saturation effectiveness ``epsilon`` covers that
  share of the way:  T_out = T_in - epsilon * (T_in - Twb_in).
* Indirect, then direct: a heat exchanger first cools the air without
  adding water (``"via": "sensible"``), with a second, wetted air stream on
  the other side. The direct stage then starts from a lower wet-bulb
  temperature and reaches a colder supply.

The labels give the supply temperature and humidity of each. Both supplies
are colder and more humid than the comfort zone: evaporative cooling trades
temperature for humidity, and the room's heat load then warms the supply air
into the zone. The processes hide their state numbers and label the states
that matter instead.

Run with:  python examples/psychrometric_evaporative_cooling.py
Writes psychrometric_evaporative_cooling.svg.
"""
from coolplot import LineStyle, MarkerStyle, PsychrometricChart
from coolplot.render.svg import SvgRenderer

epsilon_direct = 0.85      # saturation effectiveness of the wetted pad
epsilon_indirect = 0.60    # wet-bulb effectiveness of the indirect heat exchanger

chart = PsychrometricChart(T_range=(10, 45), W_range=(0, 20))   # sea level, deg C and g/kg
chart.title = "Evaporative cooling of outdoor air at 38 \u00b0C and 15 %"
chart.set_default_lines()
chart.add_zone("Comfort zone", T_range=(23, 27), RH_range=(30, 60), label="comfort zone",
               line_style=LineStyle(color="#7f8c8d", width_pt=1.5, dash="dashed"))

outdoor = {"T": 38, "RH": 15}
outdoor_state = chart.state(outdoor)
T_outdoor_C, Twb_outdoor_C = outdoor_state.T - 273.15, outdoor_state.Twb - 273.15


def supply_label(state):
    """Temperature and relative humidity of a supply state, for its label."""
    return "supply {0:.1f} \u00b0C, {1:.0f} %".format(state.T - 273.15, state.RH * 100)


def style(color):
    """A line and markers in one colour, with a white casing that lifts them off the chart's lines."""
    return dict(line_style=LineStyle(color=color, width_pt=2.0, casing_color="white", casing_width_pt=1.5),
                marker_style=MarkerStyle(size_pt=6.0, face_color=color, edge_color="white"))


# Direct evaporative cooling --------------------------------------------------
T_direct_C = T_outdoor_C - epsilon_direct * (T_outdoor_C - Twb_outdoor_C)
direct = [outdoor, {"T": T_direct_C, "via": "isenthalpic"}]
chart.add_cycle("Direct", direct, closed=False, numbers=False, **style("#b9770e"))
direct_supply = chart.cycle_states("Direct")[2]
chart.add_cycle("Direct", direct, closed=False, numbers=False, **style("#b9770e"),
                labels={1: "outdoor air", 2: supply_label(direct_supply)})

# Indirect, then direct --------------------------------------------------------
# The indirect stage cools towards the outdoor wet-bulb temperature (the
# wetted secondary air) at the outdoor humidity ratio
T_indirect_C = T_outdoor_C - epsilon_indirect * (T_outdoor_C - Twb_outdoor_C)
Twb_indirect_C = chart.state({"T": T_indirect_C, "W": outdoor_state.W * 1e3}).Twb - 273.15
T_two_stage_C = T_indirect_C - epsilon_direct * (T_indirect_C - Twb_indirect_C)
two_stage = [outdoor,
             {"T": T_indirect_C, "via": "sensible"},        # after the indirect heat exchanger
             {"T": T_two_stage_C, "via": "isenthalpic"}]    # after the wetted pad
chart.add_cycle("Indirect, then direct", two_stage, closed=False, numbers=False, **style("#1f4e9c"))
two_stage_supply = chart.cycle_states("Indirect, then direct")[3]
chart.add_cycle("Indirect, then direct", two_stage, closed=False, numbers=False, **style("#1f4e9c"),
                labels={2: "after the indirect stage", 3: supply_label(two_stage_supply)})

print("Outdoor air: T = {0:.1f} deg C, wet bulb {1:.1f} deg C, W = {2:.2f} g/kg".format(
    T_outdoor_C, Twb_outdoor_C, outdoor_state.W * 1e3))
for name, state in (("Direct", direct_supply), ("Indirect, then direct", two_stage_supply)):
    print("{0:22s} supply T = {1:5.1f} deg C, RH = {2:5.1f} %, W = {3:5.2f} g/kg".format(
        name, state.T - 273.15, state.RH * 100, state.W * 1e3))

chart.draw(SvgRenderer(width=1000, height=700)).save("psychrometric_evaporative_cooling.svg")
