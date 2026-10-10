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
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ..core.quantities import get_quantity
from ..scene import AxesSpec, Item, Line, Markers, Text
from ..spec.diagram import DiagramSpec, ProcessSpec
from ..style.theme import Theme
from ..style.values import Font

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
                    x_limits=limits[0], y_limits=limits[1], title=spec.title, style=theme.axes)


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


def inline_label(spec: DiagramSpec, theme: Theme, line: Line, key: str, value_SI: float,
                 axes: AxesSpec) -> Optional[Text]:
    """A label on the visible part of a line, aligned with it.

    ``Settings.labels.position`` says where along the visible part it sits.
    """
    x, y = line.x, line.y
    (x_lo, x_hi), (y_lo, y_hi) = axes.x_limits, axes.y_limits
    inside = np.flatnonzero(np.isfinite(x) & np.isfinite(y) &
                            (x >= x_lo) & (x <= x_hi) & (y >= y_lo) & (y <= y_hi))
    if len(inside) < 3:
        return None
    position = spec.settings.labels.position
    i = int(inside[min(int(position * len(inside)), len(inside) - 1)])
    i0, i1 = max(i - 1, 0), min(i + 1, len(x) - 1)
    direction = (float(x[i1] - x[i0]), float(y[i1] - y[i0]))
    if not all(np.isfinite(direction)):
        direction = None
    return Text(id=line.id + "/label", group=line.group + "/label", role="isoline_label",
                x=float(x[i]), y=float(y[i]), text=label_text(spec, key, value_SI),
                direction=direction, style=theme.isoline_label, z_order=Z_LABEL)


def isoline_items(spec: DiagramSpec, theme: Theme, curves, axes: AxesSpec) -> List[Item]:
    """Lines (and labels) for (request, curve) pairs from the engine.

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
        line = Line(id=request.item_id, group="iso/" + request.key, role=role, legend=legend,
                    x=ux.from_SI(curve.x), y=uy.from_SI(curve.y), style=style, z_order=z_order)
        items.append(line)
        if request.labels:
            label = inline_label(spec, theme, line, request.key, request.value_SI, axes)
            if label is not None:
                items.append(label)
    return items


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


def compose(spec: DiagramSpec, domain, curves: Sequence) -> Tuple[List[Item], AxesSpec]:
    """All scene items and the axes for a diagram.

    ``curves`` are (CurveRequest, Curve) pairs as returned by
    :meth:`coolplot.engine.Engine.curves`.
    """
    theme = scaled_theme(spec.settings.look, spec.settings.page.font_scale)
    axes = axes_spec(spec, domain, theme)
    items = isoline_items(spec, theme, curves, axes)
    for index, process in enumerate(spec.processes):
        items.extend(process_items(spec, theme, process, index))
    return items, axes
