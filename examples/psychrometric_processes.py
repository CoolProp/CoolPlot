# -*- coding: utf-8 -*-
"""
The basic air processes on a psychrometric chart
================================================

Six processes start from the same room air, 24 deg C and 50 % relative
humidity. Each one is a process of its own, with its own colour and legend
entry, and its end state is labelled with the change of enthalpy per kg of
dry air: what a coil or a humidifier adds (+) or removes (-). The default
theme has three styles for processes and uses them in turn; six processes
get their own colours here.

* Sensible heating and sensible cooling keep the humidity ratio
  (``"via": "sensible"``); sensible cooling has to stay above the dew
  point of the air, 12.9 deg C here.
* Cooling and dehumidification ends close to saturation, below that dew
  point, so water condenses on the coil.
* Evaporative cooling and desiccant dehumidification keep the enthalpy
  (``"via": "isenthalpic"``): water evaporates into the air, or a desiccant
  takes it out and releases its heat of sorption into the air.
* Steam humidification keeps the temperature (``"via": "isothermal"``),
  a good approximation for steam close to 100 deg C.

Run with:  python examples/psychrometric_processes.py
Writes psychrometric_processes.svg.
"""
from coolplot import LineStyle, MarkerStyle, PsychrometricChart
from coolplot.render.svg import SvgRenderer

chart = PsychrometricChart(T_range=(0, 45), W_range=(0, 20))   # sea level, deg C and g/kg
chart.title = "Air processes from 24 deg C and 50 %"
chart.set_default_lines()

room = {"T": 24, "RH": 50}
# Each end state is given by one property and the process that leads to it,
# or by two properties
end_states = {
    "Sensible heating": {"T": 38, "via": "sensible"},
    "Sensible cooling": {"T": 15, "via": "sensible"},
    "Cooling and dehumidification": {"T": 11, "RH": 95},
    "Evaporative cooling": {"T": 18, "via": "isenthalpic"},
    "Steam humidification": {"RH": 80, "via": "isothermal"},
    "Desiccant dehumidification": {"W": 5, "via": "isenthalpic"},
}
# One colour per process, apart from the colours of the chart's lines
colors = ["#c0392b", "#1b2631", "#7d3c98", "#b9770e", "#d81b60", "#6e2c00"]

print("{0:30s} {1:>8s} {2:>6s} {3:>8s} {4:>10s}".format("Process", "T/degC", "RH/%", "W/g/kg", "dh/kJ/kg"))
for (name, end), color in zip(end_states.items(), colors):
    line_style = LineStyle(color=color, width_pt=2.0, casing_color="white", casing_width_pt=1.5)
    marker_style = MarkerStyle(size_pt=6.0, face_color=color, edge_color="white")
    # add_cycle computes the states; the change of enthalpy then labels the
    # end state, and adding the process again under its name replaces it
    chart.add_cycle(name, [room, end], closed=False, numbers=False, line_style=line_style, marker_style=marker_style)
    start_state, end_state = chart.cycle_states(name).values()
    dh_kJ_kg = (end_state.h - start_state.h) * 1e-3
    chart.add_cycle(name, [room, end], closed=False, numbers=False, labels={2: "{0:+.1f} kJ/kg".format(dh_kJ_kg)},
                    line_style=line_style, marker_style=marker_style)
    print("{0:30s} {1:8.1f} {2:6.1f} {3:8.2f} {4:+10.1f}".format(
        name, end_state.T - 273.15, end_state.RH * 100, end_state.W * 1e3, dh_kJ_kg))

chart.draw(SvgRenderer(width=1000, height=700)).save("psychrometric_processes.svg")
