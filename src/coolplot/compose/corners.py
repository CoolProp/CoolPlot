# -*- coding: utf-8 -*-
"""Corners of the plot area for the legend and the badge.

The legend (when it sits inside the plot area) and the badge of the
branding each take one corner. Either may be set to a corner or left to
"auto". :func:`place_corners` decides both together, so that they never
share a corner:

1. A corner that is set is kept.
2. An automatic legend takes the corner where its box covers the fewest
   points of the drawn lines, among the corners the badge does not take.
3. An automatic badge does the same among the corners left.

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


def emptiest_corner(frame: Frame, width: float, height: float, inset: float, px, py,
                    taken: Sequence[str] = ()) -> str:
    """The corner, not among ``taken``, whose box covers the fewest of the points (px, py)."""
    candidates = [c for c in AUTO_ORDER if c not in taken] or list(AUTO_ORDER)
    if not frame.usable:
        return candidates[0]
    best, best_count = candidates[0], None
    for corner in candidates:
        box = corner_box(frame, corner, width, height, inset)
        inside = (np.abs(px - box.cx) <= box.half_w) & (np.abs(py - box.cy) <= box.half_h)
        count = int(np.count_nonzero(inside))
        if best_count is None or count < best_count:
            best, best_count = corner, count
    return best


def place_corners(frame: Frame, drawn, legend: Optional[Tuple[str, float, float]],
                  badge: Optional[Tuple[str, float, float, float]]) -> Tuple[Optional[str], Optional[str], List[Box]]:
    """(legend corner, badge corner, boxes) for a legend inside the plot area and a badge.

    ``legend`` is (location, width, height) or None when there is no
    legend inside the plot area; ``badge`` is (location, width, height,
    inset) or None. A location is a corner or "auto". The boxes are those
    of the legend and the badge that are placed, for the label layout.
    """
    px, py = drawn_points(frame, drawn)
    legend_at = legend[0] if legend is not None else None
    badge_at = badge[0] if badge is not None else None
    if legend_at == "auto":
        legend_at = emptiest_corner(frame, legend[1], legend[2], LEGEND_INSET_PT, px, py,
                                    () if badge_at in (None, "auto") else (badge_at,))
    if badge_at == "auto":
        badge_at = emptiest_corner(frame, badge[1], badge[2], badge[3], px, py,
                                   () if legend_at is None else (legend_at,))
    boxes = []
    if legend_at is not None and legend[1] > 0.0:
        boxes.append(corner_box(frame, legend_at, legend[1], legend[2], LEGEND_INSET_PT))
    if badge_at is not None:
        boxes.append(corner_box(frame, badge_at, badge[1], badge[2], badge[3]))
    return legend_at, badge_at, boxes
