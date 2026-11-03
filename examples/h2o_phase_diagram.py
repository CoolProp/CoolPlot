# -*- coding: utf-8 -*-
"""
A phase diagram of water
========================

The same kind of chart as the phase diagram of CO2, for water. Two things
set water apart:

- The triple point lies at 0.01 deg C and 6.1 mbar, far below atmospheric
  pressure, so at 1 bar water melts at 0 deg C and boils at 100 deg C.
- Ordinary ice (ice Ih) is less dense than liquid water, so its melting
  line leans to the left: more pressure melts ice at a lower temperature,
  down to -22 deg C at about 2090 bar. Above that pressure denser forms
  of ice (III, V, VI, ...) take over and the melting line rises again.
  The points where it changes direction are triple points of liquid water
  and two kinds of ice; the boundaries between the kinds of ice are not
  drawn.

CoolPlot draws the vapour pressure curve. The other parts are added in
this script with matplotlib, on the axes of the CoolPlot chart:

- the melting line from CoolProp (``AbstractState.melting_line``, the
  IAPWS melting curves of the ices),
- the sublimation line of ice Ih from the IAPWS (2011) equation, since
  CoolProp does not model the solid phase,
- the regions, the triple point, the critical point and the melting and
  boiling points at atmospheric pressure.

Because these extras are matplotlib artists, they appear in the PNG and
PDF output of the matplotlib renderer only, not in the SVG, PDF or Plotly
output of the other renderers.

Run with:  python examples/h2o_phase_diagram.py
Writes h2o_phase_diagram.png (needs matplotlib).
"""
import numpy as np

import matplotlib
matplotlib.use("Agg")   # this example only writes a file

import CoolProp
from coolplot import PropertyDiagram
from coolplot.render.mpl import MatplotlibRenderer

# Triple point and critical point of water in SI units (K and Pa)
state = CoolProp.AbstractState("HEOS", "Water")
T_triple_K = state.Ttriple()
p_triple_Pa = CoolProp.CoolProp.PropsSI("ptriple", "Water")
T_crit_K = state.T_critical()
p_crit_Pa = state.p_critical()

# The part of the chart to show, in the chart's units (deg C and bar)
T_view_C = (-40.0, 500.0)
p_view_bar = (1e-4, 1e4)


def p_sublimation_Pa(T_K):
    """Sublimation pressure of ice Ih in Pa, IAPWS R14-08 (2011)

    Valid from 50 K up to the triple point (273.16 K, 611.657 Pa).
    """
    theta = T_K / 273.16
    ln_p_ratio = (-21.2144006 * theta**0.00333333333 + 27.3203819 * theta**1.20666667
                  - 6.10598130 * theta**1.70333333) / theta
    return 611.657 * np.exp(ln_p_ratio)


def T_melting_K(p_Pa):
    """Melting temperature of water in K at the pressure p_Pa, from CoolProp"""
    return state.melting_line(CoolProp.iT, CoolProp.iP, p_Pa)


# The chart: CoolPlot draws the vapour pressure curve
diagram = PropertyDiagram("HEOS::Water", "pT", units="engineering")
diagram.title = "Phase diagram of water"
diagram.set_view(x_limits=T_view_C, y_limits=p_view_bar)
# The reference badge goes to the lower right, where the gas region leaves room
diagram.settings = diagram.settings.with_(branding={"location": "lower right"})
renderer = diagram.draw(MatplotlibRenderer(use_pyplot=False, figsize=(8.0, 6.5)))
ax = renderer.ax
ax.get_legend().remove()   # the curves are labelled on the chart instead


def to_chart(T_K, p_Pa):
    """Convert temperatures in K and pressures in Pa to the chart's units"""
    return diagram.to_display("T", np.asarray(T_K)), diagram.to_display("p", np.asarray(p_Pa))


# The three boundary curves, in SI units, each starting at the triple point
T_view_min_K = T_view_C[0] + 273.15
T_view_max_K = T_view_C[1] + 273.15
p_view_min_Pa = p_view_bar[0] * 1e5
p_view_max_Pa = p_view_bar[1] * 1e5
T_sub_K = np.linspace(T_view_min_K, T_triple_K, 100)
p_sub_Pa = p_sublimation_Pa(T_sub_K)
T_vap_K = np.linspace(T_triple_K, T_crit_K, 200)
p_vap_Pa = np.array([CoolProp.CoolProp.PropsSI("P", "T", T, "Q", 0, "Water") for T in T_vap_K])
p_vap_Pa[-1] = p_crit_Pa
# Many points: the melting line has sharp corners where the kind of ice changes.
# It starts at its own lowest pressure, 611.657 Pa, a hair above the triple
# point pressure of the equation of state (611.655 Pa).
p_melt_min_Pa = state.melting_line(CoolProp.iP_min, CoolProp.iT, 0.0)
p_melt_Pa = np.geomspace(p_melt_min_Pa, p_view_max_Pa, 600)
T_melt_K = np.array([T_melting_K(p) for p in p_melt_Pa])

# Shade the four regions. Each one is a closed outline in SI units. Up to
# 10000 bar the melting line stays below the critical temperature.
regions = (
    (np.concatenate([[T_view_min_K], T_melt_K[::-1], T_sub_K[::-1]]),
     np.concatenate([[p_view_max_Pa], p_melt_Pa[::-1], p_sub_Pa[::-1]]),
     "#7fa7d9"),   # solid
    (np.concatenate([T_melt_K, [T_crit_K, T_crit_K], T_vap_K[::-1]]),
     np.concatenate([p_melt_Pa, [p_view_max_Pa, p_crit_Pa], p_vap_Pa[::-1]]),
     "#8fd0b8"),   # liquid
    (np.concatenate([T_sub_K, T_vap_K, [T_view_max_K, T_view_max_K, T_view_min_K]]),
     np.concatenate([p_sub_Pa, p_vap_Pa, [p_crit_Pa, p_view_min_Pa, p_view_min_Pa]]),
     "#f2d38c"),   # gas
    ([T_crit_K, T_view_max_K, T_view_max_K, T_crit_K],
     [p_crit_Pa, p_crit_Pa, p_view_max_Pa, p_view_max_Pa],
     "#e9a6a6"),   # supercritical fluid
)
for T_K, p_Pa, color in regions:
    x, y = to_chart(T_K, p_Pa)
    ax.fill(x, y, color=color, alpha=0.35, linewidth=0.0, zorder=0.5)

# The melting and sublimation lines in the colour of the vapour pressure curve
color = ax.lines[0].get_color()
for T_K, p_Pa in ((T_melt_K, p_melt_Pa), (T_sub_K, p_sub_Pa)):
    ax.plot(*to_chart(T_K, p_Pa), color=color, linewidth=1.5, zorder=2.5)

# The critical isotherm and isobar bound the supercritical region
x_crit, y_crit = to_chart(T_crit_K, p_crit_Pa)
ax.plot([x_crit, x_crit], [y_crit, p_view_bar[1]], color=color, linewidth=0.8, linestyle="--", zorder=2.5)
ax.plot([x_crit, T_view_C[1]], [y_crit, y_crit], color=color, linewidth=0.8, linestyle="--", zorder=2.5)

# Triple point, critical point, and melting and boiling at atmospheric pressure
points = (
    ("Triple point\n{0:.2f} \u00b0C, {1:.4f} bar", T_triple_K, p_triple_Pa, (8, -22)),
    ("Critical point\n{0:.1f} \u00b0C, {1:.1f} bar", T_crit_K, p_crit_Pa, (-110, 4)),
    ("Boiling at 1 atm\n{0:.1f} \u00b0C", 373.124, 101325.0, (8, -22)),
    ("Melting at 1 atm\n{0:.1f} \u00b0C", T_melting_K(101325.0), 101325.0, (8, 4)),
)
for text, T_K, p_Pa, offset in points:
    x, y = to_chart(T_K, p_Pa)
    ax.plot(x, y, "o", color=color, markersize=5, zorder=3)
    ax.annotate(text.format(float(x), float(y)), (x, y), xytext=offset, textcoords="offset points", fontsize=8)

# The triple points where liquid water meets two kinds of ice, IAPWS R14-08
ice_points = (
    ("Ih / III", 251.165, 208.566e6, (-40, -3)),
    ("III / V", 256.164, 350.1e6, (6, -6)),
    ("V / VI", 273.31, 632.4e6, (6, -6)),
)
for text, T_K, p_Pa, offset in ice_points:
    x, y = to_chart(T_K, p_Pa)
    ax.plot(x, y, "o", color=color, markersize=3, zorder=3)
    ax.annotate(text, (x, y), xytext=offset, textcoords="offset points", fontsize=7)

# Region names and line names
labels = (
    ("Solid (ice)", -20.0, 2.0, 11, 90),
    ("Liquid", 150.0, 1000.0, 11, 0),
    ("Gas (water vapour)", 200.0, 0.01, 11, 0),
    ("Supercritical\nfluid", 440.0, 1500.0, 11, 0),
    ("melting line", 8.0, 0.08, 8, 90),
    ("sublimation line", -24.0, 0.012, 8, 90),
    ("vapour pressure curve", 200.0, 5.0, 8, 22),
)
for text, x, y, size, angle in labels:
    ax.text(x, y, text, fontsize=size, rotation=angle, ha="center", va="center", zorder=3)

renderer.save("h2o_phase_diagram.png", dpi=150)
