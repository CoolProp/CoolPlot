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
from ..scene import AxesSpec, Item, Line, Markers, Text, drawable_limits
from ..spec.diagram import CycleSpec, DiagramSpec, ProcessSpec
from ..style.theme import Theme
from ..style.values import Font
from .layout import Frame, LabelRequest, place_edge_labels, place_margin_labels, place_state_numbers

# Drawing order: isolines, saturation dome, labels, processes and cycles,
# state points, state numbers.
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


def axes_spec(spec: DiagramSpec, domain, theme: Theme, shown=()) -> AxesSpec:
    """Axis titles, scales, limits and style of the diagram.

    Without a zoom window the axes cover the calculation domain, widened
    where needed so that every point in ``shown`` (display-unit (x, y)
    arrays of processes and cycles) is visible.
    """
    diagram = spec.diagram
    limits = []
    for axis, (key, view, log) in enumerate(zip((diagram.x, diagram.y), spec.view_SI,
                                                (diagram.x_log, diagram.y_log))):
        lo_hi = view if view is not None else domain.range_SI(key)
        lo_hi = tuple(sorted(spec.units[key].from_SI(lo_hi).tolist()))
        if view is None:
            lo_hi = _include(lo_hi, [v for xy in shown for v in np.asarray(xy[axis], dtype=float)], log)
        # What the backends will draw, so that labels are laid out in that frame
        limits.append(drawable_limits(lo_hi, log))
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


def cycle_items(spec: DiagramSpec, theme: Theme, cycle: CycleSpec, states, chains, index: int) -> List[Item]:
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
    items: List[Item] = []
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
    if cycle.numbers:
        # Up and to the right of the marker, a fixed distance on screen
        offset = 0.5 * marker_style.size_pt + 1.5
        number_style = theme.state_number.with_(h_align="left", v_align="bottom")
        for n, xi, yi in zip(numbers, x, y):
            items.append(Text(id="{0}/number/{1}".format(group, n), group=group + "/numbers", role="state_number",
                              x=float(xi), y=float(yi), text=str(n), offset_pt=(offset, offset),
                              style=number_style, z_order=Z_STATES + 1.0))
    return items


def compose(spec: DiagramSpec, domain, curves: Sequence, plot_size_pt: Tuple[float, float] = None,
            previous_labels: Dict[str, Text] = None, cycles: Sequence = None) -> Tuple[List[Item], AxesSpec]:
    """All scene items and the axes for a diagram.

    ``curves`` are (CurveRequest, Curve) pairs as returned by
    :meth:`coolplot.engine.Engine.curves`. ``plot_size_pt`` is the size of
    the plot area as a renderer reports it, needed to place labels; without
    it the size is estimated from ``Settings.page``. ``previous_labels``
    maps label ids to the label items of the previous scene, so that labels
    stay where they were while that spot is still free. ``cycles`` holds
    (states, chains) for each cycle of the spec, from
    :meth:`coolplot.engine.Engine.cycle`.
    """
    theme = scaled_theme(spec.settings.look, spec.settings.page.font_scale)
    process_parts = []
    for index, process in enumerate(spec.processes):
        process_parts.extend(process_items(spec, theme, process, index))
    for index, (cycle, (states, chains)) in enumerate(zip(spec.cycles, cycles or ())):
        process_parts.extend(cycle_items(spec, theme, cycle, states, chains, len(spec.processes) + index))
    drawn = [(p.x, p.y, isinstance(p, Line)) for p in process_parts if not isinstance(p, Text)]
    axes = axes_spec(spec, domain, theme, drawn)
    size = plot_size_pt or default_plot_size_pt(spec)
    frame = Frame(axes.x_limits, axes.y_limits, axes.x_log, axes.y_log, *size)
    numbers = [p for p in process_parts if isinstance(p, Text)]
    if numbers:
        markers = [p for p in process_parts if isinstance(p, Markers)]
        mx = np.concatenate([m.x for m in markers]) if markers else np.array([])
        my = np.concatenate([m.y for m in markers]) if markers else np.array([])
        moved = {t.id: t for t in place_state_numbers(numbers, frame, mx, my)}
        process_parts = [moved.get(p.id, p) if isinstance(p, Text) else p for p in process_parts]
    lines = isoline_items(spec, theme, curves)
    items: List[Item] = list(lines)
    requests = label_requests(spec, theme, curves, lines)
    if requests:
        items.extend(labels_for(spec, requests, axes, drawn, size, previous_labels))
    items.extend(process_parts)
    return items, axes
