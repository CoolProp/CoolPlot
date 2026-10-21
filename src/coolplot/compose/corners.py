# -*- coding: utf-8 -*-
"""Corners of the plot area for the legend and the badge.

The legend (when it sits inside the plot area) and the badge of the
branding each take one corner. Either may be set to a corner or left to
"auto". :func:`place_corners` decides both together, so that an
automatic one never takes the corner of the other:

1. A corner that is set is kept (two set to the same corner share it).
2. An automatic legend takes a corner where its box covers no point of a
   cycle or process, and of those the one that covers the fewest points
   of the isolines, among the corners the badge does not take. Where no
   such corner is left, or where the legend would cover more than
   :data:`MAX_LEGEND_SHARE` of the plot area, it goes outside on the
   right instead, as before 1.2.
3. An automatic badge takes the corner, among those left, whose box
   covers the fewest points of cycles and processes, then of isolines.

Ties go to the first corner of :data:`AUTO_ORDER`. The boxes are
returned too, in the label layout's coordinates, so that isoline labels
keep clear of both.

The size of the legend is estimated the way the SVG writer sizes it
(coolplot.render.svg): a sample of 44 px, 0.6 times the font size per
character and 1.6 times the font size per entry.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

from .layout import Box, Frame

#: Corners tried by "auto", best first when several are equally free.
AUTO_ORDER = ("lower right", "upper left", "upper right", "lower left")
CORNERS = AUTO_ORDER
#: Distance of the legend box from the frame, in points (8 px in the SVG writer).
LEGEND_INSET_PT = 6.0
#: An automatic legend larger than this share of the plot area goes outside on the right.
MAX_LEGEND_SHARE = 0.25
_PT_PER_PX = 72.0 / 96.0


def legend_size_pt(texts: Sequence[str], font_size_pt: float) -> Tuple[float, float]:
    """Estimated (width, height) in points of a legend with these entry texts."""
    if not texts:
        return 0.0, 0.0
    longest = max(len(t) for t in texts)
    return (44.0 * _PT_PER_PX + 0.6 * font_size_pt * longest,
            8.0 * _PT_PER_PX + 1.6 * font_size_pt * len(texts))


def corner_box(frame: Frame, location: str, width: float, height: float, inset: float) -> Box:
    """The box of something of this size in a corner, in the label layout's coordinates (points, y up)."""
    vertical, horizontal = location.split()
    cx = inset + 0.5 * width if horizontal == "left" else frame.width_pt - inset - 0.5 * width
    cy = inset + 0.5 * height if vertical == "lower" else frame.height_pt - inset - 0.5 * height
    return Box(cx, cy, 0.0, 0.5 * width, 0.5 * height)


def drawn_points(frame: Frame, drawn) -> Tuple[np.ndarray, np.ndarray]:
    """The finite points of the (x, y) display-unit lines, in points."""
    xs, ys = [], []
    for entry in drawn:
        px, py = frame.to_pt(entry[0], entry[1])
        keep = np.isfinite(px) & np.isfinite(py)
        xs.append(px[keep])
        ys.append(py[keep])
    return (np.concatenate(xs) if xs else np.array([]), np.concatenate(ys) if ys else np.array([]))


def _count(box: Box, px, py) -> int:
    """How many of the points (px, py) the upright box covers."""
    return int(np.count_nonzero((np.abs(px - box.cx) <= box.half_w) & (np.abs(py - box.cy) <= box.half_h)))


def corner_counts(frame: Frame, width: float, height: float, inset: float, lines, overlays,
                  taken: Sequence[str] = ()) -> List[Tuple[int, int, str]]:
    """(overlay points, line points, corner) for every corner not among ``taken``, in :data:`AUTO_ORDER`."""
    out = []
    for corner in AUTO_ORDER:
        if corner in taken:
            continue
        box = corner_box(frame, corner, width, height, inset)
        out.append((_count(box, *overlays), _count(box, *lines), corner))
    return out


def auto_legend(frame: Frame, width: float, height: float, lines, overlays, taken: Sequence[str] = ()) -> str:
    """The corner of an automatic legend, or "outside right" where none is free; see the module docstring."""
    if not frame.usable or width * height > MAX_LEGEND_SHARE * frame.width_pt * frame.height_pt:
        return "outside right"
    free = [(n_lines, corner) for n_overlays, n_lines, corner in
            corner_counts(frame, width, height, LEGEND_INSET_PT, lines, overlays, taken) if n_overlays == 0]
    if not free:
        return "outside right"
    best = free[0]
    for candidate in free[1:]:
        if candidate[0] < best[0]:
            best = candidate
    return best[1]


def auto_badge(frame: Frame, width: float, height: float, inset: float, lines, overlays,
               taken: Sequence[str] = ()) -> str:
    """The corner of an automatic badge; see the module docstring."""
    counts = corner_counts(frame, width, height, inset, lines, overlays, taken)
    if not counts:
        counts = corner_counts(frame, width, height, inset, lines, overlays)
    if not frame.usable:
        return counts[0][2]
    best = counts[0]
    for candidate in counts[1:]:
        if candidate[:2] < best[:2]:
            best = candidate
    return best[2]


def place_corners(frame: Frame, lines, overlays, legend: Optional[Tuple[str, float, float]],
                  badge: Optional[Tuple[str, float, float, float]]) -> Tuple[Optional[str], Optional[str], List[Box]]:
    """(legend location, badge corner, boxes) for a legend inside the plot area and a badge.

    ``lines`` and ``overlays`` are (x, y) display-unit lines: the isolines,
    and the cycles and processes (lines and markers). ``legend`` is
    (location, width, height) or None when there is no legend inside the
    plot area; ``badge`` is (location, width, height, inset) or None. A
    location is a corner or "auto"; an automatic legend may come back as
    "outside right". The boxes are those of the legend inside the plot
    area and of the badge, for the label layout.
    """
    line_points = drawn_points(frame, lines)
    overlay_points = drawn_points(frame, overlays)
    legend_at = legend[0] if legend is not None else None
    badge_at = badge[0] if badge is not None else None
    if legend_at == "auto":
        legend_at = auto_legend(frame, legend[1], legend[2], line_points, overlay_points,
                                () if badge_at in (None, "auto") else (badge_at,))
    if badge_at == "auto":
        badge_at = auto_badge(frame, badge[1], badge[2], badge[3], line_points, overlay_points,
                              () if legend_at in (None, "outside right") else (legend_at,))
    boxes = []
    if legend_at not in (None, "outside right") and legend[1] > 0.0:
        boxes.append(corner_box(frame, legend_at, legend[1], legend[2], LEGEND_INSET_PT))
    if badge_at is not None:
        boxes.append(corner_box(frame, badge_at, badge[1], badge[2], badge[3]))
    return legend_at, badge_at, boxes
