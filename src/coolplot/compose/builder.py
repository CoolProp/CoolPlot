# -*- coding: utf-8 -*-
"""From computed curves to a scene.

:func:`compose` takes the chart spec, its calculation domain and the
computed curves (all in SI units) and builds the scene items: it converts
to display units, resolves the theme into concrete styles, writes every
text and places the labels. It does no property calculations, so
everything here is cheap and runs on every update.

Property diagrams and psychrometric charts go through the same code. The
families of the chart kind (:data:`coolplot.core.diagram_type.FAMILIES`)
say which lines belong to the phase boundary: those take the theme's
saturation style (quality 0 and 1, relative humidity 100 %) or quality
style (the other quality lines, the other lines of relative humidity),
every other family takes the next palette slot.
"""
from __future__ import annotations

import math
from dataclasses import fields, is_dataclass, replace
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..core.quantities import get_quantity
from ..core.symbols import symbol_text, unit_text
from ..scene import AxesSpec, SceneItem, Line, Markers, Text, drawable_limits
from ..spec.diagram import SATURATION_KEY, CycleSpec, DiagramSpec, ProcessSpec, dome_key, scale_key
from ..style.theme import Theme
from ..style.values import Font, LineStyle, MarkerStyle
from .branding import branding
from .corners import legend_size_pt, place_corners
from .layout import (Box, Frame, LabelRequest, place_dome_labels, place_edge_labels, place_margin_labels,
                     place_state_numbers, text_size_pt)
from .rails import place_rail_labels
from ..core.floats import is_zero, same_number

# Drawing order: isolines, saturation dome, the saturation scale, marked
# critical and triple points, labels (and those of the scale), processes
# and cycles, state points, state numbers.
Z_ISOLINE, Z_SATURATION, Z_SCALE, Z_POINT, Z_LABEL, Z_PROCESS, Z_STATES = 1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0


def _scaled(value, factor: float):
    """Copy of a style value with every font size multiplied by ``factor``."""
    if isinstance(value, Font):
        return value.with_(size_pt=value.size_pt * factor)
    if isinstance(value, tuple):
        return tuple(_scaled(v, factor) for v in value)
    if is_dataclass(value) and not isinstance(value, type):
        changes = {f.name: _scaled(getattr(value, f.name), factor) for f in fields(value)}
        return replace(value, **changes)
    return value


@lru_cache(maxsize=8)
def scaled_theme(theme: Theme, factor: float) -> Theme:
    """The theme with all font sizes scaled, see ``Settings.page.font_scale``."""
    return theme if same_number(factor, 1.0) else _scaled(theme, factor)


def shown_symbol(spec: DiagramSpec, key: str) -> str:
    """The symbol of a quantity as the chart writes it, see ``LabelSettings.symbols``."""
    return symbol_text(spec.diagram.symbol(key), spec.settings.labels.symbols)


def shown_unit(spec: DiagramSpec, key: str) -> str:
    """The unit label of a quantity as the chart writes it, see ``LabelSettings.symbols``."""
    return unit_text(spec.units[key].label, spec.settings.labels.symbols)


def axis_label(spec: DiagramSpec, key: str) -> str:
    """Axis title with symbol and unit, e.g. "Specific enthalpy h / kJ/kg"."""
    return "{0} {1} / {2}".format(spec.diagram.quantity_label(key), shown_symbol(spec, key), shown_unit(spec, key))


def _include(limits, values, log: bool, pad: float = 0.04):
    """Widen (lo, hi) so that all finite values lie inside, with a margin of
    ``pad`` times the span, so that markers are not cut off at the frame."""
    values = [v for v in values if np.isfinite(v) and (v > 0.0 or not log)]
    lo, hi = limits
    if not values:
        return limits
    if log:
        span = np.log10(hi) - np.log10(lo)
        lo = min(lo, min(values) / 10.0 ** (pad * span))
        hi = max(hi, max(values) * 10.0 ** (pad * span))
    else:
        span = hi - lo
        lo = min(lo, min(values) - pad * span)
        hi = max(hi, max(values) + pad * span)
    return lo, hi


#: Room kept around the marked critical and triple points, as a fraction of the axis span
MARKED_POINT_PAD = 0.015


def axes_spec(spec: DiagramSpec, domain, theme: Theme, shown=(), marked=()) -> AxesSpec:
    """Axis titles, scales, limits and style of the diagram.

    Without a zoom window the axes cover the calculation domain, widened
    where needed so that every point in ``shown`` (display-unit (x, y)
    arrays of processes and cycles) is visible, and every point in
    ``marked`` (the critical and triple points) with a smaller margin.
    """
    diagram = spec.diagram
    limits = []
    x_log, y_log = axis_scales(spec)
    for axis, (key, view, log) in enumerate(zip((diagram.x, diagram.y), spec.view_SI, (x_log, y_log))):
        lo_hi = view if view is not None else domain.range_SI(key)
        lo_hi = tuple(sorted(spec.units[key].from_SI(lo_hi).tolist()))
        if view is None:
            lo_hi = _include(lo_hi, [v for xy in shown for v in np.asarray(xy[axis], dtype=float)], log)
            lo_hi = _include(lo_hi, [v for xy in marked for v in np.asarray(xy[axis], dtype=float)], log,
                             MARKED_POINT_PAD)
        # What the backends will draw, so that labels are laid out in that frame
        limits.append(drawable_limits(lo_hi, log))
    return AxesSpec(x_label=axis_label(spec, diagram.x), y_label=axis_label(spec, diagram.y),
                    x_log=x_log, y_log=y_log,
                    x_limits=limits[0], y_limits=limits[1], title=spec.title, style=theme.axes,
                    tick_digits=spec.settings.labels.tick_digits)


def axis_scales(spec: DiagramSpec):
    """(x_log, y_log): the diagram's scales, except that a quantity shown in a
    unit with an offset (gauge pressure) gets a linear axis, since its
    values can be zero or negative."""
    diagram = spec.diagram
    return (diagram.x_log and is_zero(spec.units[diagram.x].offset),
            diagram.y_log and is_zero(spec.units[diagram.y].offset))


def isoline_look(spec: DiagramSpec, theme: Theme, key: str, value_SI: float):
    """(style, role, legend text, z order) of one isoline, from the theme and overrides."""
    family = spec.diagram.require_family(key)
    if family.on_boundary:
        # The saturation curve and the quality (or humidity) lines take the
        # changes of set_line_style("saturation", ...) and set_line_style("Q", ...)
        if any(same_number(value_SI, b) for b in family.boundary):
            saturation = theme.saturation.with_(**spec.style_override(SATURATION_KEY))
            return saturation, "saturation", "Saturation", Z_SATURATION
        quality = theme.quality.with_(**spec.style_override(key))
        return quality, "quality", spec.diagram.quantity_label(key), Z_ISOLINE
    families = [f.key for f in spec.diagram.families if not f.on_boundary]
    style = theme.isoline_style(key, families)
    overrides = spec.style_override(key)
    if overrides:
        style = style.with_(**overrides)
    return style, "isoline", spec.diagram.quantity_label(key), Z_ISOLINE


def legend_with_unit(spec: DiagramSpec, key: str, legend: str) -> str:
    """A family's legend text with its symbol and unit, e.g. "Temperature T / deg C".

    Used by the "rails" label mode, whose labels show bare values. A
    family labelled by its saturation states says so, with the unit of
    those: "Specific entropy s at T_sat / deg C".
    """
    text = "{0} {1}".format(legend, shown_symbol(spec, key))
    anchor = _saturation_anchor(spec, key)
    if anchor is not None:
        text += " at " + saturation_symbol(spec, anchor)
        key = anchor.by
    unit = shown_unit(spec, key)
    return text if unit in ("-", "") else text + " / " + unit


def saturation_symbol(spec: DiagramSpec, anchor) -> str:
    """The symbol of the saturation state lines are labelled by: "T_sat", "T_sat,liq" or "T(x=0.5)"."""
    return state_symbol(spec, anchor.by, anchor.Q)


def state_symbol(spec: DiagramSpec, key: str, Q: float) -> str:
    """The symbol of quantity ``key`` at saturation with vapour quality ``Q``: "T_sat", "T_sat,liq" or "T(x=0.5)"."""
    symbol = shown_symbol(spec, key)
    if same_number(Q, 1.0):
        return symbol + "_sat"
    if is_zero(Q):
        return symbol + "_sat,liq"
    return symbol + "({0}={1})".format(get_quantity("Q").symbol, spec.settings.labels.format_value(Q))


def _saturation_anchor(spec: DiagramSpec, key: str):
    """The anchor of a family labelled by its saturation states, else None."""
    return next((s.anchor for s in spec.isolines if s.key == key and s.anchor is not None
                 and s.anchor.label == "saturation"), None)


def label_text(spec: DiagramSpec, key: str, value_SI: float, anchor_SI: Optional[float] = None) -> str:
    """Text of an isoline label, e.g. "T=0 deg C" or "x=0.4".

    A line placed by saturation states (``anchor_SI`` given) is labelled
    with its own value as well, unless its family asks for the saturation
    state ("label": "saturation"): "T_sat=0 deg C" (the saturated vapour),
    "T_sat,liq=0 deg C" (the saturated liquid) or "T(x=0.5)=0 deg C".
    """
    labels = spec.settings.labels
    anchor = None
    if anchor_SI is not None:
        anchor = next((s.anchor for s in spec.isolines if s.key == key and s.anchor is not None), None)
    if anchor is not None and anchor_SI is not None and anchor.label == "saturation":
        key, value_SI = anchor.by, anchor_SI
        symbol = saturation_symbol(spec, anchor)
    else:
        symbol = shown_symbol(spec, key)
    unit = spec.units[key]
    text = "{0}={1}".format(symbol, labels.format_value(unit.label_value(value_SI)))
    if labels.show_units and unit.label not in ("-", ""):
        text += " " + shown_unit(spec, key)
    return text


def isoline_items(spec: DiagramSpec, theme: Theme, curves) -> List[Line]:
    """Lines for (request, curve) pairs from the engine.

    The first line of each family carries the legend entry for the family;
    the saturation line and the other lines of a boundary family (quality,
    relative humidity) get one entry each.
    """
    ux, uy = spec.units[spec.diagram.x], spec.units[spec.diagram.y]
    rails = spec.settings.labels.mode == "rails"
    items = []
    legends_given = set()
    for request, curve in curves:
        style, role, legend, z_order = isoline_look(spec, theme, request.key, request.value_SI)
        legend_key = role if role in ("saturation", "quality") else request.key
        if legend_key in legends_given:
            legend = None
        elif rails and role != "saturation":
            legend = legend_with_unit(spec, request.key, legend)   # the labels show bare values
        legends_given.add(legend_key)
        items.append(Line(id=request.item_id, group="iso/" + request.key, role=role, legend=legend,
                          x=ux.from_SI(curve.x), y=uy.from_SI(curve.y), style=style, z_order=z_order))
    return items


def label_requests(spec: DiagramSpec, theme: Theme, curves, lines: Sequence[Line]) -> List[LabelRequest]:
    """The lines that get a label, most important first.

    Quality lines come first (they sit in the dome, where space is
    scarce), then the families in the order of the spec. Saturation lines
    (quality 0 and 1, relative humidity 100 %) are not labelled;
    ``Settings.labels.every`` thins out dense families.
    """
    labels = spec.settings.labels
    every = labels.every
    by_family: Dict[str, list] = {}   # family -> (request, line) pairs
    for (request, _), line in zip(curves, lines):
        boundary = spec.diagram.require_family(request.key).boundary
        if not request.labels or any(same_number(request.value_SI, b) for b in boundary):
            continue
        by_family.setdefault(request.key, []).append((request, line))
    order = sorted(by_family, key=lambda k: (not spec.diagram.require_family(k).on_boundary,
                                             [s.key for s in spec.isolines].index(k)))
    requests = []
    for key in order:
        for request, line in by_family[key][::every]:
            style = theme.isoline_label
            if theme.isoline_label_color == "line" and line.style.color is not None:
                style = style.with_(color=line.style.color)   # the label in its line's colour
            text = label_text(spec, key, request.value_SI, request.anchor_SI)
            value = spec.units[key].label_value(request.value_SI)
            anchor = _saturation_anchor(spec, key)
            if anchor is not None and request.anchor_SI is not None:
                value = spec.units[anchor.by].label_value(request.anchor_SI)   # the saturation state shown
            if labels.mode == "rails":
                text = labels.format_value(value)   # the bare value; symbol and unit are in the legend
            requests.append(LabelRequest(id=line.id + "/label", group=line.group + "/label", family=key,
                                         text=text, style=style, x=line.x, y=line.y, value=value,
                                         line_color=line.style.color))
    return requests


def inline_labels(spec: DiagramSpec, requests: Sequence[LabelRequest], frame: Frame) -> List[Text]:
    """Labels at ``Settings.labels.position`` along the visible part of each line."""
    (x_lo, x_hi), (y_lo, y_hi) = frame.x_limits, frame.y_limits
    position = spec.settings.labels.position
    labels = []
    for r in requests:
        x, y = r.x, r.y
        inside = np.flatnonzero(np.isfinite(x) & np.isfinite(y) &
                                (x >= x_lo) & (x <= x_hi) & (y >= y_lo) & (y <= y_hi))
        if len(inside) < 3:
            continue
        i = int(inside[min(int(position * len(inside)), len(inside) - 1)])
        i0, i1 = max(i - 1, 0), min(i + 1, len(x) - 1)
        dx, dy = float(x[i1] - x[i0]), float(y[i1] - y[i0])
        direction = (dx, dy) if math.isfinite(dx) and math.isfinite(dy) else None
        labels.append(Text(id=r.id, group=r.group, role="isoline_label", x=float(x[i]), y=float(y[i]),
                           text=r.text, direction=direction, style=r.style, z_order=Z_LABEL))
    return labels


def dome_labels(spec: DiagramSpec, domain, requests: Sequence[LabelRequest], frame: Frame, keep_out_lines,
                occupied, labels: Sequence[Text]) -> List[Text]:
    """The labels inside the dome (``LabelSettings.dome``), see :func:`coolplot.compose.layout.place_dome_labels`.

    The family is :func:`coolplot.spec.diagram.dome_key`; its lines are
    matched to the states of ``domain.dome`` by their item ids.
    """
    key = dome_key(spec.diagram)
    if not spec.settings.labels.dome or key is None or not domain.dome:
        return []
    kx, ky = spec.diagram.x, spec.diagram.y
    ux, uy = spec.units[kx], spec.units[ky]
    ends = {}
    for value_SI, bubble, dew in domain.dome:
        b, d = dict(bubble), dict(dew)
        if not all(k in state for state in (b, d) for k in (kx, ky)):
            continue
        line_id = "iso/{0}/{1:.12g}".format(key, value_SI)   # coolplot.engine.planning.isoline_id of a planned value
        ends[line_id + "/label"] = ((float(ux.from_SI(b[kx])), float(uy.from_SI(b[ky]))),
                                    (float(ux.from_SI(d[kx])), float(uy.from_SI(d[ky]))))
    family = [r for r in requests if r.family == key]
    return place_dome_labels(family, ends, frame, keep_out_lines, spec.settings.labels.keep_out_pt, occupied, labels)


def default_plot_size_pt(spec: DiagramSpec) -> Tuple[float, float]:
    """Estimated size of the plot area before a renderer reports the real one.

    The page minus room for tick labels, axis titles and a legend outside
    on the right.
    """
    page = spec.settings.page
    return 0.72 * page.width_pt, 0.82 * page.height_pt


def labels_for(spec: DiagramSpec, requests, axes: AxesSpec, keep_out_lines, plot_size_pt,
               previous, occupied=()) -> List[Text]:
    """Place the labels according to ``Settings.labels.mode``.

    ``occupied`` are boxes (points, see :class:`coolplot.compose.layout.Box`)
    that edge labels keep clear of, such as the badge.
    """
    settings = spec.settings.labels
    frame = Frame.from_axes(axes, plot_size_pt)
    if settings.mode == "inline":
        return inline_labels(spec, requests, frame)
    if settings.mode == "rails":
        legend = axes.style.legend
        outer_right = not (legend.visible and legend.location == "outside right")
        return place_rail_labels(requests, frame, keep_out_lines, settings.keep_out_pt, previous, occupied,
                                 outer_right)
    if settings.mode == "margin":
        return place_margin_labels(requests, frame, settings.margin_edges)
    edges = {family: settings.preferred_edges(family, spec.diagram.require_family(family).edges)
             for family in {r.family for r in requests}}
    return place_edge_labels(requests, frame, keep_out_lines, settings.keep_out_pt, edges, previous,
                             settings.fallback, occupied)


def marked_point_style(spec: DiagramSpec, theme: Theme) -> MarkerStyle:
    """The marker of the critical and triple points: a dot in the colour of the saturation curve.

    The dot is a little more than twice as wide as the curve, and its edge
    is the curve's casing, so it stands out where lines cross it as the
    curve does.
    """
    saturation = theme.saturation.with_(**spec.style_override(SATURATION_KEY))
    casing = saturation.casing_color is not None and saturation.casing_width_pt > 0.0
    return MarkerStyle(shape="o", size_pt=2.0 * saturation.width_pt + 3.0, face_color=saturation.color,
                       edge_color=saturation.casing_color if casing else None,
                       edge_width_pt=saturation.casing_width_pt if casing else 0.0, alpha=saturation.alpha)


#: The marked points of the spec and the states that draw them, see Domain.points
_POINT_STATES = (("critical", ("critical",)), ("triple", ("triple_liquid", "triple_vapour")))


def _inside(value: float, lo: float, hi: float) -> bool:
    """Whether a value lies in [lo, hi], with room for rounding noise."""
    return lo * (1.0 - 1e-9) <= value <= hi * (1.0 + 1e-9)


def _marked_states(spec: DiagramSpec, domain) -> List[Tuple[str, List[Dict[str, float]]]]:
    """(name, states) of each marked point inside the chart's T-p box.

    A state needs both axis quantities. Points outside the box are left
    out: the default region ("DEF") starts 1 % above the triple point, so
    its triple point is not on the chart; a region down to the limit of
    the equation of state (``tp_limits=[None, ...]``) shows it.
    """
    states = dict(getattr(domain, "points", ()))
    kx, ky = spec.diagram.x, spec.diagram.y
    T_lo, T_hi, p_lo, p_hi = domain.tp_box
    found = []
    for name, state_names in _POINT_STATES:
        if name not in spec.marked_points:
            continue
        points = [dict(states[n]) for n in state_names if n in states]
        points = [p for p in points if kx in p and ky in p and "T" in p and "p" in p
                  and _inside(p["T"], T_lo, T_hi) and _inside(p["p"], p_lo, p_hi)]
        if points:
            found.append((name, points))
    return found


def marked_points_shown(spec: DiagramSpec, domain) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Display-unit (x, y) arrays of the marked points, which the axes are widened to show whole.

    The triple point lies on the lower edge of the region, where half of
    its dot would be cut off otherwise.
    """
    ux, uy = spec.units[spec.diagram.x], spec.units[spec.diagram.y]
    return [(ux.from_SI([p[spec.diagram.x] for p in points]), uy.from_SI([p[spec.diagram.y] for p in points]))
            for _, points in _marked_states(spec, domain)]


def marked_point_items(spec: DiagramSpec, theme: Theme, domain) -> List[Markers]:
    """One set of markers for the critical point and one for the two ends of the triple line.

    The states come with the domain (:attr:`coolplot.engine.planning.Domain.points`);
    a point the fluid does not have, or whose state lacks a quantity of the
    axes, is left out. The markers have no legend entry.
    """
    kx, ky = spec.diagram.x, spec.diagram.y
    ux, uy = spec.units[kx], spec.units[ky]
    style = marked_point_style(spec, theme)
    items = []
    for name, points in _marked_states(spec, domain):
        items.append(Markers(id="point/" + name, group="points", role="marked_point",
                             x=ux.from_SI([p[kx] for p in points]), y=uy.from_SI([p[ky] for p in points]),
                             style=style, z_order=Z_POINT))
    return items


#: Distance of the saturation scale from the left edge of the plot area, in points
SCALE_INSET_PT = 10.0
#: Gap between a tick of the saturation scale and its label, in points
SCALE_GAP_PT = 2.0


def saturation_scale_parts(spec: DiagramSpec, theme: Theme, domain, frame: Frame):
    """(items, overlays, boxes) of the saturation scale, see :class:`coolplot.spec.diagram.SaturationScale`.

    The scale is a vertical line ``SCALE_INSET_PT`` inside the left edge
    of the plot area, with a tick across it at every saturation state of
    ``domain.scale`` that lies within the vertical axis, the value right of
    each tick and a title ("T_sat / deg C") above the top tick, or below
    the lowest one where there is no room above. It takes the colour,
    width and length of the axis ticks and the font of the tick labels,
    with the halo of the isoline labels, as lines run through it.

    It does not widen the axes. ``overlays`` holds the line of the scale,
    which the legend and the badge avoid like a cycle, ``boxes`` the box
    in points (layout coordinates) that the isoline labels keep clear of.
    """
    if spec.saturation_scale is None or not domain.scale or not frame.usable:
        return [], [], []
    by, key = scale_key(spec.diagram, spec.fluid), spec.diagram.y
    unit_by, unit_y = spec.units[by], spec.units[key]
    st = theme.axes
    labels = spec.settings.labels
    ticks: List[Tuple[float, float, float]] = []   # (y in display units, y in points, saturation value in SI)
    for saturation_SI, value_SI in domain.scale:
        y = float(unit_y.from_SI(value_SI))
        py = float(frame.to_pt([frame.x_limits[0]], [y])[1][0])
        if math.isfinite(py) and -1e-9 <= py <= frame.height_pt + 1e-9:
            ticks.append((y, py, saturation_SI))
    if not ticks:
        return [], [], []
    # Ticks whose values would overlap are left out, from the top down: on a temperature axis the saturation
    # pressures crowd together at the bottom
    value_style = st.tick_label.with_(h_align="left", v_align="center", halo_color=theme.isoline_label.halo_color,
                                      halo_width_pt=theme.isoline_label.halo_width_pt)
    text_h = text_size_pt("0", value_style)[1]
    kept: List[Tuple[float, float, float]] = []
    for tick in sorted(ticks, key=lambda t: -t[1]):
        if not kept or kept[-1][1] - tick[1] >= text_h:
            kept.append(tick)
    ticks = kept[::-1]
    length = st.tick_length_pt
    px = SCALE_INSET_PT
    x_line, x_left, x_right = (float(v) for v in frame.to_data([px, px - length, px + length], [0.0, 0.0, 0.0])[0])
    line_style = LineStyle(color=st.tick_color, width_pt=st.tick_width_pt)
    y_low, y_high = ticks[0][0], ticks[-1][0]
    tick_x, tick_y = [], []
    for y, _, _ in ticks:
        tick_x += [x_left, x_right, math.nan]
        tick_y += [y, y, math.nan]
    group = "scale"
    items: List[SceneItem] = [
        Line(id="scale/line", group=group, role="scale", x=np.array([x_line, x_line]), y=np.array([y_low, y_high]),
             style=line_style, z_order=Z_SCALE),
        Line(id="scale/ticks", group=group, role="scale", x=np.array(tick_x[:-1]), y=np.array(tick_y[:-1]),
             style=line_style, z_order=Z_SCALE)]
    widest = 0.0
    for y, _, saturation_SI in ticks:
        text = labels.format_value(unit_by.label_value(saturation_SI))
        widest = max(widest, text_size_pt(text, value_style)[0])
        items.append(Text(id="scale/label/{0:.12g}".format(saturation_SI), group=group + "/labels",
                          role="scale_label", x=x_line, y=y, text=text, offset_pt=(length + SCALE_GAP_PT, 0.0),
                          style=value_style, z_order=Z_LABEL))
    title = "{0} / {1}".format(state_symbol(spec, by, spec.saturation_scale.Q), shown_unit(spec, by))
    title_w, title_h = text_size_pt(title, value_style)
    gap = length + SCALE_GAP_PT
    above = ticks[-1][1] + 0.5 * text_h + gap + title_h <= frame.height_pt
    title_y = ticks[-1][0] if above else ticks[0][0]
    items.append(Text(id="scale/title", group=group + "/labels", role="scale_label", x=x_line, y=title_y,
                      text=title, offset_pt=(-length, gap if above else -gap),
                      style=value_style.with_(v_align="bottom" if above else "top"), z_order=Z_LABEL))
    # The box the scale takes, with its values and title, for the label layout
    left = px - length
    right = px + max(gap + widest, title_w - length)
    bottom = ticks[0][1] - 0.5 * text_h - (0.0 if above else gap + title_h)
    top = ticks[-1][1] + 0.5 * text_h + (gap + title_h if above else 0.0)
    box = Box(0.5 * (left + right), 0.5 * (bottom + top), 0.0, 0.5 * (right - left), 0.5 * (top - bottom))
    return items, [(np.array([x_line, x_line]), np.array([y_low, y_high]))], [box]


def process_items(spec: DiagramSpec, theme: Theme, process: ProcessSpec, index: int) -> List[SceneItem]:
    """The line and the state markers of one process."""
    ux, uy = spec.units[spec.diagram.x], spec.units[spec.diagram.y]
    kx, ky = spec.diagram.x, spec.diagram.y
    group = "process/" + process.name
    items: List[SceneItem] = []
    if process.line_states:
        items.append(Line(id=group + "/line", group=group, role="process", legend=process.name,
                          x=ux.from_SI([s[kx] for s in process.line_states]),
                          y=uy.from_SI([s[ky] for s in process.line_states]),
                          style=process.line_style or theme.process_style(index), z_order=Z_PROCESS))
    if process.marker_states:
        items.append(Markers(id=group + "/points", group=group, role="state_points", legend=process.name,
                             x=ux.from_SI([s[kx] for s in process.marker_states]),
                             y=uy.from_SI([s[ky] for s in process.marker_states]),
                             style=process.marker_style or theme.state_point_style(index), z_order=Z_STATES))
    return items


def cycle_items(spec: DiagramSpec, theme: Theme, cycle: CycleSpec, states, chains, index: int) -> List[SceneItem]:
    """One line per chain, the state markers and the state numbers of a cycle.

    All items share the group "cycle/<name>", so that a change to the
    cycle touches only them. Each state is marked and numbered once,
    however many chains pass through it.
    """
    ux, uy = spec.units[spec.diagram.x], spec.units[spec.diagram.y]
    kx, ky = spec.diagram.x, spec.diagram.y
    group = "cycle/" + cycle.name
    line_style = cycle.line_style or theme.process_style(index)
    marker_style = cycle.marker_style or theme.state_point_style(index)
    items: List[SceneItem] = []
    for i, chain in enumerate(chains):
        items.append(Line(id="{0}/loop/{1}".format(group, i), group=group, role="cycle",
                          legend=cycle.name if i == 0 else None,
                          x=ux.from_SI([s[kx] for s in chain]), y=uy.from_SI([s[ky] for s in chain]),
                          style=line_style, z_order=Z_PROCESS))
    numbers = sorted(states)
    x = ux.from_SI([states[n][kx] for n in numbers])
    y = uy.from_SI([states[n][ky] for n in numbers])
    items.append(Markers(id=group + "/states", group=group, role="state_points", legend=cycle.name,
                         x=x, y=y, style=marker_style, z_order=Z_STATES))
    if cycle.numbers or cycle.labels:
        items.extend(state_numbers(group, theme, marker_style, numbers, x, y, dict(cycle.labels), cycle.numbers))
    return items


def state_text(number: int, label, show_number: bool):
    """What is written next to a state: "2", "2: label", "label", or None for nothing."""
    if label is None:
        return str(number) if show_number else None
    return "{0}: {1}".format(number, label) if show_number else label


def state_numbers(group: str, theme: Theme, marker_style, numbers, x, y, labels=None,
                  show_numbers: bool = True) -> List[Text]:
    """The number and label of each state, up and to the right of its marker, a fixed distance on screen."""
    offset = 0.5 * marker_style.size_pt + 1.5
    number_style = theme.state_number.with_(h_align="left", v_align="bottom")
    labels = labels or {}
    texts = []
    for n, xi, yi in zip(numbers, x, y):
        text = state_text(n, labels.get(n), show_numbers)
        if text is None:
            continue
        texts.append(Text(id="{0}/number/{1}".format(group, n), group=group + "/numbers", role="state_number",
                          x=float(xi), y=float(yi), text=text, offset_pt=(offset, offset),
                          style=number_style, z_order=Z_STATES + 1.0))
    return texts


def compose(spec: DiagramSpec, domain, curves: Sequence, plot_size_pt: Optional[Tuple[float, float]] = None,
            previous_labels: Optional[Dict[str, Text]] = None, cycles: Optional[Sequence] = None,
            sources: Sequence[str] = ()) -> Tuple[List[SceneItem], AxesSpec]:
    """All scene items and the axes for a diagram.

    ``curves`` are (CurveRequest, Curve) pairs as returned by
    :meth:`coolplot.engine.Engine.curves`. ``plot_size_pt`` is the size of
    the plot area as a renderer reports it, needed to place labels; without
    it the size is estimated from ``Settings.page``. ``previous_labels``
    maps label ids to the label items of the previous scene, so that labels
    stay where they were while that spot is still free. ``cycles`` holds
    (states, chains) for each cycle of the spec, from
    :meth:`coolplot.engine.Engine.cycle`. ``sources`` are the badge lines
    naming the sources of the properties, from
    :meth:`coolplot.engine.Engine.source_lines`.
    """
    theme = scaled_theme(spec.settings.look, spec.settings.page.font_scale)
    process_parts = overlay_items(spec, theme, cycles or ())
    drawn = [(p.x, p.y, isinstance(p, Line)) for p in process_parts if not isinstance(p, Text)]
    axes = axes_spec(spec, domain, theme, drawn, marked_points_shown(spec, domain))
    size = plot_size_pt or default_plot_size_pt(spec)
    frame = Frame.from_axes(axes, size)
    process_parts = placed_state_numbers(process_parts, frame)
    lines = isoline_items(spec, theme, curves)
    scale_items, scale_lines, scale_boxes = saturation_scale_parts(spec, theme, domain, frame)
    drawn = drawn + scale_lines   # the legend, the badge and the labels keep clear of the scale as of a cycle
    badge, watermark = branding(spec, theme, frame, sources)
    axes, badge, boxes = corners_for(spec, theme, axes, frame, badge, lines, process_parts, drawn)
    if badge is not None or watermark is not None:
        axes = replace(axes, badge=badge, watermark=watermark)
    items: List[SceneItem] = list(lines)
    items.extend(scale_items)
    items.extend(marked_point_items(spec, theme, domain))
    requests = label_requests(spec, theme, curves, lines)
    if requests:
        # Rail and edge labels keep clear of a legend inside the plot area, of the badge and of the scale
        placed = labels_for(spec, requests, axes, drawn, size, previous_labels, tuple(boxes + scale_boxes))
        items.extend(placed)
        items.extend(dome_labels(spec, domain, requests, Frame.from_axes(axes, size), drawn, boxes + scale_boxes,
                                 [t for t in placed if isinstance(t, Text)]))   # rails also give tick lines
    items.extend(process_parts)
    return items, axes


def corners_for(spec: DiagramSpec, theme: Theme, axes: AxesSpec, frame: Frame, badge, lines, parts, drawn):
    """(axes, badge, boxes) with the corners of a legend inside the plot area and of the badge decided.

    See :func:`coolplot.compose.corners.place_corners`. ``boxes`` holds the
    legend's box (when it is inside) and then the badge's.
    """
    legend_style = theme.axes.legend
    legend = None
    if legend_style.visible and legend_style.location != "outside right":
        texts = []
        for item in list(lines) + list(parts):
            if item.legend and item.visible and item.legend not in texts:
                texts.append(item.legend)
        if texts:
            legend = (legend_style.location,) + legend_size_pt(texts, legend_style.text.font.size_pt)
    badge_spec = None
    if badge is not None:
        badge_spec = (spec.settings.branding.location,) + tuple(badge.size_pt()) + (badge.inset_pt,)
    shown = [(line.x, line.y) for line in lines if line.visible]
    page_width, page_height = default_plot_size_pt(spec)
    legend_at, badge_at, boxes = place_corners(frame, shown, drawn, legend, badge_spec, page_width * page_height)
    if legend is not None and legend_at is not None:
        axes = replace(axes, style=replace(axes.style, legend=replace(axes.style.legend, location=legend_at)))
    if badge is not None:
        badge = replace(badge, location=badge_at)
    return axes, badge, boxes


def overlay_items(spec: DiagramSpec, theme: Theme, cycles) -> List[SceneItem]:
    """The items of every process and cycle, each with its own palette slot."""
    parts: List[SceneItem] = []
    for index, process in enumerate(spec.processes):
        parts.extend(process_items(spec, theme, process, index))
    for index, (cycle, (states, chains)) in enumerate(zip(spec.cycles, cycles)):
        parts.extend(cycle_items(spec, theme, cycle, states, chains, len(spec.processes) + index))
    return parts


def placed_state_numbers(parts: List[SceneItem], frame: Frame) -> List[SceneItem]:
    """The same items, with the state numbers moved clear of the markers."""
    numbers = [p for p in parts if isinstance(p, Text)]
    if not numbers:
        return parts
    markers = [m for m in parts if isinstance(m, Markers)]
    mx = np.concatenate([m.x for m in markers] + [np.array([])])
    my = np.concatenate([m.y for m in markers] + [np.array([])])
    moved = {t.id: t for t in place_state_numbers(numbers, frame, mx, my)}
    return [moved.get(p.id, p) for p in parts]
