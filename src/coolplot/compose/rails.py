# -*- coding: utf-8 -*-
"""Isoline labels on rails along the frame ("rails" label mode).

Printed charts often write the values of a family of lines in a row along
one side of the chart, where the lines leave it, and say the quantity
and its unit once, in the legend. This module does that for every
family of a chart with a few rules:

1. **Rails.** A rail is a row of labels along one edge of the plot area.
   The outer rails sit outside the frame, at the top and on the right
   (the bottom and the left carry the tick labels): a short tick on the
   frame marks where the line leaves, and the bare value is written next
   to it, horizontal (at the top vertical when that fits more labels).
   The inner rails sit just inside the frame on every edge; there each
   label is turned along its line, and the boxes of the labels touch a
   common line parallel to the frame, so that the row looks straight
   whatever the angles. A second inner rail lies a little further in.
2. **One rail per family.** Each family gets the rail on which the most of
   its labels fit (outer rails win a tie, then the order of
   :func:`slots`), and no two families share a rail. A family whose
   lines leave through two edges may then take a second free rail for
   the lines that do not reach its first rail (not for those it thinned
   out). A family whose labels
   fit on no rail (its lines end inside the plot) gets a label near the
   end of each line, turned along it.
3. **Thinning by value.** When not all labels of a family fit, whole
   levels of values are dropped: the values that are multiples of ten
   steps of the family are kept longest, then those of five and two
   steps (:func:`value_levels`). The same level holds for the whole
   family, so a row never skips values irregularly.
4. **Free space.** Labels inside the frame keep clear of the processes
   (``keep_out_pt``), of each other and of boxes that are taken (the
   legend and the badge).
5. **Stability.** A family keeps the rail of the previous layout unless
   another rail fits more than one label more, and a label that stays
   where it was is returned as the same item, so nothing is redrawn.

The module is pure and works in points on the plot area, like
:mod:`coolplot.compose.layout`, whose geometry it uses. coolplot-core
(cpp/src/layout.cpp, section "Rails") does the same, step for step.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..scene import Line, Text
from ..style.values import LineStyle
from .layout import (EDGES, PAD_PT, Box, Frame, LabelRequest, Piece, _candidate, _text, keep_out_points,
                     text_size_pt, visible_pieces, LINE_HEIGHT)

#: Length of the tick on the frame where a line with an outer label leaves it, in pt.
TICK_PT = 5.0
#: Width of that tick, in pt.
TICK_WIDTH_PT = 0.8
#: Distance between the frame and an outer label, in pt.
OUTER_GAP_PT = 4.0
#: Free space between neighbouring labels on an outer rail, in pt.
GAP_PT = 3.0
#: Depth of the second inner rail, in heights of a label.
SECOND_RAIL = 2.2
#: Distance between the end of a line and its end label, in pt.
END_GAP_PT = 4.0
#: Shortest visible piece of a line that gets an end label, in pt.
END_MIN_PT = 30.0
#: The multiples of the step of a family that make the levels of values, most significant first.
LEVEL_STEPS = (10, 5, 2, 1)


def slots(outer_right: bool = True) -> List[Tuple[str, int]]:
    """The rails in order of preference: (edge, depth index), -1 for an outer rail."""
    out = [("top", -1)]
    if outer_right:
        out.append(("right", -1))
    out += [("top", 0), ("right", 0), ("bottom", 0), ("left", 0), ("bottom", 1), ("left", 1),
            ("top", 1), ("right", 1)]
    return out


def value_levels(values: Sequence[float]) -> List[int]:
    """The level of each value: 0 for multiples of ten steps, 1 of five, 2 of two, 3 for the rest.

    The step is the smallest gap between the values. Values that are not
    finite get level 0.
    """
    finite = sorted(v for v in values if math.isfinite(v))
    gaps = [b - a for a, b in zip(finite, finite[1:]) if b - a > 1e-12 * max(abs(a), abs(b), 1.0)]
    if not gaps:
        return [0 for _ in values]
    step = min(gaps)
    levels = []
    for v in values:
        level = 0 if not math.isfinite(v) else len(LEVEL_STEPS) - 1
        if math.isfinite(v):
            for i, k in enumerate(LEVEL_STEPS):
                q = v / (k * step)
                if abs(q - round(q)) < 1e-6:
                    level = i
                    break
        levels.append(level)
    return levels


def choose(candidates: List[dict], fits) -> List[dict]:
    """The candidates of the finest level at which all of them fit together.

    If not even the coarsest level fits, candidates are added one by one,
    coarsest level first and along the rail, as long as they fit.
    """
    for max_level in range(len(LEVEL_STEPS) - 1, -1, -1):
        chosen = [c for c in candidates if c["level"] <= max_level]
        if chosen and fits(chosen):
            return chosen
    chosen: List[dict] = []
    for c in sorted(candidates, key=lambda c: (c["level"], c["along"])):
        if fits(chosen + [c]):
            chosen.append(c)
    return chosen


def _depth(edge: str, x: float, y: float, frame: Frame) -> float:
    """How far a point lies inside the frame, measured from ``edge``."""
    return {"top": frame.height_pt - y, "bottom": y, "right": frame.width_pt - x, "left": x}[edge]


def crossing(piece: Piece, edge: str, depth: float, frame: Frame) -> Optional[Tuple[float, float, float]]:
    """(x, y, arc length) where the piece meets the rail ``depth`` points inside ``edge``.

    The crossing nearest to the end of the piece on that edge; None if the
    piece does not leave through ``edge`` or does not reach that depth.
    Depth 0 is the end of the piece on the frame.
    """
    if edge not in (piece.start_edge, piece.end_edge):
        return None
    forward = piece.start_edge == edge
    if depth <= 0.0:
        i = 0 if forward else len(piece.px) - 1
        return float(piece.px[i]), float(piece.py[i]), float(piece.arc[i])
    d = np.array([_depth(edge, x, y, frame) for x, y in zip(piece.px, piece.py)]) - depth
    order = range(len(d) - 1) if forward else range(len(d) - 2, -1, -1)
    for i in order:
        a, b = d[i], d[i + 1]
        if (a <= 0.0 <= b) or (b <= 0.0 <= a):
            t = 0.0 if abs(b - a) < 1e-12 else -a / (b - a)
            x = piece.px[i] + t * (piece.px[i + 1] - piece.px[i])
            y = piece.py[i] + t * (piece.py[i + 1] - piece.py[i])
            return float(x), float(y), float(piece.arc[i] + t * (piece.arc[i + 1] - piece.arc[i]))
    return None


def _nearest_depth(box: Box, edge: str, frame: Frame) -> float:
    """The depth of the corner of a box nearest to ``edge``."""
    return min(_depth(edge, x, y, frame) for x, y in box.corners())


def inner_candidate(piece: Piece, edge: str, bound: float, half_w: float, half_h: float, frame: Frame):
    """A label turned along the piece whose box touches the rail ``bound`` points inside ``edge``.

    The centre is moved along the line until the corner of the box
    nearest to the edge lies on the rail: two corrections, since the angle
    changes a little as the label moves. The centre stays at least half a
    label from the ends of the piece (a steep line meets the first guess
    close to the frame). Returns (box, direction in pt) or None where the
    line does not reach the rail or bends too much there.
    """
    if piece.length < 2.0 * half_w:
        return None
    depth = bound + half_h
    c = None
    for _ in range(3):
        hit = crossing(piece, edge, depth, frame)
        if hit is None:
            return None
        c = _candidate(piece, min(max(hit[2], half_w), piece.length - half_w), half_w, half_h, 0.0)
        if c is None:
            return None
        # The next centre: where this one is, moved by what its box is off the rail
        depth = _depth(edge, c.box.cx, c.box.cy, frame) + (bound - _nearest_depth(c.box, edge, frame))
    if abs(_nearest_depth(c.box, edge, frame) - bound) > 0.5:
        return None
    return c.box, c.direction


def _fits_on_line(cands: List[dict], extent: str) -> bool:
    """Whether labels in a row along an outer rail keep ``GAP_PT`` between them."""
    row = sorted(cands, key=lambda c: c["along"])
    return all(b["along"] - a["along"] >= 0.5 * (a[extent] + b[extent]) + GAP_PT for a, b in zip(row, row[1:]))


class _Rails:
    """One layout: the frame, what labels keep clear of and the boxes placed so far."""

    def __init__(self, frame: Frame, kx, ky, keep_out_pt: float, occupied: Sequence[Box]):
        self.frame = frame
        self.kx, self.ky = kx, ky
        self.keep_out_pt = keep_out_pt
        self.placed: List[Box] = list(occupied)

    def boxes_free(self, cands: List[dict]) -> bool:
        """Whether the boxes lie in the frame, clear of the processes, the boxes placed and each other."""
        boxes = [c["box"] for c in cands]
        for i, box in enumerate(boxes):
            if not box.inside(self.frame.width_pt, self.frame.height_pt, 0.0):
                return False
            if box.near_points(self.kx, self.ky, self.keep_out_pt):
                return False
            if any(box.overlaps(other, PAD_PT) for other in self.placed):
                return False
            if any(box.overlaps(other, PAD_PT) for other in boxes[i + 1:]):
                return False
        return True


def _candidates_on(slot, members, pieces, levels, frame: Frame, bound_of) -> List[dict]:
    """The label positions of one family on one rail, one per line that reaches it."""
    edge, k = slot
    out = []
    for index, request in enumerate(members):
        width, height = text_size_pt(request.text, request.style)
        for piece in pieces[index]:
            if k < 0:
                hit = crossing(piece, edge, 0.0, frame)
                if hit is None:
                    continue
                along = hit[0] if edge == "top" else hit[1]
                out.append({"request": request, "x": hit[0], "y": hit[1], "along": along, "w": width,
                            "h": height, "level": levels[index]})
                break
            found = inner_candidate(piece, edge, bound_of(k), 0.5 * width, 0.5 * height, frame)
            if found is not None:
                box, direction = found
                along = box.cx if edge in ("top", "bottom") else box.cy
                out.append({"request": request, "box": box, "direction": direction, "along": along,
                            "level": levels[index]})
                break
    return out


def _select(slot, cands: List[dict], rails: _Rails) -> Tuple[List[dict], bool]:
    """(chosen, vertical) on a rail: outer rails by spacing along the row, inner ones by boxes."""
    edge, k = slot
    if not cands:
        return [], False
    if k >= 0:
        return choose(cands, rails.boxes_free), False
    limit = rails.frame.width_pt if edge == "top" else rails.frame.height_pt

    def row(extent):
        # Labels stay within the length of the frame, so that the two outer rails never meet at the corner
        within = [c for c in cands if c["along"] - 0.5 * c[extent] >= 0.0 and c["along"] + 0.5 * c[extent] <= limit]
        return choose(within, lambda cs: _fits_on_line(cs, extent)) if within else []
    if edge == "right":
        return row("h"), False
    horizontal, vertical = row("w"), row("h")
    if len(vertical) > len(horizontal):
        return vertical, True
    return horizontal, False


def _end_candidates(members, pieces, levels) -> List[dict]:
    """A label near the inner end of each line that ends inside the plot, turned along the line."""
    out = []
    for index, request in enumerate(members):
        width, height = text_size_pt(request.text, request.style)
        for piece in pieces[index]:
            if piece.length <= END_MIN_PT or (piece.end_edge is not None and piece.start_edge is not None):
                continue
            s = piece.length - (0.5 * width + END_GAP_PT) if piece.end_edge is None else 0.5 * width + END_GAP_PT
            c = _candidate(piece, s, 0.5 * width, 0.5 * height, 0.0)
            if c is not None:
                out.append({"request": request, "box": c.box, "direction": c.direction, "along": c.box.cx,
                            "level": levels[index]})
                break
    return out


def _previous_slot(members, previous: Dict[str, Text], frame: Frame, second_bound: float):
    """The rail most labels of a family sat on in the previous layout, or None."""
    votes: Dict[Tuple[str, int], int] = {}
    for request in members:
        old = previous.get(request.id)
        if old is None:
            continue
        if not old.clip:
            slot = ("top", -1) if old.offset_pt[1] > 0.0 else ("right", -1)
        else:
            (px,), (py,) = frame.to_pt([old.x], [old.y])
            if not (math.isfinite(px) and math.isfinite(py)):
                continue
            depths = [(_depth(edge, px, py, frame), i, edge) for i, edge in enumerate(EDGES)]
            depth, _, edge = min(depths)
            slot = (edge, 0 if depth < second_bound else 1)
        votes[slot] = votes.get(slot, 0) + 1
    if not votes:
        return None
    return max(sorted(votes), key=lambda s: votes[s])


def _outer_items(c: dict, edge: str, vertical: bool, frame: Frame) -> List:
    """The tick on the frame and the label outside it."""
    request = c["request"]
    if edge == "top":
        ex, ey, ix, iy = c["x"], frame.height_pt, c["x"], frame.height_pt - TICK_PT
        offset = (0.0, OUTER_GAP_PT)
        style = request.style.with_(h_align="left" if vertical else "center",
                                    v_align="center" if vertical else "bottom")
        direction = (0.0, 1.0) if vertical else None
    else:
        ex, ey, ix, iy = frame.width_pt, c["y"], frame.width_pt - TICK_PT, c["y"]
        offset = (OUTER_GAP_PT, 0.0)
        style = request.style.with_(h_align="left", v_align="center")
        direction = None
    (dx0, dx1), (dy0, dy1) = frame.to_data([ex, ix], [ey, iy])
    line_id = request.id[:-len("/label")] if request.id.endswith("/label") else request.id
    tick = Line(id=line_id + "/tick", group=request.group, role="label_tick", x=np.array([dx0, dx1]),
                y=np.array([dy0, dy1]),
                style=LineStyle(color=request.line_color or request.style.color, width_pt=TICK_WIDTH_PT),
                z_order=4.0)
    text = Text(id=request.id, group=request.group, role="isoline_label", x=float(dx0), y=float(dy0),
                text=request.text, direction=direction, style=style, offset_pt=offset, clip=False, z_order=4.0)
    return [tick, text]


def _kept(old: Optional[Text], new: Text, frame: Frame) -> Text:
    """The old label item where the new one is the same label in the same place, else the new one."""
    if old is None or old.text != new.text or old.style != new.style or old.clip != new.clip \
            or old.offset_pt != new.offset_pt or (old.direction is None) != (new.direction is None):
        return new
    (ox, nx), (oy, ny) = frame.to_pt([old.x, new.x], [old.y, new.y])
    if not (math.isfinite(ox) and math.isfinite(oy)) or math.hypot(nx - ox, ny - oy) >= 0.5:
        return new
    if old.direction is not None:
        old_angle = math.atan2(*frame_direction(frame, old)[::-1])
        new_angle = math.atan2(*frame_direction(frame, new)[::-1])
        if abs(old_angle - new_angle) > 1e-3:
            return new
    return old


def frame_direction(frame: Frame, text: Text) -> Tuple[float, float]:
    """The direction of a text on screen, in points."""
    (x0, x1), (y0, y1) = frame.to_pt([text.x, text.x + text.direction[0]], [text.y, text.y + text.direction[1]])
    return float(x1 - x0), float(y1 - y0)


def place_rail_labels(requests: Sequence[LabelRequest], frame: Frame, keep_out_lines, keep_out_pt: float,
                      previous: Optional[Dict[str, Text]] = None, occupied: Sequence[Box] = (),
                      outer_right: bool = True) -> List:
    """Ticks and labels for the requests, see the module docstring.

    ``requests`` are in order of importance; a request's ``text`` is what
    the label says (the bare value) and ``value`` the value it shows, by
    which the family is thinned. ``keep_out_lines``, ``previous`` and
    ``occupied`` are as for :func:`coolplot.compose.layout.place_edge_labels`.
    ``outer_right`` is False when the legend sits outside on the right,
    where the outer rail would be.
    """
    if not frame.usable or not requests:
        return []
    previous = previous or {}
    kx, ky = keep_out_points(frame, keep_out_lines)
    rails = _Rails(frame, kx, ky, keep_out_pt, occupied)
    height = max(LINE_HEIGHT * r.style.font.size_pt for r in requests)

    def bound_of(k: int) -> float:
        return PAD_PT + k * SECOND_RAIL * height

    families: Dict[str, List[LabelRequest]] = {}
    for request in requests:
        families.setdefault(request.family, []).append(request)
    pieces = {key: [visible_pieces(*frame.to_pt(r.x, r.y), frame.width_pt, frame.height_pt) for r in members]
              for key, members in families.items()}
    levels = {key: value_levels([r.value for r in members]) for key, members in families.items()}
    rail_slots = slots(outer_right)

    # How many labels of each family fit on each rail, on their own
    scores = {}
    for key, members in families.items():
        for slot in rail_slots:
            cands = _candidates_on(slot, members, pieces[key], levels[key], frame, bound_of)
            scores[key, slot] = len(_select(slot, cands, rails)[0])
    # Rails go to the family that fits the most labels there; the rail of
    # the previous layout counts one label more, so that a family does not
    # jump between rails that fit about as many
    kept = {key: _previous_slot(members, previous, frame, bound_of(1)) for key, members in families.items()}
    family_order = list(families)
    pairs = sorted(scores, key=lambda ks: (-(scores[ks] + (1 if kept[ks[0]] == ks[1] else 0)), ks[1][1] >= 0,
                                           rail_slots.index(ks[1]), family_order.index(ks[0])))
    assignment: Dict[str, Tuple[str, int]] = {}
    for key, slot in pairs:
        if scores[key, slot] < min(2, len(families[key])) or key in assignment or slot in assignment.values():
            continue
        assignment[key] = slot

    items: List = []

    def place(slot, chosen, vertical):
        for c in sorted(chosen, key=lambda c: c["along"]):
            if slot[1] < 0:
                tick, text = _outer_items(c, slot[0], vertical, frame)
                items.extend([tick, _kept(previous.get(text.id), text, frame)])
            else:
                rails.placed.append(c["box"])
                text = _text(c["request"], frame, c["box"], c["direction"])
                items.append(_kept(previous.get(text.id), text, frame))

    reached: Dict[str, set] = {}
    for key, slot in sorted(assignment.items(), key=lambda ks: (ks[1][1] >= 0, rail_slots.index(ks[1]))):
        cands = _candidates_on(slot, families[key], pieces[key], levels[key], frame, bound_of)
        reached[key] = {c["request"].id for c in cands}
        place(slot, *_select(slot, cands, rails))
    # A second rail for the lines of a family that do not reach its first rail
    taken = set(assignment.values())
    for key in family_order:
        if key not in assignment:
            continue
        rest = [i for i, r in enumerate(families[key]) if r.id not in reached[key]]
        if len(rest) < 2:
            continue
        members = [families[key][i] for i in rest]
        rest_pieces = [pieces[key][i] for i in rest]
        rest_levels = [levels[key][i] for i in rest]   # the levels of the whole family
        best = None
        for slot in rail_slots:
            if slot in taken:
                continue
            chosen, vertical = _select(slot, _candidates_on(slot, members, rest_pieces, rest_levels, frame,
                                                            bound_of), rails)
            if len(chosen) >= 2 and (best is None or len(chosen) > len(best[1])):
                best = (slot, chosen, vertical)
        if best is not None:
            taken.add(best[0])
            place(*best)
    # Families without a rail: a label near the end of each line that ends inside the plot
    for key in family_order:
        if key in assignment:
            continue
        chosen = choose(_end_candidates(families[key], pieces[key], levels[key]), rails.boxes_free)
        for c in sorted(chosen, key=lambda c: c["along"]):
            rails.placed.append(c["box"])
            text = _text(c["request"], frame, c["box"], c["direction"])
            items.append(_kept(previous.get(text.id), text, frame))
    return items
