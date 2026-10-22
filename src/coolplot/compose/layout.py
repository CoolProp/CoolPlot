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
from ..core.floats import is_zero, is_zero_array

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
    """One line that wants a label, in display coordinates

    ``value`` is the value of the line in display units (NaN where it has
    none) and ``line_color`` the colour of the line; the "rails" mode
    (:mod:`coolplot.compose.rails`) thins by the one and colours ticks
    with the other.
    """
    id: str
    group: str
    family: str
    text: str
    style: TextStyle
    x: np.ndarray
    y: np.ndarray
    value: float = float("nan")
    line_color: Optional[str] = None


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
        """Data coordinates (display units) to points from the lower left corner of the plot area."""
        return (self._axis(x, self.x_limits, self.x_log, self.width_pt),
                self._axis(y, self.y_limits, self.y_log, self.height_pt))

    def to_data(self, px, py):
        """Points from the lower left corner of the plot area to data coordinates."""
        return (self._inverse(px, self.x_limits, self.x_log, self.width_pt),
                self._inverse(py, self.y_limits, self.y_log, self.height_pt))

    @property
    def usable(self) -> bool:
        """Whether the frame has a size and finite limits, so that labels can be placed."""
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
        """The unit vectors along and across the box, in points."""
        c, s = math.cos(self.angle), math.sin(self.angle)
        return (c, s), (-s, c)

    def corners(self):
        """The four corners of the box, in points."""
        (ux, uy), (vx, vy) = self.axes()
        return [(self.cx + a * self.half_w * ux + b * self.half_h * vx,
                 self.cy + a * self.half_w * uy + b * self.half_h * vy)
                for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

    def inside(self, width: float, height: float, inset: float) -> bool:
        """Whether the box lies inside the plot area, ``inset`` points away from its edges."""
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
        """The length of the piece in points."""
        return float(self.arc[-1])

    def at(self, s: float) -> Tuple[float, float]:
        """The point at arc length ``s`` along the piece."""
        return float(np.interp(s, self.arc, self.px)), float(np.interp(s, self.arc, self.py))

    def project(self, qx: float, qy: float) -> Tuple[float, float]:
        """(arc length, distance) of the point on the piece nearest to (qx, qy)."""
        ax, ay = self.px[:-1], self.py[:-1]
        dx, dy = np.diff(self.px), np.diff(self.py)
        seg = dx * dx + dy * dy
        degenerate = is_zero_array(seg)   # a segment of zero length
        safe = np.where(degenerate, 1.0, seg)
        t = np.where(degenerate, 0.0, np.clip(((qx - ax) * dx + (qy - ay) * dy) / safe, 0.0, 1.0))
        dist = np.hypot(ax + t * dx - qx, ay + t * dy - qy)
        i = int(np.argmin(dist))   # the first of equally near segments, like a loop would find
        return float(self.arc[i] + t[i] * math.sqrt(seg[i])), float(dist[i])


#: Frame edges by the code the clipping below uses; -1 means no edge.
_EDGE_NAMES = ("left", "right", "bottom", "top")


def _clip_segments(x0, y0, x1, y1, width: float, height: float):
    """Liang-Barsky clipping of all segments to the plot area at once.

    Returns (t0, t1, edge0, edge1, visible): per segment the visible
    parameter range, the codes of the edges crossed at either end (-1
    where the end point is inside) and whether anything is visible. An
    end point exactly on the frame also counts as crossing it: isolines
    often end exactly at the axis limits, because the calculation domain
    and the axis limits are the same.
    """
    dx, dy = x1 - x0, y1 - y0
    n = len(x0)
    t0, t1 = np.zeros(n), np.ones(n)
    edge0, edge1 = np.full(n, -1), np.full(n, -1)
    visible = np.isfinite(x0) & np.isfinite(y0) & np.isfinite(x1) & np.isfinite(y1)
    for code, (p, q) in enumerate(((-dx, x0), (dx, width - x0), (-dy, y0), (dy, height - y0))):
        parallel = is_zero_array(p)
        visible &= ~(parallel & (q < 0.0))   # parallel to this edge and outside it
        t = q / np.where(parallel, 1.0, p)
        entering = (p < 0.0) & (t > t0)
        t0, edge0 = np.where(entering, t, t0), np.where(entering, code, edge0)
        leaving = (p > 0.0) & (t < t1)
        t1, edge1 = np.where(leaving, t, t1), np.where(leaving, code, edge1)
    visible &= t0 <= t1
    edge0 = np.where(edge0 == -1, _on_edges(x0, y0, width, height), edge0)
    edge1 = np.where(edge1 == -1, _on_edges(x1, y1, width, height), edge1)
    return t0, t1, edge0, edge1, visible


def _on_edges(x, y, width: float, height: float, tol: float = 1e-6):
    """The code of the frame edge each point lies on, or -1; top, right, bottom, left in that order of preference."""
    near = tol * max(width, height)
    codes = np.full(len(x), -1)
    for value, limit, code in ((x, 0.0, 0), (y, 0.0, 2), (x, width, 1), (y, height, 3)):
        codes = np.where(np.abs(value - limit) <= near, code, codes)   # later edges win, so top comes first
    return codes


def visible_pieces(px: np.ndarray, py: np.ndarray, width: float, height: float) -> List[Piece]:
    """The parts of a polyline inside the plot area. NaN points split a line."""
    px, py = np.asarray(px, dtype=float), np.asarray(py, dtype=float)
    if len(px) < 2:
        return []
    x0, y0, x1, y1 = px[:-1], py[:-1], px[1:], py[1:]
    t0, t1, edge0, edge1, visible = _clip_segments(x0, y0, x1, y1, width, height)
    # A piece starts at a visible segment that enters through an edge or
    # follows an invisible segment or one that left through an edge; it
    # ends at a segment that leaves, or is followed by one that does not
    # continue it.
    before = np.concatenate(([False], visible[:-1]))
    left_before = np.concatenate(([True], edge1[:-1] != -1))
    starts = np.flatnonzero(visible & ((edge0 != -1) | ~before | left_before))
    after = np.concatenate((visible[1:], [False]))
    enters_after = np.concatenate((edge0[1:] != -1, [True]))
    ends = np.flatnonzero(visible & ((edge1 != -1) | ~after | enters_after))
    pieces: List[Piece] = []
    for a, b in zip(starts, ends):
        rows = slice(a, b + 1)
        xs = np.concatenate(([x0[a] + t0[a] * (x1[a] - x0[a])], x0[rows] + t1[rows] * (x1[rows] - x0[rows])))
        ys = np.concatenate(([y0[a] + t0[a] * (y1[a] - y0[a])], y0[rows] + t1[rows] * (y1[rows] - y0[rows])))
        start_edge = _EDGE_NAMES[edge0[a]] if edge0[a] != -1 else None
        end_edge = _EDGE_NAMES[edge1[b]] if edge1[b] != -1 else None
        pieces.append(Piece(xs, ys, start_edge, end_edge))
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
    if is_zero(dx) and is_zero(dy):
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
    # The bend counts in whole millionths of a degree, so that two spots whose
    # bends differ only by rounding noise tie and the order they were found in
    # decides, the same way here and in coolplot-core (cpp/src/layout.cpp)
    bend_micro = math.floor(bend * 1e6 + 0.5)
    return Candidate(score + bend_micro * 5e-8, Box(mx, my, angle, half_w, half_h), (dx, dy))


def _candidates(pieces: Sequence[Piece], half_w: float, half_h: float, preferred: Sequence[str],
                previous: Optional[Tuple[float, float]], fallback: bool = True) -> List[Candidate]:
    """All positions considered for one label, best (lowest score) first."""
    found = []
    if previous is not None:
        found.extend(_previous_candidates(pieces, half_w, half_h, previous, fallback))
    for piece in pieces:
        found.extend(_edge_candidates(piece, half_w, half_h, preferred))
        for fraction in ((0.5, 0.25, 0.75) if fallback else ()):   # fallbacks along the line
            c = _candidate(piece, fraction * piece.length, half_w, half_h, len(EDGES) + 2.0)
            if c is not None:
                found.append(c)
    found.sort(key=lambda c: c.score)
    return found


def _previous_candidates(pieces, half_w, half_h, previous, fallback) -> List[Candidate]:
    """The old position, if the line still passes through it.

    Without fallbacks it also has to stay near a frame crossing, so that a
    label cannot drift to the middle of the chart.
    """
    # How far from the frame the edge candidates reach (three slides inward)
    edge_reach = half_w + PAD_PT + half_h + 4.0 * half_w + 1.0
    found = []
    for piece in pieces:
        s, dist = piece.project(*previous)
        near_edge = ((piece.start_edge is not None and s <= edge_reach)
                     or (piece.end_edge is not None and piece.length - s <= edge_reach))
        if dist <= 3.0 and (fallback or near_edge):
            c = _candidate(piece, s, half_w, half_h, -10.0)
            if c is not None:
                found.append(c)
    return found


def _edge_candidates(piece, half_w, half_h, preferred) -> List[Candidate]:
    """Spots just inside the frame where the piece crosses it, sliding inward three times."""
    found = []
    for edge, forward in ((piece.start_edge, True), (piece.end_edge, False)):
        if edge is None:
            continue
        rank = list(preferred).index(edge) if edge in preferred else len(preferred) + 1
        for k in range(3):   # slide inward if the spot next to the frame is taken
            s = half_w + PAD_PT + half_h + k * 2.0 * half_w
            c = _candidate(piece, s if forward else piece.length - s, half_w, half_h, rank + 0.5 * k)
            if c is not None:
                found.append(c)
    return found


def keep_out_points(frame: Frame, lines, spacing_pt: float = 2.0) -> Tuple[np.ndarray, np.ndarray]:
    """Points every ``spacing_pt`` along the given lines, in pt.

    Each entry is (x, y) for a line, or (x, y, False) for single points
    such as state markers, which are not joined.
    """
    xs, ys = [], []
    for entry in lines:
        joined = entry[2] if len(entry) > 2 else True
        px, py = frame.to_pt(entry[0], entry[1])
        for i in range(len(px)):
            if not (math.isfinite(px[i]) and math.isfinite(py[i])):
                continue
            xs.append(px[i])
            ys.append(py[i])
            if joined and i + 1 < len(px):
                between_x, between_y = _between(px[i], py[i], px[i + 1], py[i + 1], spacing_pt)
                xs.extend(between_x)
                ys.extend(between_y)
    return np.array(xs), np.array(ys)


def _between(x0, y0, x1, y1, spacing_pt: float):
    """Points every ``spacing_pt`` strictly between two finite points (none if the second is not finite)."""
    if not (math.isfinite(x1) and math.isfinite(y1)):
        return [], []
    n = int(math.hypot(x1 - x0, y1 - y0) // spacing_pt)
    ts = [k / (n + 1.0) for k in range(1, n + 1)]
    return [x0 + t * (x1 - x0) for t in ts], [y0 + t * (y1 - y0) for t in ts]


def place_edge_labels(requests: Sequence[LabelRequest], frame: Frame, keep_out_lines, keep_out_pt: float,
                      preferred_edges: Dict[str, Tuple[str, ...]],
                      previous: Optional[Dict[str, Text]] = None, fallback: bool = True,
                      occupied: Sequence[Box] = ()) -> List[Text]:
    """Edge labels for the requests, in the order given (most important first).

    ``keep_out_lines`` are (x, y) display-unit lines, or (x, y, False) for
    unconnected points, that no label may come closer to than
    ``keep_out_pt``. ``previous`` maps label ids to the
    label items of the previous layout, see the module docstring; a label
    that stays where it was is returned as the very same item, so a
    renderer does not redraw it. ``fallback`` allows positions along the
    line when no spot near the frame is free. ``occupied`` are boxes no
    label may overlap, such as the badge (:mod:`coolplot.compose.branding`).
    """
    if not frame.usable:
        return []
    previous = previous or {}
    kx, ky = keep_out_points(frame, keep_out_lines)
    placed: List[Box] = list(occupied)
    labels = []
    for request in requests:
        width, height = text_size_pt(request.text, request.style)
        half_w, half_h = 0.5 * width, 0.5 * height
        px, py = frame.to_pt(request.x, request.y)
        pieces = visible_pieces(px, py, frame.width_pt, frame.height_pt)
        old = previous.get(request.id)
        old_pt = _old_position(frame, old)
        preferred = preferred_edges.get(request.family, EDGES)
        for c in _candidates(pieces, half_w, half_h, preferred, old_pt, fallback):
            if not _free(c.box, frame, kx, ky, keep_out_pt, placed):
                continue
            placed.append(c.box)
            new = _text(request, frame, c.box, c.direction)
            labels.append(old if _same_label(old, old_pt, new, c.box) else new)
            break
    return labels


def _same_label(old: Optional[Text], old_pt, new: Text, box: Box) -> bool:
    """Whether the new label is the old one in the same place, so the old item can be kept."""
    if old is None or old_pt is None:
        return False
    return old.text == new.text and old.style == new.style and math.hypot(box.cx - old_pt[0], box.cy - old_pt[1]) < 0.5


def _old_position(frame: Frame, old: Optional[Text]):
    """Where a label of the previous layout sits, in pt, or None."""
    if old is None:
        return None
    ox, oy = frame.to_pt([old.x], [old.y])
    if not (math.isfinite(ox[0]) and math.isfinite(oy[0])):
        return None
    return float(ox[0]), float(oy[0])


def _free(box: Box, frame: Frame, kx, ky, keep_out_pt: float, placed: List[Box]) -> bool:
    """Whether a label box lies inside the frame, clear of the keep-out points and of the labels placed."""
    if not box.inside(frame.width_pt, frame.height_pt, PAD_PT):
        return False
    if box.near_points(kx, ky, keep_out_pt):
        return False
    return not any(box.overlaps(other, PAD_PT) for other in placed)


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
        half = 0.5 * height + PAD_PT   # vertical at top and bottom, horizontal at the sides
        px, py = frame.to_pt(request.x, request.y)
        for piece in visible_pieces(px, py, frame.width_pt, frame.height_pt):
            spot = _margin_spot(piece, taken)
            if spot is None:
                continue
            edge, x, y = spot
            along = x if edge in ("top", "bottom") else y
            if not _margin_free(along, half, edge, frame, taken):
                continue
            taken[edge].append((along, half))
            labels.append(_margin_text(request, frame, edge, x, y, gap_pt))
            break
    return labels


def _margin_spot(piece, taken):
    """(edge, x, y) where the piece leaves the frame through a labelled edge, or None."""
    ends = [(piece.start_edge, piece.px[0], piece.py[0]), (piece.end_edge, piece.px[-1], piece.py[-1])]
    return next(((e, x, y) for e, x, y in ends if e in taken), None)


def _margin_free(along: float, half: float, edge: str, frame: Frame, taken) -> bool:
    """Whether a margin label fits on the edge without leaving the canvas or touching another."""
    limit = frame.width_pt if edge in ("top", "bottom") else frame.height_pt
    if along - half < -PAD_PT or along + half > limit + PAD_PT:
        return False
    return not any(abs(along - a) < half + h for a, h in taken[edge])


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
    number placed before or another marker, or leaves the frame (a state
    label can be long and would be cut off). If no corner is free it takes
    the first corner inside the frame, else the first one.
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
        inside = None   # the first corner inside the frame, should every corner be taken
        for sx, sy, h_align, v_align in NUMBER_SPOTS:
            cx = px[0] + sx * (distance + 0.5 * width)
            cy = py[0] + sy * (distance + 0.5 * height)
            box = Box(cx, cy, 0.0, 0.5 * width, 0.5 * height)
            if not box.inside(frame.width_pt, frame.height_pt, 0.0):
                continue
            if inside is None:
                inside = (box, sx, sy, h_align, v_align)
            if any(box.overlaps(b, 0.5) for b in placed) or box.near_points(mx[others], my[others], 2.0):
                continue
            choice = (box, sx, sy, h_align, v_align)
            break
        if choice is None:
            choice = inside
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
