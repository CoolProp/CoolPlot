# -*- coding: utf-8 -*-
"""The saturation scale next to the vertical axis (DiagramSpec.saturation_scale, 1.5)."""
import json

import pytest

pytest.importorskip("CoolProp")

from coolplot import DiagramSpec, PropertyDiagram  # noqa: E402
from coolplot.compose.builder import SCALE_INSET_PT, default_plot_size_pt  # noqa: E402
from coolplot.compose.layout import Frame  # noqa: E402
from coolplot.spec import SaturationScale  # noqa: E402


def _scale(diagram):
    return [item for item in diagram.update_scene() if item.group.startswith("scale")]


def _values(diagram):
    return [item.text for item in diagram.update_scene() if item.role == "scale_label" and item.id != "scale/title"]


def test_no_scale_by_default():
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    assert diagram.saturation_scale is None
    assert _scale(diagram) == []
    assert "saturation_scale" not in diagram.spec.to_dict()


def test_a_pressure_axis_gets_saturation_temperatures():
    diagram = PropertyDiagram("R290", "ph", units="engineering", tp_limits="ACHP")
    diagram.saturation_scale = {"step": 20}
    assert diagram.saturation_scale == SaturationScale(step_SI=20.0, Q=1.0)
    # Every 20 K within the pressures the axis shows (from 0.25 bar) up to the critical point
    assert _values(diagram) == [str(v) for v in range(-60, 81, 20)]
    title = next(i for i in diagram.scene if i.id == "scale/title")
    assert title.text == "T_sat / \u00b0C"
    # Each tick sits at the saturation pressure of its temperature
    label = next(i for i in diagram.scene if i.id.startswith("scale/label/") and i.text == "0")
    p_sat_bar = diagram.fluid.state_point("T", 273.15, "Q", 1.0).p / 1e5
    assert label.y == pytest.approx(p_sat_bar, rel=1e-9)


def test_a_temperature_axis_gets_saturation_pressures_without_overlaps():
    diagram = PropertyDiagram("Water", "Ts", units="engineering")
    diagram.saturation_scale = True
    title = next(i for i in diagram.update_scene() if i.id == "scale/title")
    assert title.text == "p_sat / bar"
    labels = [i for i in diagram.scene if i.id.startswith("scale/label/")]
    frame = Frame.from_axes(diagram.scene.axes, default_plot_size_pt(diagram.spec))
    py = sorted(float(frame.to_pt([0.0], [t.y])[1][0]) for t in labels)
    height = 1.2 * labels[0].style.font.size_pt
    assert all(b - a >= height - 1e-9 for a, b in zip(py, py[1:]))   # thinned: no two values overlap
    assert "200" in _values(diagram)


def test_the_scale_sits_inside_the_left_edge_and_does_not_move_the_axes():
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    before = diagram.update_scene().axes
    diagram.saturation_scale = True
    items = _scale(diagram)
    axes = diagram.scene.axes
    assert (axes.x_limits, axes.y_limits) == (before.x_limits, before.y_limits)
    line = next(i for i in items if i.id == "scale/line")
    frame = Frame.from_axes(axes, default_plot_size_pt(diagram.spec))
    assert float(frame.to_pt(line.x, line.y)[0][0]) == pytest.approx(SCALE_INSET_PT)
    assert line.style.color == diagram.theme.axes.tick_color


def test_isoline_labels_keep_clear_of_the_scale():
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    diagram.set_default_lines(labels=True)
    diagram.settings = diagram.settings.with_(labels={"mode": "edge"})
    diagram.saturation_scale = True
    scene = diagram.update_scene()
    frame = Frame.from_axes(scene.axes, default_plot_size_pt(diagram.spec))
    line = next(i for i in scene if i.id == "scale/line")
    x_scale = float(frame.to_pt(line.x, line.y)[0][0])
    y_lo, y_hi = sorted(float(v) for v in frame.to_pt(line.x, line.y)[1])
    for label in (i for i in scene if i.role == "isoline_label"):
        px, py = (float(v[0]) for v in frame.to_pt([label.x], [label.y]))
        assert not (px < x_scale + 25.0 and y_lo <= py <= y_hi), label.text


def test_a_blend_shows_dew_or_bubble_points():
    diagram = PropertyDiagram("HEOS::R32[0.7]&R125[0.3]", "ph", units="engineering", tp_limits="ACHP")
    diagram.saturation_scale = {"step": 20}
    dew = {i.text: i.y for i in _scale(diagram) if i.id.startswith("scale/label/")}
    diagram.saturation_scale = {"step": 20, "Q": 0}
    bubble = {i.text: i.y for i in _scale(diagram) if i.id.startswith("scale/label/")}
    assert next(i.text for i in diagram.scene if i.id == "scale/title") == "T_sat,liq / \u00b0C"
    assert bubble["0"] > dew["0"]   # the bubble point of a temperature lies at a higher pressure


def test_the_spec_keeps_the_scale_through_json():
    diagram = PropertyDiagram("R290", "ph", units="IP")
    diagram.saturation_scale = {"step": 20, "Q": 0}   # 20 deg F
    assert diagram.saturation_scale.step_SI == pytest.approx(20.0 / 1.8)
    record = json.loads(json.dumps(diagram.spec.to_dict()))
    assert DiagramSpec.from_dict(record) == diagram.spec
    diagram.saturation_scale = False
    assert diagram.saturation_scale is None


@pytest.mark.parametrize("diagram_type", ["hs", "pT", "Tp"])
def test_a_chart_without_pressure_or_temperature_alone_on_the_vertical_axis_has_no_scale(diagram_type):
    diagram = PropertyDiagram("R290", diagram_type)
    with pytest.raises(ValueError, match="needs pressure or temperature on the vertical axis"):
        diagram.saturation_scale = True


def test_the_values_given_are_checked():
    diagram = PropertyDiagram("R290", "ph")
    with pytest.raises(ValueError, match="takes 'step' and 'Q'"):
        diagram.saturation_scale = {"every": 10}
    with pytest.raises(ValueError, match="has to be positive"):
        diagram.saturation_scale = {"step": -5}
    with pytest.raises(ValueError, match="between 0 and 1"):
        diagram.saturation_scale = {"Q": 2}
