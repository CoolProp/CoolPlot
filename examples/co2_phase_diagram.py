# -*- coding: utf-8 -*-
"""
A phase diagram of CO2
======================

The p-T chart of a pure fluid shows its vapour pressure curve, from the
triple point to the critical point. A full phase diagram adds the two
boundaries of the solid: the melting line (solid-liquid) and the
sublimation line (solid-vapour). They meet the vapour pressure curve at
the triple point, the only state where solid, liquid and vapour coexist.

For CO2 the triple point lies at -56.6 deg C and 5.2 bar, above
atmospheric pressure. That is why CO2 has no liquid phase at 1 bar: dry
ice sublimates directly to gas at -78.5 deg C, and liquid CO2 escaping
from a vessel turns into snow and gas, which matters for the safety of
CO2 systems.

CoolPlot draws the vapour pressure curve. The other parts are added in
this script with matplotlib, on the axes of the CoolPlot chart:

- the melting line from CoolProp (``AbstractState.melting_line``), which
  CoolProp provides for some fluids, CO2 among them,
- the sublimation line from the correlation of Span and Wagner (1996),
  since CoolProp does not model the solid phase,
- the regions, the triple point and the critical point.

Because these extras are matplotlib artists, they appear in the PNG and
PDF output of the matplotlib renderer only, not in the SVG, PDF or Plotly
output of the other renderers.

Run with:  python examples/co2_phase_diagram.py
Writes co2_phase_diagram.png (needs matplotlib).
"""
import numpy as np

import matplotlib
matplotlib.use("Agg")   # this example only writes a file
from matplotlib import patheffects

import CoolProp
from coolplot import PropertyDiagram
from coolplot.render.mpl import MatplotlibRenderer

# Triple point and critical point of CO2 in SI units (K and Pa)
state = CoolProp.AbstractState("HEOS", "CO2")
T_triple_K = state.Ttriple()
p_triple_Pa = CoolProp.CoolProp.PropsSI("ptriple", "CO2")
T_crit_K = state.T_critical()
p_crit_Pa = state.p_critical()

# The part of the chart to show, in the chart's units (deg C and bar).
T_view_C = (-110.0, 80.0)
p_view_bar = (0.05, 8000.0)


def p_sublimation_Pa(T_K):
    """Sublimation pressure of CO2 in Pa, Span and Wagner (1996)

    Valid from about 150 K up to the triple point.
    """
    theta = 1.0 - T_K / T_triple_K
    ln_p_ratio = T_triple_K / T_K * (-14.740846 * theta + 2.4327015 * theta**1.9 - 5.3061778 * theta**2.9)
    return p_triple_Pa * np.exp(ln_p_ratio)


def T_melting_K(p_Pa):
    """Melting temperature of CO2 in K at the pressure p_Pa, from CoolProp"""
    return state.melting_line(CoolProp.iT, CoolProp.iP, p_Pa)


# The chart: CoolPlot draws the vapour pressure curve
diagram = PropertyDiagram("HEOS::CO2", "pT", units="engineering")
diagram.title = "Phase diagram of CO2"
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
p_view_max_Pa = p_view_bar[1] * 1e5
T_sub_K = np.linspace(T_view_min_K, T_triple_K, 100)
p_sub_Pa = p_sublimation_Pa(T_sub_K)
T_vap_K = np.linspace(T_triple_K, T_crit_K, 100)
p_vap_Pa = np.array([CoolProp.CoolProp.PropsSI("P", "T", T, "Q", 0, "CO2") for T in T_vap_K])
p_vap_Pa[-1] = p_crit_Pa
# CoolProp's melting line of CO2 ends at 8227 bar; a view that goes higher
# shows the line up to there
p_melt_max_Pa = min(p_view_max_Pa, state.melting_line(CoolProp.iP_max, CoolProp.iT, 0.0))
p_melt_Pa = np.geomspace(p_triple_Pa, p_melt_max_Pa, 100)
T_melt_K = np.array([T_melting_K(p) for p in p_melt_Pa])

# The melting line runs past the critical temperature: split it there
below_crit = T_melt_K <= T_crit_K
p_melt_crit_Pa = np.interp(T_crit_K, T_melt_K, p_melt_Pa)   # T_melt_K rises with pressure

# Shade the regions of the solid, the liquid and the supercritical fluid; the
# gas keeps the plain background. Each region is a closed outline in SI
# units, with the index of its colour in the theme's categorical colours.
regions = (
    (np.concatenate([[T_view_min_K], T_melt_K[::-1], T_sub_K[::-1]]),
     np.concatenate([[p_view_max_Pa], p_melt_Pa[::-1], p_sub_Pa[::-1]]),
     1),   # solid
    (np.concatenate([T_melt_K[below_crit], [T_crit_K, T_crit_K], T_vap_K[::-1]]),
     np.concatenate([p_melt_Pa[below_crit], [p_melt_crit_Pa, p_crit_Pa], p_vap_Pa[::-1]]),
     2),   # liquid
    (np.concatenate([[T_crit_K, T_view_C[1] + 273.15, T_view_C[1] + 273.15], T_melt_K[::-1][:np.sum(~below_crit)],
                     [T_crit_K]]),
     np.concatenate([[p_crit_Pa, p_crit_Pa, p_view_max_Pa], p_melt_Pa[::-1][:np.sum(~below_crit)],
                     [p_melt_crit_Pa]]),
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
x_mc, y_mc = to_chart(T_crit_K, p_melt_crit_Pa)
ax.plot([x_crit, x_mc], [y_crit, y_mc], zorder=2.4, **line_kwargs(theme.quality, dash="--"))
ax.plot([x_crit, T_view_C[1]], [y_crit, y_crit], zorder=2.4, **line_kwargs(theme.quality, dash="--"))

# The triple point, the critical point and dry ice at atmospheric pressure,
# drawn like the state points of a cycle. The dry ice temperature is read
# from the sublimation line (the pressure rises with temperature along it).
p_atm_Pa = 101325.0
T_dry_ice_K = np.interp(np.log(p_atm_Pa), np.log(p_sub_Pa), T_sub_K)
points = (
    ("Triple point\n{0:.1f} \u00b0C, {1:.2f} bar", T_triple_K, p_triple_Pa, (8, -22)),
    ("Critical point\n{0:.1f} \u00b0C, {1:.1f} bar", T_crit_K, p_crit_Pa, (-96, 4)),
    ("Dry ice at 1 atm\n{0:.1f} \u00b0C", T_dry_ice_K, p_atm_Pa, (8, -16)),
)
for text, T_K, p_Pa, offset in points:
    x, y = to_chart(T_K, p_Pa)
    ax.plot(x, y, zorder=3, **marker_kwargs(theme.state_points[0]))
    ax.annotate(text.format(float(x), float(y)), (x, y), xytext=offset, textcoords="offset points", zorder=3,
                **text_kwargs(theme.isoline_label))

# Region names in the axis label style at title size, line names like isoline labels
region_size_pt = theme.axes.title.font.size_pt
for text, x, y in (("Solid", -95.0, 300.0), ("Liquid", 0.0, 1500.0), ("Gas", 0.0, 1.0),
                   ("Supercritical\nfluid", 60.0, 300.0)):
    ax.text(x, y, text, ha="center", va="center", zorder=3, **text_kwargs(theme.axes.axis_label, region_size_pt))
for text, x, y, angle in (("melting line", -60.0, 100.0, 88), ("sublimation line", -101.0, 0.45, 38),
                          ("vapour pressure curve", -12.0, 14.0, 22)):
    ax.text(x, y, text, rotation=angle, ha="center", va="center", zorder=3, **text_kwargs(theme.isoline_label))

renderer.save("co2_phase_diagram.png", dpi=150)

print("Triple point {0:.2f} deg C, {1:.3f} bar".format(T_triple_K - 273.15, p_triple_Pa * 1e-5))
print("Dry ice at 1 atm {0:.1f} deg C".format(T_dry_ice_K - 273.15))
