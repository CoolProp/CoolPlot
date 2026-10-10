# -*- coding: utf-8 -*-
"""From computed humid-air lines to the scene of a psychrometric chart.

The same building blocks as for property diagrams: theme styles, the
central number format and the edge label layout with keep-out zones
around air processes. No property calculations happen here.

Styles: the saturation line uses the theme's saturation style, lines of
relative humidity the quality style (they play the same part as vapour
quality in a property diagram), and wet-bulb temperature, enthalpy and
specific volume take the first three palette slots, like temperature,
enthalpy and density in a property diagram.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np

from ..scene import AxesSpec, Item, Line, Markers, Text, drawable_limits
from ..spec.psychro import PSYCHRO_QUANTITIES, PsychroSpec, psychro_units
from .builder import Z_ISOLINE, Z_PROCESS, Z_SATURATION, Z_STATES, scaled_theme
from .layout import Frame, LabelRequest, place_edge_labels, place_state_numbers

# Palette slots, borrowed from the property diagram families
_SLOT_KEYS = {"Twb": "T", "h": "h", "v": "rho"}
_SLOT_FAMILIES = ["T", "h", "rho"]
#: Preferred label edges: RH lines end at the right or top, Twb, h and v
#: lines run down to the bottom or out to the right.
_EDGES = {"RH": ("right", "top"), "Twb": ("bottom", "left"), "h": ("bottom", "left"), "v": ("bottom", "right")}


def axis_label(spec: PsychroSpec, key: str) -> str:
    symbol, name = PSYCHRO_QUANTITIES[key]
    return "{0} {1} / {2}".format(name, symbol, psychro_units(spec.units)[key].label)


def label_text(spec: PsychroSpec, key: str, value_SI: float) -> str:
    labels = spec.settings.labels
    unit = psychro_units(spec.units)[key]
    text = "{0}={1}".format(PSYCHRO_QUANTITIES[key][0], labels.format_value(float(unit.from_SI(value_SI))))
    if labels.show_units and unit.label not in ("-", ""):
        text += " " + unit.label
    return text


def _look(theme, key: str, value_SI: float):
    if key == "RH":
        if value_SI >= 1.0:
            return theme.saturation, "saturation", "Saturation", Z_SATURATION
        return theme.quality, "quality", PSYCHRO_QUANTITIES["RH"][1], Z_ISOLINE
    return theme.isoline_style(_SLOT_KEYS[key], _SLOT_FAMILIES), "isoline", PSYCHRO_QUANTITIES[key][1], Z_ISOLINE


def compose_psychro(spec: PsychroSpec, curves: Sequence, processes: Sequence,
                    plot_size_pt: Tuple[float, float] = None,
                    previous_labels: Dict[str, Text] = None) -> Tuple[List[Item], AxesSpec]:
    """Scene items and axes of a psychrometric chart.

    ``curves`` are (key, value_SI, labels, curve) with curve.x the dry-bulb
    temperature in K and curve.y the humidity ratio; ``processes`` are
    (AirProcessSpec, [(T_K, W), ...]).
    """
    theme = scaled_theme(spec.settings.look, spec.settings.page.font_scale)
    units = psychro_units(spec.units)
    uT, uW = units["T"], units["W"]
    limits = [drawable_limits(tuple(sorted(u.from_SI(r).tolist())), False)
              for u, r in ((uT, spec.view_T_K or spec.T_range_K), (uW, spec.view_W or spec.W_range))]
    axes = AxesSpec(x_label=axis_label(spec, "T"), y_label=axis_label(spec, "W"), x_limits=limits[0],
                    y_limits=limits[1], title=spec.title, style=theme.axes,
                    tick_digits=spec.settings.labels.tick_digits)

    items: List[Item] = []
    requests = []
    legends = set()
    for key, value_SI, labels, curve in curves:
        if curve.n_valid < 2:
            continue
        style, role, legend, z = _look(theme, key, value_SI)
        legend_key = role if key == "RH" else key
        if legend_key in legends:
            legend = None
        legends.add(legend_key)
        item_id = "psy/{0}/{1:.12g}".format(key, value_SI)
        line = Line(id=item_id, group="psy/" + key, role=role, legend=legend, x=uT.from_SI(curve.x),
                    y=uW.from_SI(curve.y), style=style, z_order=z)
        items.append(line)
        if labels and not (key == "RH" and value_SI >= 1.0):
            requests.append(LabelRequest(id=item_id + "/label", group="psy/" + key + "/label", family=key,
                                         text=label_text(spec, key, value_SI), style=theme.isoline_label,
                                         x=line.x, y=line.y))

    parts: List[Item] = []
    for index, (process, states) in enumerate(processes):
        group = "air/" + process.name
        xs = uT.from_SI([s[0] for s in states])
        ys = uW.from_SI([s[1] for s in states])
        line_x, line_y = (np.append(xs, xs[0]), np.append(ys, ys[0])) if process.closed else (xs, ys)
        parts.append(Line(id=group + "/line", group=group, role="process", legend=process.name, x=line_x, y=line_y,
                          style=process.line_style or theme.process_style(index), z_order=Z_PROCESS))
        marker_style = process.marker_style or theme.state_point_style(index)
        parts.append(Markers(id=group + "/states", group=group, role="state_points", legend=process.name,
                             x=xs, y=ys, style=marker_style, z_order=Z_STATES))
        if process.numbers:
            offset = 0.5 * marker_style.size_pt + 1.5
            style = theme.state_number.with_(h_align="left", v_align="bottom")
            for n, (x, y) in enumerate(zip(xs, ys), start=1):
                parts.append(Text(id="{0}/number/{1}".format(group, n), group=group + "/numbers",
                                  role="state_number", x=float(x), y=float(y), text=str(n),
                                  offset_pt=(offset, offset), style=style, z_order=Z_STATES + 1.0))

    size = plot_size_pt or (0.72 * spec.settings.page.width_pt, 0.82 * spec.settings.page.height_pt)
    frame = Frame(axes.x_limits, axes.y_limits, False, False, *size)
    numbers = [p for p in parts if isinstance(p, Text)]
    if numbers:
        markers = [p for p in parts if isinstance(p, Markers)]
        moved = {t.id: t for t in place_state_numbers(numbers, frame, np.concatenate([m.x for m in markers]),
                                                      np.concatenate([m.y for m in markers]))}
        parts = [moved.get(p.id, p) if isinstance(p, Text) else p for p in parts]
    keep_out = [(p.x, p.y, isinstance(p, Line)) for p in parts if not isinstance(p, Text)]
    labels = spec.settings.labels
    if requests:
        edges = {key: _EDGES.get(key, ("top", "right")) for key in _EDGES}
        items.extend(place_edge_labels(requests, frame, keep_out, labels.keep_out_pt, edges, previous_labels,
                                       labels.fallback))
    items.extend(parts)
    return items, axes
