# -*- coding: utf-8 -*-
"""Isoline labels on rails along the frame (label mode "rails", 1.2)."""
import math

import numpy as np
import pytest

from coolplot.compose.layout import Box, Frame, text_size_pt
from coolplot.compose.rails import choose, value_levels
from coolplot.scene import Line, Text


def test_values_are_levelled_by_multiples_of_their_step():
    values = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert value_levels(values) == [0, 3, 2, 3, 2, 1, 2, 3, 2, 3, 0]
    assert value_levels([0.75, 1.0, 1.25, 1.5, 2.5]) == [3, 2, 1, 2, 0]
    assert value_levels([5.0]) == [0] and value_levels([1.0, float("nan")]) == [0, 0]


def test_choose_drops_whole_levels_then_fills_greedily():
    cands = [{"level": level, "along": float(i), "value": 10.0 * i}
             for i, level in enumerate([0, 3, 2, 3, 1, 3, 2, 3, 0])]
    assert [c["along"] for c in choose(cands, lambda cs: len(cs) <= 5)] == [0.0, 2.0, 4.0, 6.0, 8.0]
    assert [c["along"] for c in choose(cands, lambda cs: len(cs) <= 2)] == [0.0, 8.0]
    # Not even the coarsest level fits: one by one, coarsest first
    assert [c["along"] for c in choose(cands, lambda cs: len(cs) <= 1)] == [0.0]
    # The coarsest level is blocked (the label at 0): evenly spaced values keep every m-th label
    free = lambda cs: all(c["along"] > 0.5 for c in cs) and len(cs) <= 4   # noqa: E731
    assert [c["along"] for c in choose(cands, free)] == [1.0, 3.0, 5.0, 7.0]
    # Not evenly spaced: one by one
    uneven = [dict(c, value=v) for c, v in zip(cands, [1, 2, 5, 10, 20, 50, 100, 200, 500])]
    assert [c["along"] for c in choose(uneven, free)] == [8.0, 4.0, 2.0, 6.0]


pytest.importorskip("CoolProp")
from coolplot import PropertyDiagram, PsychrometricChart  # noqa: E402

SIZE = (600.0, 420.0)


def _rails(chart, legend="auto"):
    chart.settings = chart.settings.with_(labels={"mode": "rails"})
    t = chart.theme
    chart.theme = t.with_(axes=t.axes.with_(legend=t.axes.legend.with_(location=legend)))
    return chart


def _ph():
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    d.set_lines("T", values=list(range(-40, 181, 10)), labels=True)
    d.set_lines("s", values=[x / 100.0 for x in range(75, 301, 25)], labels=True)
    d.set_lines("rho", values=[1, 2, 5, 10, 20, 50, 100, 200, 500], labels=True)
    d.set_lines("Q", values=[x / 10.0 for x in range(0, 11)], labels=True)
    d.add_cycle("Heat pump", [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
                              {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}])
    return _rails(d)


def _frame(scene):
    a = scene.axes
    return Frame(a.x_limits, a.y_limits, a.x_log, a.y_log, *SIZE)


def _inner_boxes(scene, frame):
    boxes = []
    for t in scene:
        if t.role != "isoline_label" or not t.clip:
            continue
        (px,), (py,) = frame.to_pt([t.x], [t.y])
        angle = 0.0
        if t.direction is not None:
            (x0, x1), (y0, y1) = frame.to_pt([t.x, t.x + t.direction[0]], [t.y, t.y + t.direction[1]])
            angle = math.atan2(y1 - y0, x1 - x0)
        w, h = text_size_pt(t.text, t.style)
        boxes.append((t, Box(float(px), float(py), angle, 0.5 * w, 0.5 * h)))
    return boxes


def test_rails_write_bare_values_with_ticks_and_units_in_the_legend():
    chart = _ph()
    scene = chart.update_scene(SIZE)
    labels = [t for t in scene if t.role == "isoline_label"]
    ticks = [t for t in scene if t.role == "label_tick"]
    assert len(labels) > 25
    assert all(not any(ch.isalpha() for ch in t.text) for t in labels)   # numbers only
    outer = [t for t in labels if not t.clip]
    assert outer and len(ticks) == len(outer)
    for tick in ticks:
        assert isinstance(tick, Line) and tick.group.endswith("/label") and tick.id.endswith("/tick")
        assert scene[tick.id[:-len("/tick")] + "/label"].clip is False
    legends = {i.legend for i in scene if i.legend}
    assert {"Temperature T / deg C", "Specific entropy s / kJ/kg/K", "Density rho / kg/m3",
            "Vapour quality x", "Saturation"} <= legends
    assert scene.axes.style.legend.location in ("upper left", "upper right", "lower left", "lower right")


def test_rail_labels_stay_in_the_frame_and_clear_of_each_other_the_cycle_and_the_legend():
    chart = _ph()
    scene = chart.update_scene(SIZE)
    frame = _frame(scene)
    boxes = _inner_boxes(scene, frame)
    assert boxes
    for i, (_, box) in enumerate(boxes):
        assert box.inside(frame.width_pt, frame.height_pt, -0.5)
        for _, other in boxes[i + 1:]:
            assert not box.overlaps(other, 0.0)
    from coolplot.compose.layout import keep_out_points
    cycle = [(i.x, i.y) for i in scene if i.group == "cycle/Heat pump" and isinstance(i, Line)]
    kx, ky = keep_out_points(frame, cycle)
    assert not any(box.near_points(kx, ky, chart.settings.labels.keep_out_pt - 0.5) for _, box in boxes)
    # The legend's box, estimated as the composer does
    from coolplot.compose.corners import corner_box, legend_size_pt
    texts = list(dict.fromkeys(i.legend for i in scene if i.legend and i.visible))
    legend = corner_box(frame, scene.axes.style.legend.location,
                        *legend_size_pt(texts, chart.theme.axes.legend.text.font.size_pt), 6.0)
    assert not any(box.overlaps(legend, 0.0) for _, box in boxes)


def test_outer_labels_keep_to_the_length_of_the_frame():
    scene = _ph().update_scene(SIZE)
    frame = _frame(scene)
    for t in scene:
        if t.role == "isoline_label" and not t.clip:
            (px,), (py,) = frame.to_pt([t.x], [t.y])
            if t.offset_pt[1] > 0.0:   # top rail
                assert -1e-6 <= px <= frame.width_pt + 1e-6 and py == pytest.approx(frame.height_pt)
            else:
                assert -1e-6 <= py <= frame.height_pt + 1e-6 and px == pytest.approx(frame.width_pt)


def test_an_outside_legend_leaves_the_right_rail_free():
    scene = _rails(_ph(), legend="outside right").update_scene(SIZE)
    assert scene.axes.style.legend.location == "outside right"
    assert not any(t.role == "isoline_label" and not t.clip and t.offset_pt[0] > 0.0 for t in scene)
    assert any(t.role == "isoline_label" and not t.clip and t.offset_pt[1] > 0.0 for t in scene)


def test_a_family_leaving_through_two_edges_gets_a_second_rail():
    chart = _rails(PsychrometricChart(T_range=(-10, 45), W_range=(0, 25)))
    chart.set_default_lines()
    scene = chart.update_scene(SIZE)
    rh = sorted(float(t.text) for t in scene if t.role == "isoline_label" and t.id.startswith("iso/RH/"))
    assert rh[0] <= 20.0 and rh[-1] >= 80.0 and len(rh) >= 7


def test_a_short_rail_drops_whole_levels_of_values():
    chart = _ph()
    scene = chart.update_scene((260.0, 420.0))
    shown = sorted(float(t.text) for t in scene if t.role == "isoline_label" and t.id.startswith("iso/T/"))
    assert 2 <= len(shown) < 23   # all temperature lines reach the top: one rail, thinned
    steps = np.diff(shown)
    assert np.allclose(steps, steps[0])   # one regular step, no irregular gaps


def test_the_layout_is_stable_and_keeps_its_items():
    chart = _ph()
    first = chart.update_scene(SIZE)
    labels = {t.id: t for t in first if t.role == "isoline_label"}
    again = chart.update_scene(SIZE)
    for key, t in labels.items():
        assert again[key] is t
    # Dragging a state a little moves few labels, and no family changes its rail
    chart.move_cycle_state("Heat pump", 2, 690.0, 15.0)
    moved = chart.update_scene(SIZE)
    kept = sum(1 for key, t in labels.items() if key in moved and moved[key] is t)
    assert kept >= 0.8 * len(labels)


def test_the_legend_and_the_badge_never_share_a_corner(tmp_path):
    from coolplot.spec.settings import BrandingSettings
    chart = _ph()
    for location in ("auto", "upper left", "lower right"):
        chart.settings = chart.settings.with_(branding=BrandingSettings(lines=("CoolPlot test",), location=location))
        scene = chart.update_scene(SIZE)
        assert scene.axes.badge is not None
        assert scene.axes.badge.location != scene.axes.style.legend.location
        if location != "auto":
            assert scene.axes.badge.location == location


def test_an_auto_legend_in_a_scene_made_by_hand_reads_as_a_corner():
    from coolplot.scene import AxesSpec
    from coolplot.style.values import AxesStyle, LegendStyle
    axes = AxesSpec(style=AxesStyle(legend=LegendStyle(location="auto")))
    assert axes.style.legend.location == "upper right"


def test_texts_of_rails_draw_with_every_backend(tmp_path):
    chart = _ph()
    from coolplot.render.svg import SvgRenderer
    chart.draw(SvgRenderer(width=900, height=650)).save(str(tmp_path / "rails.svg"))
    svg = (tmp_path / "rails.svg").read_text()
    assert "cp-role-label_tick" in svg and "Temperature T / deg C" in svg
    pytest.importorskip("matplotlib")
    chart.save(str(tmp_path / "rails.png"))
    assert (tmp_path / "rails.png").stat().st_size > 10000
    assert isinstance(next(t for t in chart.scene if t.role == "isoline_label"), Text)


def test_matplotlib_lifts_the_title_above_the_top_rail():
    pytest.importorskip("matplotlib")
    import matplotlib
    from coolplot.render.mpl import MatplotlibRenderer
    chart = _ph()
    chart.title = "R290"
    renderer = chart.draw(MatplotlibRenderer(use_pyplot=False))
    top = [t for t in chart.scene if t.role == "isoline_label" and not t.clip and t.offset_pt[1] > 0.0]
    assert top
    figure = renderer.figure
    figure.canvas.draw()
    title = renderer.ax.title.get_window_extent()
    for t in top:
        artist = next(a for a in renderer.ax.texts if a.get_text() == t.text and a.get_clip_on() is False)
        assert artist.get_window_extent().y1 <= title.y0 + 1.0
    assert renderer._title_pad > matplotlib.rcParams["axes.titlepad"]


def test_a_redraw_with_nothing_changed_moves_no_label():
    # Relative humidity and wet-bulb temperature take second rails on a low chart; laying it out
    # again with the first layout as the previous one keeps every label
    chart = _rails(PsychrometricChart(T_range=(-10, 45), W_range=(0, 25)))
    chart.set_default_lines()
    first = chart.update_scene((500.0, 180.0))
    labels = {t.id: t for t in first if t.role == "isoline_label"}
    again = chart.update_scene((500.0, 180.0))
    assert {t.id for t in again if t.role == "isoline_label"} == set(labels)
    assert all(again[key] is t for key, t in labels.items())


def test_an_automatic_legend_keeps_clear_of_cycles_where_it_can():
    from coolplot.compose.corners import CORNERS, corner_box, legend_size_pt
    from coolplot.compose.layout import keep_out_points
    inside = 0
    for size in ((218.0, 117.0), (400.0, 300.0), (600.0, 420.0)):
        chart = _ph()
        scene = chart.update_scene(size)
        location = scene.axes.style.legend.location
        assert location != "outside right"   # judged against the page, not the plot area left
        a = scene.axes
        frame = Frame(a.x_limits, a.y_limits, a.x_log, a.y_log, *size)
        texts = list(dict.fromkeys(i.legend for i in scene if i.legend and i.visible))
        width, height = legend_size_pt(texts, chart.theme.axes.legend.text.font.size_pt)
        cycle = [(i.x, i.y) if isinstance(i, Line) else (i.x, i.y, False)
                 for i in scene if i.group == "cycle/Heat pump" and not isinstance(i, Text)]
        px, py = keep_out_points(frame, cycle)

        def covered(corner):
            box = corner_box(frame, corner, width, height, 6.0)
            return int(np.count_nonzero((np.abs(px - box.cx) <= box.half_w) & (np.abs(py - box.cy) <= box.half_h)))
        assert covered(location) == min(covered(c) for c in CORNERS), size
        inside += covered(location) == 0
    assert inside >= 2
    # On a small page the legend would cover more than a quarter of the plot area: it goes outside
    small = _ph()
    small.settings = small.settings.with_(page={"width_pt": 240.0, "height_pt": 170.0})
    assert small.update_scene((170.0, 130.0)).axes.style.legend.location == "outside right"


def test_edge_labels_keep_clear_of_a_legend_inside():
    chart = _ph()
    chart.settings = chart.settings.with_(labels={"mode": "edge"})
    scene = chart.update_scene(SIZE)
    a = scene.axes
    assert a.style.legend.location != "outside right"
    from coolplot.compose.corners import corner_box, legend_size_pt
    frame = _frame(scene)
    texts = list(dict.fromkeys(i.legend for i in scene if i.legend and i.visible))
    legend = corner_box(frame, a.style.legend.location,
                        *legend_size_pt(texts, chart.theme.axes.legend.text.font.size_pt), 6.0)
    assert not any(box.overlaps(legend, 0.0) for _, box in _inner_boxes(scene, frame))


def test_plotly_keeps_rail_labels_outside_the_frame_and_makes_room_for_them():
    pytest.importorskip("plotly")
    from coolplot.render.plotly import PlotlyRenderer
    chart = _ph()
    chart.title = "R290"
    renderer = PlotlyRenderer()
    renderer.sync(chart.update_scene(SIZE))   # laid out with the temperatures upright at the top
    assert any(t.role == "isoline_label" and not t.clip and t.direction is not None for t in chart.scene)
    margin = renderer.figure.layout.margin
    assert margin.t > renderer.margins[2]
    turned = [a for a in renderer.figure.layout.annotations
              if a.name and chart.scene[a.name].role == "isoline_label" and not chart.scene[a.name].clip
              and a.textangle]
    assert turned and all(a.xanchor == "center" and a.yanchor == "middle" and a.yshift > 4.0 for a in turned)


@pytest.mark.parametrize("writer", ["svg", "plotly"])
def test_the_labels_are_laid_out_for_the_plot_area_they_are_drawn_in(writer):
    """Outer labels widen a margin; laid out again for the smaller plot area, the layout must settle."""
    if writer == "plotly":
        pytest.importorskip("plotly")
        from coolplot.render.plotly import PlotlyRenderer as Writer
        sizes = [(520, 360), (700, 450)]
    else:
        from coolplot.render.svg import SvgRenderer as Writer
        sizes = [(700, 450), (520, 360)]
    for width, height in sizes:
        chart = _rails(PsychrometricChart(T_range=(-10, 45), W_range=(0, 25)))
        chart.set_default_lines()
        chart.title = "Humid air"
        renderer = Writer(width=width, height=height)
        chart.draw(renderer)
        laid_out = chart._plot_size_pt
        for _ in range(3):   # redraws as an interactive chart would make them
            renderer.sync(chart.update_scene(renderer.plot_size_pt()))
        assert tuple(renderer.plot_size_pt()) == pytest.approx(tuple(chart._plot_size_pt), abs=0.01)
        assert len({tuple(round(v, 2) for v in s) for s in (laid_out, chart._plot_size_pt)}) <= 2


def test_a_straight_segment_counts_along_its_whole_length():
    from coolplot.compose.corners import place_corners
    frame = Frame((0.0, 100.0), (0.0, 100.0), False, False, 600.0, 420.0)
    # One segment from (60, 0) to (100, 40): its end points lie outside a legend in the lower right, its middle inside
    legend_at, _, _ = place_corners(frame, [], [([60.0, 100.0], [0.0, 40.0])], ("auto", 150.0, 60.0), None)
    assert legend_at != "lower right"
