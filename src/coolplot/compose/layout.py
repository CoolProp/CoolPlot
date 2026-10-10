# -*- coding: utf-8 -*-
"""Placing isoline labels where they do not get in the way.

Printed refrigerant charts put the value labels of isolines near the edges
of the chart, where the lines fan out and there is room, and keep the
middle free for the cycle. This module does the same in one pass over all
labels of a diagram:

1. Every line is clipped to the visible plot area. Where it leaves the
   frame, candidate positions are made just inside the frame, rotated
   along the line. A few positions further along the line serve as
   fallbacks.
2. Each process (cycle) reserves a keep-out zone: its drawn path widened
   by ``LabelSettings.keep_out_pt``. Positions inside it are rejected.
3. Labels are placed in order of importance, each taking its best free
   position. A position is free if it lies inside the frame, outside the
   keep-out zones and does not overlap a label placed before. A label
   without a free position is left out rather than overlapping others.
4. A label that was placed before keeps its position if that is still
   free, so labels do not jump around while the user drags a cycle, and
   the scene sees the same item, so nothing is redrawn.

Everything is measured in points on the plot area, which needs the size
of the plot area (``plot_size_pt``). The width of a text is estimated from
the number of characters and the font size; that is good enough to avoid
collisions and works for every backend.

The module is pure: no CoolProp, no plotting library, no state. The same
inputs always give the same labels.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..scene import Text
from ..style.values import TextStyle

EDGES = ("top", "right", "bottom", "left")

#: Average width of a character relative to the font size, for sans-serif
#: fonts with digits and lower-case letters. Used to estimate label boxes.
CHAR_WIDTH = 0.55
#: Height of a label box relative to the font size.
LINE_HEIGHT = 1.25
#: Free space between a label and the frame or a neighbouring label, in pt.
PAD_PT = 2.0
#: Labels are not put where the line bends by more than this over the
#: length of the label: rotated text on a sharp bend is hard to read.
MAX_BEND_DEG = 35.0


@dataclass(frozen=True)
class LabelRequest:
    """One line that wants a label, in display coordinates"""
    id: str
    group: str
    family: str
    text: str
    style: TextStyle
    x: np.ndarray
    y: np.ndarray


@dataclass(frozen=True)
class Frame:
    """The visible plot area and its size, to convert display units to points

    Point coordinates start at the lower left corner of the plot area,
    with y pointing up.
    """
    x_limits: Tuple[float, float]
    y_limits: Tuple[float, float]
    x_log: bool
    y_log: bool
    width_pt: float
    height_pt: float

    def _axis(self, values, limits, log, size):
        values = np.asarray(values, dtype=float)
        lo, hi = limits
        if log:
            with np.errstate(divide="ignore", invalid="ignore"):
                values = np.where(values > 0.0, np.log10(np.where(values > 0.0, values, 1.0)), np.nan)
            lo, hi = math.log10(lo), math.log10(hi)
        return (values - lo) / (hi - lo) * size

    def _inverse(self, values, limits, log, size):
        lo, hi = limits
        if log:
            lo, hi = math.log10(lo), math.log10(hi)
        out = lo + np.asarray(values, dtype=float) / size * (hi - lo)
        return 10.0 ** out if log else out

    def to_pt(self, x, y):
        return (self._axis(x, self.x_limits, self.x_log, self.width_pt),
                self._axis(y, self.y_limits, self.y_log, self.height_pt))

    def to_data(self, px, py):
        return (self._inverse(px, self.x_limits, self.x_log, self.width_pt),
                self._inverse(py, self.y_limits, self.y_log, self.height_pt))

    @property
    def usable(self) -> bool:
        (x0, x1), (y0, y1) = self.x_limits, self.y_limits
        ok = x1 > x0 and y1 > y0 and self.width_pt > 0.0 and self.height_pt > 0.0
        if self.x_log:
            ok = ok and x0 > 0.0
        if self.y_log:
            ok = ok and y0 > 0.0
        return ok


def text_size_pt(text: str, style: TextStyle) -> Tuple[float, float]:
    """Estimated (width, height) of a one-line label in points."""
    size = style.font.size_pt
    return CHAR_WIDTH * size * max(len(text), 1), LINE_HEIGHT * size


# ---------------------------------------------------------------------------
# Rotated boxes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Box:
    """A label box: centre, angle (radians) and half width and height, in pt"""
    cx: float
    cy: float
    angle: float
    half_w: float
    half_h: float

    def axes(self):
        c, s = math.cos(self.angle), math.sin(self.angle)
        return (c, s), (-s, c)

    def corners(self):
        (ux, uy), (vx, vy) = self.axes()
        return [(self.cx + a * self.half_w * ux + b * self.half_h * vx,
                 self.cy + a * self.half_w * uy + b * self.half_h * vy)
                for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

    def inside(self, width: float, height: float, inset: float) -> bool:
        return all(inset <= x <= width - inset and inset <= y <= height - inset for x, y in self.corners())

    def near_points(self, px: np.ndarray, py: np.ndarray, margin: float) -> bool:
        """Whether any of the points lies within ``margin`` of the box."""
        if len(px) == 0:
            return False
        (ux, uy), (vx, vy) = self.axes()
        dx, dy = px - self.cx, py - self.cy
        u = np.abs(dx * ux + dy * uy)
        v = np.abs(dx * vx + dy * vy)
        return bool(np.any((u <= self.half_w + margin) & (v <= self.half_h + margin)))

    def overlaps(self, other: "Box", pad: float) -> bool:
        """Separating axis test for two rotated rectangles, with padding."""
        corners_a, corners_b = self.corners(), other.corners()
        for box in (self, other):
            for ax, ay in box.axes():
                pa = [x * ax + y * ay for x, y in corners_a]
                pb = [x * ax + y * ay for x, y in corners_b]
                if max(pa) + pad < min(pb) or max(pb) + pad < min(pa):
                    return False
        return True


# ---------------------------------------------------------------------------
# Lines in plot coordinates
# ---------------------------------------------------------------------------
@dataclass
class Piece:
    """A visible part of a line, with where it starts and ends

    ``start_edge`` and ``end_edge`` name the frame edge the line crosses
    there, or are None where the line itself ends inside the plot.
    """
    px: np.ndarray
    py: np.ndarray
    start_edge: Optional[str]
    end_edge: Optional[str]

    def __post_init__(self):
        steps = np.hypot(np.diff(self.px), np.diff(self.py))
        self.arc = np.concatenate(([0.0], np.cumsum(steps)))

    @property
    def length(self) -> float:
        return float(self.arc[-1])

    def at(self, s: float) -> Tuple[float, float]:
        return float(np.interp(s, self.arc, self.px)), float(np.interp(s, self.arc, self.py))

    def project(self, qx: float, qy: float) -> Tuple[float, float]:
        """(arc length, distance) of the point on the piece nearest to (qx, qy)."""
        best = (0.0, math.inf)
        for i in range(len(self.px) - 1):
            ax, ay, bx, by = self.px[i], self.py[i], self.px[i + 1], self.py[i + 1]
            dx, dy = bx - ax, by - ay
            seg = dx * dx + dy * dy
            t = 0.0 if seg == 0.0 else min(1.0, max(0.0, ((qx - ax) * dx + (qy - ay) * dy) / seg))
            dist = math.hypot(ax + t * dx - qx, ay + t * dy - qy)
            if dist < best[1]:
                best = (self.arc[i] + t * math.sqrt(seg), dist)
        return best


def _clip_segment(x0, y0, x1, y1, width, height):
    """Liang-Barsky clipping of a segment to the plot area.

    Returns (t0, t1, edge0, edge1): the visible parameter range and the
    edges crossed at either end (None where the end point is inside), or
    None if nothing is visible.
    """
    t0, t1, edge0, edge1 = 0.0, 1.0, None, None
    dx, dy = x1 - x0, y1 - y0
    for p, q, edge in ((-dx, x0, "left"), (dx, width - x0, "right"),
                       (-dy, y0, "bottom"), (dy, height - y0, "top")):
        if p == 0.0:
            if q < 0.0:
                return None
            continue
        t = q / p
        if p < 0.0:
            if t > t1:
                return None
            if t > t0:
                t0, edge0 = t, edge
        else:
            if t < t0:
                return None
            if t < t1:
                t1, edge1 = t, edge
    # An end point exactly on the frame also counts as crossing it: isolines
    # often end exactly at the axis limits, because the calculation domain
    # and the axis limits are the same.
    if edge0 is None:
        edge0 = _on_edge(x0, y0, width, height)
    if edge1 is None:
        edge1 = _on_edge(x1, y1, width, height)
    return t0, t1, edge0, edge1


def _on_edge(x, y, width, height, tol=1e-6):
    """The frame edge a point lies on, or None."""
    for value, limit, edge in ((y, height, "top"), (x, width, "right"), (y, 0.0, "bottom"), (x, 0.0, "left")):
        if abs(value - limit) <= tol * max(width, height):
            return edge
    return None


def visible_pieces(px: np.ndarray, py: np.ndarray, width: float, height: float) -> List[Piece]:
    """The parts of a polyline inside the plot area. NaN points split a line."""
    pieces: List[Piece] = []
    xs: List[float] = []
    ys: List[float] = []
    start_edge = None

    def close(end_edge):
        nonlocal xs, ys
        if len(xs) >= 2:
            pieces.append(Piece(np.array(xs), np.array(ys), start_edge, end_edge))
        xs, ys = [], []

    for i in range(len(px) - 1):
        x0, y0, x1, y1 = px[i], py[i], px[i + 1], py[i + 1]
        if not (math.isfinite(x0) and math.isfinite(y0) and math.isfinite(x1) and math.isfinite(y1)):
            close(None)
            continue
        clipped = _clip_segment(x0, y0, x1, y1, width, height)
        if clipped is None:
            close(None)
            continue
        t0, t1, edge0, edge1 = clipped
        if edge0 is not None or not xs:
            close(None)
            start_edge = edge0
            xs, ys = [x0 + t0 * (x1 - x0)], [y0 + t0 * (y1 - y0)]
        xs.append(x0 + t1 * (x1 - x0))
        ys.append(y0 + t1 * (y1 - y0))
        if edge1 is not None:
            close(edge1)
    close(None)
    return pieces


# ---------------------------------------------------------------------------
# Edge labels
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Candidate:
    score: float
    box: Box
    direction: Tuple[float, float]   # along the line at the label, in pt


def _candidate(piece: Piece, s: float, half_w: float, half_h: float, score: float) -> Optional[Candidate]:
    """A label centred at arc length ``s``, aligned with the chord over its length."""
    if s - half_w < 0.0 or s + half_w > piece.length:
        return None
    ax, ay = piece.at(s - half_w)
    mx, my = piece.at(s)
    bx, by = piece.at(s + half_w)
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return None
    # How much the line bends under the label: angle between the two halves
    first, second = math.atan2(my - ay, mx - ax), math.atan2(by - my, bx - mx)
    bend = abs(math.degrees((second - first + math.pi) % (2.0 * math.pi) - math.pi))
    if bend > MAX_BEND_DEG:
        return None
    angle = math.atan2(dy, dx)
    # Text is always upright: turn by half a turn if it would read downwards
    if angle > math.pi / 2.0:
        angle -= math.pi
    elif angle <= -math.pi / 2.0:
        angle += math.pi
    return Candidate(score + bend / 20.0, Box(mx, my, angle, half_w, half_h), (dx, dy))


def _candidates(pieces: Sequence[Piece], half_w: float, half_h: float, preferred: Sequence[str],
                previous: Optional[Tuple[float, float]], fallback: bool = True) -> List[Candidate]:
    """All positions considered for one label, best (lowest score) first."""
    found = []
    if previous is not None:
        # Keep the old position if the line still passes through it
        for piece in pieces:
            s, dist = piece.project(*previous)
            if dist <= 3.0:
                c = _candidate(piece, s, half_w, half_h, -10.0)
                if c is not None:
                    found.append(c)
    for piece in pieces:
        for edge, forward in ((piece.start_edge, True), (piece.end_edge, False)):
            if edge is None:
                continue
            rank = list(preferred).index(edge) if edge in preferred else len(preferred) + 1
            for k in range(3):   # slide inward if the spot next to the frame is taken
                s = half_w + PAD_PT + half_h + k * 2.0 * half_w
                c = _candidate(piece, s if forward else piece.length - s, half_w, half_h, rank + 0.5 * k)
                if c is not None:
                    found.append(c)
        for fraction in ((0.5, 0.25, 0.75) if fallback else ()):   # fallbacks along the line
            c = _candidate(piece, fraction * piece.length, half_w, half_h, len(EDGES) + 2.0)
            if c is not None:
                found.append(c)
    found.sort(key=lambda c: c.score)
    return found


def keep_out_points(frame: Frame, lines, spacing_pt: float = 2.0) -> Tuple[np.ndarray, np.ndarray]:
    """Points every ``spacing_pt`` along the given (x, y) lines, in pt."""
    xs, ys = [], []
    for x, y in lines:
        px, py = frame.to_pt(x, y)
        for i in range(len(px)):
            if not (math.isfinite(px[i]) and math.isfinite(py[i])):
                continue
            xs.append(px[i])
            ys.append(py[i])
            if i + 1 < len(px) and math.isfinite(px[i + 1]) and math.isfinite(py[i + 1]):
                n = int(math.hypot(px[i + 1] - px[i], py[i + 1] - py[i]) // spacing_pt)
                for k in range(1, n + 1):
                    t = k / (n + 1.0)
                    xs.append(px[i] + t * (px[i + 1] - px[i]))
                    ys.append(py[i] + t * (py[i + 1] - py[i]))
    return np.array(xs), np.array(ys)


def place_edge_labels(requests: Sequence[LabelRequest], frame: Frame, keep_out_lines, keep_out_pt: float,
                      preferred_edges: Dict[str, Tuple[str, ...]],
                      previous: Optional[Dict[str, Text]] = None, fallback: bool = True) -> List[Text]:
    """Edge labels for the requests, in the order given (most important first).

    ``keep_out_lines`` are (x, y) display-unit lines no label may come
    closer to than ``keep_out_pt``. ``previous`` maps label ids to the
    label items of the previous layout, see the module docstring; a label
    that stays where it was is returned as the very same item, so a
    renderer does not redraw it. ``fallback`` allows positions along the
    line when no spot near the frame is free.
    """
    if not frame.usable:
        return []
    previous = previous or {}
    kx, ky = keep_out_points(frame, keep_out_lines)
    placed: List[Box] = []
    labels = []
    for request in requests:
        width, height = text_size_pt(request.text, request.style)
        half_w, half_h = 0.5 * width, 0.5 * height
        px, py = frame.to_pt(request.x, request.y)
        pieces = visible_pieces(px, py, frame.width_pt, frame.height_pt)
        old = previous.get(request.id)
        old_pt = None
        if old is not None:
            ox, oy = frame.to_pt([old.x], [old.y])
            if math.isfinite(ox[0]) and math.isfinite(oy[0]):
                old_pt = (float(ox[0]), float(oy[0]))
        preferred = preferred_edges.get(request.family, EDGES)
        for c in _candidates(pieces, half_w, half_h, preferred, old_pt, fallback):
            box = c.box
            if not box.inside(frame.width_pt, frame.height_pt, PAD_PT):
                continue
            if box.near_points(kx, ky, keep_out_pt):
                continue
            if any(box.overlaps(other, PAD_PT) for other in placed):
                continue
            placed.append(box)
            new = _text(request, frame, box, c.direction)
            unchanged = (old is not None and old_pt is not None and old.text == new.text
                         and old.style == new.style and math.hypot(box.cx - old_pt[0], box.cy - old_pt[1]) < 0.5)
            labels.append(old if unchanged else new)
            break
    return labels


def _text(request: LabelRequest, frame: Frame, box: Box, direction_pt) -> Text:
    """The scene item for a placed label; the direction is given in data units."""
    (x0, x1), (y0, y1) = frame.to_data([box.cx - 0.5 * direction_pt[0], box.cx + 0.5 * direction_pt[0]],
                                       [box.cy - 0.5 * direction_pt[1], box.cy + 0.5 * direction_pt[1]])
    cx, cy = frame.to_data([box.cx], [box.cy])
    direction = (float(x1 - x0), float(y1 - y0))
    if not all(math.isfinite(v) for v in direction):
        direction = None
    return Text(id=request.id, group=request.group, role="isoline_label", x=float(cx[0]), y=float(cy[0]),
                text=request.text, direction=direction,
                style=request.style.with_(h_align="center", v_align="center"), z_order=4.0)


# ---------------------------------------------------------------------------
# Margin labels
# ---------------------------------------------------------------------------
def place_margin_labels(requests: Sequence[LabelRequest], frame: Frame, edges: Sequence[str],
                        gap_pt: float = 3.0) -> List[Text]:
    """Horizontal labels outside the frame where the lines cross it.

    Like a second set of tick labels: they never touch the data, at the
    cost of white space on those sides. Labels at the top and bottom are
    written vertically, so that closely spaced lines still get one each.
    Labels that would overlap a label placed before on the same edge are
    left out.
    """
    if not frame.usable:
        return []
    taken: Dict[str, List[Tuple[float, float]]] = {edge: [] for edge in edges}
    labels = []
    for request in requests:
        width, height = text_size_pt(request.text, request.style)
        px, py = frame.to_pt(request.x, request.y)
        for piece in visible_pieces(px, py, frame.width_pt, frame.height_pt):
            ends = [(piece.start_edge, piece.px[0], piece.py[0]), (piece.end_edge, piece.px[-1], piece.py[-1])]
            spot = next(((e, x, y) for e, x, y in ends if e in taken), None)
            if spot is None:
                continue
            edge, x, y = spot
            along = x if edge in ("top", "bottom") else y
            half = 0.5 * height + PAD_PT   # vertical at top and bottom, horizontal at the sides
            limit = frame.width_pt if edge in ("top", "bottom") else frame.height_pt
            if along - half < -PAD_PT or along + half > limit + PAD_PT:
                continue
            if any(abs(along - a) < half + h for a, h in taken[edge]):
                continue
            taken[edge].append((along, half))
            labels.append(_margin_text(request, frame, edge, x, y, gap_pt))
            break
    return labels


def _margin_text(request: LabelRequest, frame: Frame, edge: str, x: float, y: float, gap_pt: float) -> Text:
    # (h_align, v_align, offset, direction). A vertical direction turns the
    # text to read upwards; its start (h_align "left") is then at the bottom.
    align = {"top": ("left", "center", (0.0, gap_pt), (0.0, 1.0)),
             "bottom": ("right", "center", (0.0, -gap_pt), (0.0, 1.0)),
             "right": ("left", "center", (gap_pt, 0.0), None),
             "left": ("right", "center", (-gap_pt, 0.0), None)}
    h_align, v_align, offset, direction = align[edge]
    # Snap onto the frame exactly, so the text sits at the same distance
    # from it for every line
    if edge in ("top", "bottom"):
        y = frame.height_pt if edge == "top" else 0.0
    else:
        x = frame.width_pt if edge == "right" else 0.0
    cx, cy = frame.to_data([x], [y])
    return Text(id=request.id, group=request.group, role="isoline_label", x=float(cx[0]), y=float(cy[0]),
                text=request.text, direction=direction, style=request.style.with_(h_align=h_align, v_align=v_align),
                offset_pt=offset, clip=False, z_order=4.0)


# ---------------------------------------------------------------------------
# State numbers
# ---------------------------------------------------------------------------
#: Where a state number may go around its marker, in order of preference:
#: (x direction, y direction, h_align, v_align).
NUMBER_SPOTS = ((1, 1, "left", "bottom"), (-1, 1, "right", "bottom"), (1, -1, "left", "top"),
                (-1, -1, "right", "top"))


def place_state_numbers(numbers: Sequence[Text], frame: Frame, marker_x, marker_y) -> List[Text]:
    """Move state numbers around their markers so they do not cover each other.

    Each number starts up and to the right of its marker (its offset gives
    the distance) and moves to another corner if that spot overlaps a
    number placed before or another marker. If no corner is free it stays
    in the first one.
    """
    if not frame.usable:
        return list(numbers)
    mx, my = frame.to_pt(np.asarray(marker_x, dtype=float), np.asarray(marker_y, dtype=float))
    placed: List[Box] = []
    out = []
    for t in numbers:
        px, py = frame.to_pt([t.x], [t.y])
        if not (math.isfinite(px[0]) and math.isfinite(py[0])):
            out.append(t)
            continue
        width, height = text_size_pt(t.text, t.style)
        distance = abs(t.offset_pt[0])
        others = (np.hypot(mx - px[0], my - py[0]) > 0.5)   # every marker but its own
        choice = None
        for sx, sy, h_align, v_align in NUMBER_SPOTS:
            cx = px[0] + sx * (distance + 0.5 * width)
            cy = py[0] + sy * (distance + 0.5 * height)
            box = Box(cx, cy, 0.0, 0.5 * width, 0.5 * height)
            if any(box.overlaps(b, 0.5) for b in placed) or box.near_points(mx[others], my[others], 2.0):
                continue
            choice = (box, sx, sy, h_align, v_align)
            break
        if choice is None:
            sx, sy, h_align, v_align = NUMBER_SPOTS[0]
            box = Box(px[0] + distance + 0.5 * width, py[0] + distance + 0.5 * height, 0.0,
                      0.5 * width, 0.5 * height)
            choice = (box, sx, sy, h_align, v_align)
        box, sx, sy, h_align, v_align = choice
        placed.append(box)
        out.append(replace(t, offset_pt=(sx * distance, sy * distance),
                           style=t.style.with_(h_align=h_align, v_align=v_align)))
    return out
