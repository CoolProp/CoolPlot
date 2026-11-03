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
from matplotlib import patheffects

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


# Styles from the chart's theme, so that the additions look like the lines,
# points and labels CoolPlot draws itself. They follow the theme if you
# choose another one, for example diagram.theme = "dark" before drawing.
theme = diagram.theme
font_family = ax.xaxis.label.get_fontfamily()   # the font the renderer chose for the theme


def line_kwargs(style, dash="-"):
    """matplotlib settings for a line in a LineStyle of the theme, with its casing"""
    kwargs = dict(color=style.color, linewidth=style.width_pt, linestyle=dash, solid_capstyle="round")
    if style.casing_color is not None:
        kwargs["path_effects"] = [patheffects.Stroke(linewidth=style.width_pt + 2.0 * style.casing_width_pt,
                                                     foreground=style.casing_color), patheffects.Normal()]
    return kwargs


def marker_kwargs(style, scale=1.0):
    """matplotlib settings for a point in a MarkerStyle of the theme"""
    return dict(marker=style.shape, markersize=style.size_pt * scale, markerfacecolor=style.face_color,
                markeredgecolor=style.edge_color, markeredgewidth=style.edge_width_pt, linestyle="none")


def text_kwargs(style, size_pt=None):
    """matplotlib settings for a text in a TextStyle of the theme, with its halo"""
    kwargs = dict(color=style.color, fontsize=size_pt or style.font.size_pt, fontfamily=font_family,
                  fontweight=style.font.weight)
    if style.halo_color is not None:
        kwargs["path_effects"] = [patheffects.withStroke(linewidth=2.0 * style.halo_width_pt,
                                                         foreground=style.halo_color)]
    return kwargs


# Region fills take the theme's categorical colours, faint enough for the
# grid and the lines to stay readable on top of them
REGION_ALPHA = 0.12


def region_color(index):
    return theme.categorical[index % len(theme.categorical)]


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

# Shade the regions of the solid, the liquid and the supercritical fluid; the
# gas keeps the plain background. Each region is a closed outline in SI
# units, with the index of its colour in the theme's categorical colours.
# Up to 10000 bar the melting line stays below the critical temperature.
regions = (
    (np.concatenate([[T_view_min_K], T_melt_K[::-1], T_sub_K[::-1]]),
     np.concatenate([[p_view_max_Pa], p_melt_Pa[::-1], p_sub_Pa[::-1]]),
     1),   # solid
    (np.concatenate([T_melt_K, [T_crit_K, T_crit_K], T_vap_K[::-1]]),
     np.concatenate([p_melt_Pa, [p_view_max_Pa, p_crit_Pa], p_vap_Pa[::-1]]),
     2),   # liquid
    ([T_crit_K, T_view_max_K, T_view_max_K, T_crit_K],
     [p_crit_Pa, p_crit_Pa, p_view_max_Pa, p_view_max_Pa],
     0),   # supercritical fluid
)
for T_K, p_Pa, index in regions:
    x, y = to_chart(T_K, p_Pa)
    ax.fill(x, y, color=region_color(index), alpha=REGION_ALPHA, linewidth=0.0, zorder=0.5)

# The melting and sublimation lines in the style of the vapour pressure curve
for T_K, p_Pa in ((T_melt_K, p_melt_Pa), (T_sub_K, p_sub_Pa)):
    ax.plot(*to_chart(T_K, p_Pa), zorder=2.5, **line_kwargs(theme.saturation))

# The critical isotherm and isobar bound the supercritical region; they
# take the style of the lines of constant quality, a thin muted line
x_crit, y_crit = to_chart(T_crit_K, p_crit_Pa)
ax.plot([x_crit, x_crit], [y_crit, p_view_bar[1]], zorder=2.4, **line_kwargs(theme.quality, dash="--"))
ax.plot([x_crit, T_view_C[1]], [y_crit, y_crit], zorder=2.4, **line_kwargs(theme.quality, dash="--"))

# Triple point, critical point, and melting and boiling at atmospheric
# pressure, drawn like the state points of a cycle
points = (
    ("Triple point\n{0:.2f} \u00b0C, {1:.4f} bar", T_triple_K, p_triple_Pa, (8, -22)),
    ("Critical point\n{0:.1f} \u00b0C, {1:.1f} bar", T_crit_K, p_crit_Pa, (-100, 4)),
    ("Boiling at 1 atm\n{0:.1f} \u00b0C", 373.124, 101325.0, (8, -22)),
    ("Melting at 1 atm\n{0:.1f} \u00b0C", T_melting_K(101325.0), 101325.0, (8, 4)),
)
for text, T_K, p_Pa, offset in points:
    x, y = to_chart(T_K, p_Pa)
    ax.plot(x, y, zorder=3, **marker_kwargs(theme.state_points[0]))
    ax.annotate(text.format(float(x), float(y)), (x, y), xytext=offset, textcoords="offset points", zorder=3,
                **text_kwargs(theme.isoline_label))

# The triple points where liquid water meets two kinds of ice, IAPWS R14-08,
# as smaller points
ice_points = (
    ("Ih / III", 251.165, 208.566e6, (-36, -3)),
    ("III / V", 256.164, 350.1e6, (6, -6)),
    ("V / VI", 273.31, 632.4e6, (6, -6)),
)
for text, T_K, p_Pa, offset in ice_points:
    x, y = to_chart(T_K, p_Pa)
    ax.plot(x, y, zorder=3, **marker_kwargs(theme.state_points[0], scale=0.6))
    ax.annotate(text, (x, y), xytext=offset, textcoords="offset points", zorder=3,
                **text_kwargs(theme.isoline_label))

# Region names in the axis label style at title size, line names like isoline labels
region_size_pt = theme.axes.title.font.size_pt
for text, x, y, angle in (("Solid (ice)", -20.0, 2.0, 90), ("Liquid", 150.0, 1000.0, 0),
                          ("Gas (water vapour)", 200.0, 0.01, 0), ("Supercritical\nfluid", 440.0, 1500.0, 0)):
    ax.text(x, y, text, rotation=angle, ha="center", va="center", zorder=3,
            **text_kwargs(theme.axes.axis_label, region_size_pt))
for text, x, y, angle in (("melting line", 8.0, 0.08, 90), ("sublimation line", -24.0, 0.012, 90),
                          ("vapour pressure curve", 200.0, 5.0, 22)):
    ax.text(x, y, text, rotation=angle, ha="center", va="center", zorder=3, **text_kwargs(theme.isoline_label))

renderer.save("h2o_phase_diagram.png", dpi=150)
