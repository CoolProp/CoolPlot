# -*- coding: utf-8 -*-
"""From computed curves to a scene.

:func:`compose` takes the diagram spec, its calculation domain and the
computed curves (all in SI units) and builds the scene items: it converts
to display units, resolves the theme into concrete styles, writes every
text and places the labels. It does no property calculations, so
everything here is cheap and runs on every update.
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from functools import lru_cache
from typing import Dict, List, Sequence, Tuple

import numpy as np

from ..core.quantities import get_quantity
from ..scene import AxesSpec, Item, Line, Markers, Text
from ..spec.diagram import DiagramSpec, ProcessSpec
from ..style.theme import Theme
from ..style.values import Font
from .layout import Frame, LabelRequest, place_edge_labels, place_margin_labels

# Drawing order: isolines, saturation dome, labels, processes, state points.
Z_ISOLINE, Z_SATURATION, Z_LABEL, Z_PROCESS, Z_STATES = 1.0, 2.0, 4.0, 5.0, 6.0


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
    return theme if factor == 1.0 else _scaled(theme, factor)


def axis_label(spec: DiagramSpec, key: str) -> str:
    """Axis title with symbol and unit, e.g. "Specific enthalpy h / kJ/kg"."""
    q = get_quantity(key)
    return "{0} {1} / {2}".format(q.label, q.symbol, spec.units[key].label)


def axes_spec(spec: DiagramSpec, domain, theme: Theme) -> AxesSpec:
    """Axis titles, scales, limits and style of the diagram."""
    diagram = spec.diagram
    limits = []
    for key, view in zip((diagram.x, diagram.y), spec.view_SI):
        lo_hi = view if view is not None else domain.range_SI(key)
        limits.append(tuple(sorted(spec.units[key].from_SI(lo_hi).tolist())))
    return AxesSpec(x_label=axis_label(spec, diagram.x), y_label=axis_label(spec, diagram.y),
                    x_log=diagram.x_log, y_log=diagram.y_log,
                    x_limits=limits[0], y_limits=limits[1], title=spec.title, style=theme.axes,
                    tick_digits=spec.settings.labels.tick_digits)


def isoline_look(spec: DiagramSpec, theme: Theme, key: str, value_SI: float):
    """(style, role, legend text, z order) of one isoline, from the theme and overrides."""
    if key == "Q":
        if value_SI in (0.0, 1.0):
            return theme.saturation, "saturation", "Saturation", Z_SATURATION
        return theme.quality, "quality", "Vapour quality", Z_ISOLINE
    families = [k for k in spec.diagram.supported_isolines() if k != "Q"]
    style = theme.isoline_style(key, families)
    overrides = spec.style_override(key)
    if overrides:
        style = style.with_(**overrides)
    return style, "isoline", get_quantity(key).label, Z_ISOLINE


def label_text(spec: DiagramSpec, key: str, value_SI: float) -> str:
    """Text of an isoline label, e.g. "T=0 deg C" or "x=0.4"."""
    labels = spec.settings.labels
    unit = spec.units[key]
    text = "{0}={1}".format(get_quantity(key).symbol, labels.format_value(float(unit.from_SI(value_SI))))
    if labels.show_units and unit.label not in ("-", ""):
        text += " " + unit.label
    return text


def isoline_items(spec: DiagramSpec, theme: Theme, curves) -> List[Line]:
    """Lines for (request, curve) pairs from the engine.

    The first line of each family carries the legend entry for the family;
    the saturation dome and the quality lines get one entry each.
    """
    ux, uy = spec.units[spec.diagram.x], spec.units[spec.diagram.y]
    items = []
    legends_given = set()
    for request, curve in curves:
        style, role, legend, z_order = isoline_look(spec, theme, request.key, request.value_SI)
        legend_key = role if request.key == "Q" else request.key
        if legend_key in legends_given:
            legend = None
        legends_given.add(legend_key)
        items.append(Line(id=request.item_id, group="iso/" + request.key, role=role, legend=legend,
                          x=ux.from_SI(curve.x), y=uy.from_SI(curve.y), style=style, z_order=z_order))
    return items


def label_requests(spec: DiagramSpec, theme: Theme, curves, lines: Sequence[Line]) -> List[LabelRequest]:
    """The lines that get a label, most important first.

    Quality lines come first (they sit in the dome, where space is
    scarce), then the families in the order of the spec. Saturation lines
    (quality 0 and 1) are not labelled; ``Settings.labels.every`` thins
    out dense families.
    """
    every = spec.settings.labels.every
    by_family = {}
    for (request, _), line in zip(curves, lines):
        if not request.labels or (request.key == "Q" and request.value_SI in (0.0, 1.0)):
            continue
        by_family.setdefault(request.key, []).append((request, line))
    order = sorted(by_family, key=lambda k: (k != "Q", [s.key for s in spec.isolines].index(k)))
    requests = []
    for key in order:
        for request, line in by_family[key][::every]:
            requests.append(LabelRequest(id=line.id + "/label", group=line.group + "/label", family=key,
                                         text=label_text(spec, key, request.value_SI),
                                         style=theme.isoline_label, x=line.x, y=line.y))
    return requests


def inline_labels(spec: DiagramSpec, requests: Sequence[LabelRequest], axes: AxesSpec) -> List[Text]:
    """Labels at ``Settings.labels.position`` along the visible part of each line."""
    (x_lo, x_hi), (y_lo, y_hi) = axes.x_limits, axes.y_limits
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
        direction = (float(x[i1] - x[i0]), float(y[i1] - y[i0]))
        if not all(np.isfinite(direction)):
            direction = None
        labels.append(Text(id=r.id, group=r.group, role="isoline_label", x=float(x[i]), y=float(y[i]),
                           text=r.text, direction=direction, style=r.style, z_order=Z_LABEL))
    return labels


def default_plot_size_pt(spec: DiagramSpec) -> Tuple[float, float]:
    """Estimated size of the plot area before a renderer reports the real one.

    The page minus room for tick labels, axis titles and a legend outside
    on the right.
    """
    page = spec.settings.page
    return 0.72 * page.width_pt, 0.82 * page.height_pt


def labels_for(spec: DiagramSpec, requests, axes: AxesSpec, keep_out_lines, plot_size_pt,
               previous) -> List[Text]:
    """Place the labels according to ``Settings.labels.mode``."""
    settings = spec.settings.labels
    if settings.mode == "inline":
        return inline_labels(spec, requests, axes)
    frame = Frame(axes.x_limits, axes.y_limits, axes.x_log, axes.y_log, *plot_size_pt)
    if settings.mode == "margin":
        return place_margin_labels(requests, frame, settings.margin_edges)
    edges = {family: settings.preferred_edges(family) for family in {r.family for r in requests}}
    return place_edge_labels(requests, frame, keep_out_lines, settings.keep_out_pt, edges, previous,
                             settings.fallback)


def process_items(spec: DiagramSpec, theme: Theme, process: ProcessSpec, index: int) -> List[Item]:
    """The line and the state markers of one process."""
    ux, uy = spec.units[spec.diagram.x], spec.units[spec.diagram.y]
    kx, ky = spec.diagram.x, spec.diagram.y
    group = "process/" + process.name
    items = []
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


def compose(spec: DiagramSpec, domain, curves: Sequence, plot_size_pt: Tuple[float, float] = None,
            previous_labels: Dict[str, Text] = None) -> Tuple[List[Item], AxesSpec]:
    """All scene items and the axes for a diagram.

    ``curves`` are (CurveRequest, Curve) pairs as returned by
    :meth:`coolplot.engine.Engine.curves`. ``plot_size_pt`` is the size of
    the plot area as a renderer reports it, needed to place labels; without
    it the size is estimated from ``Settings.page``. ``previous_labels``
    maps label ids to the label items of the previous scene, so that labels
    stay where they were while that spot is still free.
    """
    theme = scaled_theme(spec.settings.look, spec.settings.page.font_scale)
    axes = axes_spec(spec, domain, theme)
    lines = isoline_items(spec, theme, curves)
    items: List[Item] = list(lines)
    process_parts = []
    for index, process in enumerate(spec.processes):
        process_parts.extend(process_items(spec, theme, process, index))
    requests = label_requests(spec, theme, curves, lines)
    if requests:
        keep_out = [(p.x, p.y) for p in process_parts]
        size = plot_size_pt or default_plot_size_pt(spec)
        items.extend(labels_for(spec, requests, axes, keep_out, size, previous_labels))
    items.extend(process_parts)
    return items, axes
