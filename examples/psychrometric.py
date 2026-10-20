# -*- coding: utf-8 -*-
"""A psychrometric chart with an air-conditioning process.

Outdoor air at 32 deg C and 50 % is cooled and dehumidified on a cooling
coil to 13 deg C and 95 %, then reheated to 20 deg C at the same humidity
ratio.

Run with:  python examples/psychrometric.py
Writes psychrometric.svg.
"""
from coolplot import PsychrometricChart
from coolplot.render.svg import SvgRenderer

chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))   # sea level, deg C and g/kg
chart.title = "Psychrometric chart, 1.013 bar"
chart.set_default_lines()
chart.add_cycle("Air conditioning", [
    {"T": 32, "RH": 50},    # 1 outdoor air
    {"T": 13, "RH": 95},    # 2 after the cooling coil
    {"T": 20, "W": 8.9},    # 3 after reheating, same humidity ratio as 2
], closed=False)
for number, state in enumerate(list(chart.cycle_states("Air conditioning").values()), start=1):
    print("{0}: T = {1:5.1f} deg C, RH = {2:5.1f} %, W = {3:5.2f} g/kg, h = {4:5.1f} kJ/kg".format(
        number, state.T - 273.15, state.RH * 100, state.W * 1e3, state.h * 1e-3))

chart.draw(SvgRenderer(width=1000, height=700)).save("psychrometric.svg")
