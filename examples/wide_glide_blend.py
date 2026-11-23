# -*- coding: utf-8 -*-
"""
A blend with a wide glide: R436A in a heat pump
===============================================

R436A is propane (R290) and isobutane (R600a), 56/44 by mass. The two
boil far apart, so the blend evaporates and condenses over a range of
temperatures, the glide: about 7.8 K in the evaporator and 6.3 K in the
condenser of this heat pump, evaporating at a dew point of -5 deg C and
condensing at a bubble point of 45 deg C.

The isotherms slope down through the dome instead of running along the
isobars, and the lines of constant quality fan out between the bubble
and the dew line. Every saturation state on those lines is checked to
be one whose liquid and vapour add up to the blend: CoolProp 8.0 gave a
wrong state on the cold part of the lines of intermediate quality of
R436A (3 % off in pressure at 140 K), which CoolProp 8.1 fixes for most
temperatures and CoolPlot leaves out where it does not (CoolProp issue
3585). CoolProp 8.1 is
recommended for blends.

Run with:  python examples/wide_glide_blend.py
Writes R436A_ph.svg.
"""
import time

from CoolProp.CoolProp import PropsSI

from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer

FLUID = "HEOS::R436A.mix"
T_evap_dew_C = -5.0     # dew point at the evaporator outlet
T_cond_bubble_C = 45.0  # bubble point at the condenser outlet

# The saturation pressures and the glide at each, from CoolProp directly
p_evap_Pa = PropsSI("P", "T", T_evap_dew_C + 273.15, "Q", 1, FLUID)
p_cond_Pa = PropsSI("P", "T", T_cond_bubble_C + 273.15, "Q", 0, FLUID)
T_evap_bubble_C = PropsSI("T", "P", p_evap_Pa, "Q", 0, FLUID) - 273.15
T_cond_dew_C = PropsSI("T", "P", p_cond_Pa, "Q", 1, FLUID) - 273.15
dT_glide_evap_K = T_evap_dew_C - T_evap_bubble_C
dT_glide_cond_K = T_cond_dew_C - T_cond_bubble_C
print("Evaporator: {0:.2f} bar, {1:.1f} to {2:.1f} deg C, glide {3:.1f} K".format(
    p_evap_Pa / 1e5, T_evap_bubble_C, T_evap_dew_C, dT_glide_evap_K))
print("Condenser:  {0:.2f} bar, {1:.1f} to {2:.1f} deg C, glide {3:.1f} K".format(
    p_cond_Pa / 1e5, T_cond_dew_C, T_cond_bubble_C, dT_glide_cond_K))

diagram = PropertyDiagram(FLUID, "ph", units="engineering", tp_limits="ACHP")
diagram.title = "R436A (R290/R600a 56/44 by mass)"
diagram.set_lines("Q", num=11, labels=True)
diagram.set_lines("T", num=8, rounding=True, labels=True)
diagram.set_lines("s", num=5, rounding=True, labels=True)
# Engineering units: pressures in bar. Every point along a path is a flash
# of the blend, so the paths get fewer steps than the default of 20.
p_evap_bar = p_evap_Pa / 1e5
p_cond_bar = p_cond_Pa / 1e5
diagram.add_cycle("Heat pump", [
    {"p": p_evap_bar, "Q": 1.0},
    {"p": p_cond_bar, "via": "compression", "eta_is": 0.7},
    {"p": p_cond_bar, "Q": 0.0},
    {"p": p_evap_bar, "via": "isenthalpic"},
], steps=6)

start = time.time()
renderer = diagram.draw(SvgRenderer(width=900, height=650))
renderer.save("R436A_ph.svg")
print("drawn in {0:.1f} s".format(time.time() - start))
