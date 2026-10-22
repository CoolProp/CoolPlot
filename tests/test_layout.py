# -*- coding: utf-8 -*-
"""Label layout: edge labels clear of processes, margin labels, stability."""
import math

import numpy as np
import pytest

from coolplot.compose.layout import (Box, Frame, LabelRequest, keep_out_points, place_edge_labels, place_margin_labels,
                                     text_size_pt, visible_pieces)
from coolplot.core.floats import same_numbers
from coolplot.core.numbers import format_number
from coolplot.style.values import Font, TextStyle

STYLE = TextStyle(font=Font(size_pt=8.0))
FRAME = Frame((0.0, 100.0), (0.0, 100.0), False, False, 400.0, 300.0)


def _fan(n=8):
    """Straight lines fanning out from the lower left corner, like isentropes."""
    requests = []
    for i in range(n):
        slope = 0.2 + 0.4 * i
        x = np.linspace(0.0, 100.0, 50)
        requests.append(LabelRequest(id="iso/s/{0}/label".format(i), group="iso/s/label", family="s",
                                     text="s={0}".format(i), style=STYLE, x=x, y=slope * x))
    return requests


def _boxes(labels, frame):
    """Rebuild the boxes of placed labels in points."""
    out = []
    for t in labels:
        px, py = frame.to_pt([t.x], [t.y])
        w, h = text_size_pt(t.text, t.style)
        angle = 0.0
        if t.direction is not None:
            qx, qy = frame.to_pt([t.x + t.direction[0]], [t.y + t.direction[1]])
            angle = math.atan2(qy[0] - py[0], qx[0] - px[0])
            if angle > math.pi / 2:
                angle -= math.pi
            elif angle <= -math.pi / 2:
                angle += math.pi
        out.append(Box(float(px[0]), float(py[0]), angle, w / 2, h / 2))
    return out


def test_visible_pieces_know_their_edges():
    px = np.array([-10.0, 50.0, 50.0, 50.0])
    py = np.array([150.0, 150.0, 100.0, -20.0])
    (piece,) = visible_pieces(px, py, 400.0, 300.0)
    assert piece.start_edge == "left" and piece.end_edge == "bottom"
    # A line ending exactly on the frame crosses it there
    (piece,) = visible_pieces(np.array([100.0, 200.0, 400.0]), np.array([100.0, 100.0, 100.0]), 400.0, 300.0)
    assert piece.start_edge is None and piece.end_edge == "right"
    pieces = visible_pieces(np.array([-50.0, 450.0]), np.array([150.0, 150.0]), 400.0, 300.0)
    assert [(p.start_edge, p.end_edge) for p in pieces] == [("left", "right")]
    assert visible_pieces(np.array([-5.0, -1.0]), np.array([0.0, 10.0]), 400.0, 300.0) == []


def test_edge_labels_do_not_overlap_and_stay_in_the_frame():
    labels = place_edge_labels(_fan(), FRAME, [], 10.0, {"s": ("top", "right")})
    assert len(labels) >= 6
    boxes = _boxes(labels, FRAME)
    for i, a in enumerate(boxes):
        assert a.inside(400.0, 300.0, 0.5)
        for b in boxes[i + 1:]:
            assert not a.overlaps(b, 0.0)


def test_edge_labels_prefer_the_requested_edge():
    labels = place_edge_labels(_fan(4), FRAME, [], 10.0, {"s": ("right",)})
    px, _ = FRAME.to_pt([t.x for t in labels], [t.y for t in labels])
    # The flat lines leave through the right edge; their labels sit there
    assert np.sum(px > 300.0) >= 2


def test_keep_out_zone_around_a_process():
    cycle = (np.array([20.0, 80.0, 80.0, 20.0, 20.0]), np.array([20.0, 20.0, 80.0, 80.0, 20.0]))
    keep_out_pt = 12.0
    labels = place_edge_labels(_fan(), FRAME, [cycle], keep_out_pt, {"s": ("top", "right")})
    cx, cy = FRAME.to_pt(*cycle)
    # Points along the process, every point
    sx = np.concatenate([np.linspace(cx[i], cx[i + 1], 100) for i in range(4)])
    sy = np.concatenate([np.linspace(cy[i], cy[i + 1], 100) for i in range(4)])
    for box in _boxes(labels, FRAME):
        assert not box.near_points(sx, sy, keep_out_pt - 0.5)


def test_layout_is_deterministic_and_stable():
    first = place_edge_labels(_fan(), FRAME, [], 10.0, {"s": ("top",)})
    again = place_edge_labels(_fan(), FRAME, [], 10.0, {"s": ("top",)})
    assert [t.id for t in first] == [t.id for t in again]
    assert same_numbers([v for t in first for v in (t.x, t.y)], [v for t in again for v in (t.x, t.y)])
    previous = {t.id: t for t in first}
    # A process appears in a corner: labels away from it are the same items
    corner = (np.array([90.0, 99.0]), np.array([90.0, 99.0]))
    moved = place_edge_labels(_fan(), FRAME, [corner], 10.0, {"s": ("top",)}, previous)
    same = [t for t in moved if previous.get(t.id) is t]
    assert len(same) >= len(moved) - 2


def test_without_fallback_the_middle_stays_clear():
    # Many close vertical lines: only a few labels fit near the frame
    requests = []
    for i in range(30):
        x0 = 40.0 + 0.5 * i
        requests.append(LabelRequest(id=str(i), group="g", family="T", text="T={0}".format(i), style=STYLE,
                                     x=np.array([x0, x0]), y=np.array([0.0, 100.0])))
    with_fallback = place_edge_labels(requests, FRAME, [], 10.0, {"T": ("top",)})
    without = place_edge_labels(requests, FRAME, [], 10.0, {"T": ("top",)}, fallback=False)
    assert len(without) < len(with_fallback)
    _, py = FRAME.to_pt([t.x for t in without], [t.y for t in without])
    assert np.all((py > 235.0) | (py < 65.0))   # near the top or bottom edge, never mid-plot


def test_margin_labels_sit_outside_and_do_not_collide():
    labels = place_margin_labels(_fan(), FRAME, ("top", "right"))
    assert labels and all(not t.clip for t in labels)
    for t in labels:
        px, py = FRAME.to_pt([t.x], [t.y])
        on_top = abs(py[0] - 300.0) < 1e-6
        on_right = abs(px[0] - 400.0) < 1e-6
        assert on_top or on_right
        assert (t.offset_pt[1] > 0.0) if on_top else (t.offset_pt[0] > 0.0)
    tops = sorted(FRAME.to_pt([t.x for t in labels if t.direction], [0.0] * len(labels))[0])
    assert np.all(np.diff(tops) >= text_size_pt("s=0", STYLE)[1])


def test_unusable_frame_gives_no_labels():
    frame = Frame((0.0, 100.0), (0.0, 100.0), False, True, 400.0, 300.0)   # log axis from zero
    assert place_edge_labels(_fan(), frame, [], 10.0, {}) == []


@pytest.mark.parametrize("value, text", [(25.0, "25"), (0.1 + 0.2, "0.3"), (1e6, "1e6"), (2.5e-4, "2.5e-4"),
                                         (-20.0, "-20"), (100000.0, "100000"), (0.0, "0")])
def test_central_number_format(value, text):
    assert format_number(value) == text


# Regression tests from the adversarial review of 0.2 ------------------------


def test_labels_survive_a_log_view_from_zero():
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    diagram.set_lines("T", num=8, rounding=True, labels=True)
    diagram.set_view(None, (0.0, 10.0))
    scene = diagram.update_scene()
    assert scene.axes.y_limits == pytest.approx((0.01, 10.0))
    assert any(i.role == "isoline_label" for i in scene)
    with pytest.raises(ValueError):
        diagram.set_view((float("nan"), 300.0))


def test_markers_are_kept_out_as_points():
    frame = Frame((0.0, 1.0), (0.0, 1.0), False, False, 100.0, 100.0)
    px, _ = keep_out_points(frame, [([0.1, 0.9], [0.1, 0.9], False)])
    assert len(px) == 2
    px, _ = keep_out_points(frame, [([0.1, 0.9], [0.1, 0.9])])
    assert len(px) > 2


def test_a_long_state_label_turns_to_the_side_where_it_stays_inside_the_frame():
    from coolplot.compose.layout import place_state_numbers
    from coolplot.scene import Text
    frame = Frame((0.0, 10.0), (0.0, 10.0), False, False, 400.0, 300.0)
    label = Text(id="n1", group="g", role="state_number", x=9.5, y=5.0,   # 20 pt from the right edge
                 text="1: a label far too long to fit to the right of its state", offset_pt=(4.5, 4.5),
                 style=TextStyle(font=Font(size_pt=8.0), h_align="left", v_align="bottom"))
    placed = place_state_numbers([label], frame, [9.5], [5.0])
    assert placed[0].style.h_align == "right" and same_numbers(placed[0].offset_pt, (-4.5, 4.5))
