# -*- coding: utf-8 -*-
"""The critical and triple points marked with a dot (DiagramSpec.marked_points, 1.6)."""
import json

import pytest

pytest.importorskip("CoolProp")

from coolplot import DiagramSpec, PropertyDiagram  # noqa: E402
from coolplot.render.svg import SvgRenderer  # noqa: E402

#: The region down to the limits of the equation of state, which starts at the triple point
FULL = [None, None, None, None]


def _marked(diagram):
    return {item.id: item for item in diagram.update_scene() if item.role == "marked_point"}


def test_nothing_is_marked_by_default():
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    assert diagram.marked_points == ()
    assert _marked(diagram) == {}
    assert "marked_points" not in diagram.spec.to_dict()   # the record of a chart without them is unchanged


def test_the_names_are_checked_and_kept_in_order():
    diagram = PropertyDiagram("R290", "ph")
    diagram.marked_points = ["Triple", "critical", "triple"]
    assert diagram.marked_points == ("critical", "triple")
    diagram.marked_points = "critical"
    assert diagram.marked_points == ("critical",)
    diagram.marked_points = None
    assert diagram.marked_points == ()
    with pytest.raises(ValueError, match="'critical', 'triple', not 'boiling'"):
        diagram.marked_points = ("boiling",)


def test_the_spec_keeps_the_points_through_json():
    diagram = PropertyDiagram("Water", "Ts", tp_limits=FULL)
    diagram.marked_points = ("critical", "triple")
    record = json.loads(json.dumps(diagram.spec.to_dict()))
    assert record["marked_points"] == ["critical", "triple"]
    assert DiagramSpec.from_dict(record) == diagram.spec


def test_the_critical_point_sits_on_top_of_the_dome():
    diagram = PropertyDiagram("CO2", "ph", units="SI", tp_limits="ACHP")
    diagram.marked_points = ("critical",)
    critical = diagram.fluid.critical
    point = _marked(diagram)["point/critical"]
    assert point.x.tolist() == pytest.approx([critical["h"]])
    assert point.y.tolist() == pytest.approx([critical["p"]])
    assert point.legend is None and point.z_order == 3.5   # above the dome and single lines, below labels


def test_the_triple_point_marks_both_ends_of_the_dome():
    diagram = PropertyDiagram("Water", "Ts", units="SI", tp_limits=FULL)
    diagram.marked_points = ("critical", "triple")
    triple = _marked(diagram)["point/triple"]
    assert triple.y.tolist() == pytest.approx([273.16, 273.16], abs=1e-3)
    assert triple.x[0] == pytest.approx(0.0, abs=1.0)        # entropy of the saturated liquid, J/kg/K
    assert triple.x[1] == pytest.approx(9155.5, abs=1.0)     # and of the saturated vapour
    # The axes are widened so that the dots are drawn whole, not cut in half at the frame
    axes = diagram.scene.axes
    assert axes.y_limits[0] < 273.16 and axes.x_limits[0] < 0.0


def test_a_point_outside_the_region_is_left_out():
    # The default region starts 1 % above the triple point
    diagram = PropertyDiagram("Water", "Ts")
    diagram.marked_points = ("critical", "triple")
    assert set(_marked(diagram)) == {"point/critical"}
    diagram.tp_limits = FULL
    assert set(_marked(diagram)) == {"point/critical", "point/triple"}


def test_the_points_do_not_stretch_the_axes_otherwise():
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    before = diagram.update_scene().axes
    diagram.marked_points = ("critical", "triple")
    after = diagram.update_scene().axes
    assert after.x_limits == before.x_limits and after.y_limits == before.y_limits


@pytest.mark.parametrize("fluid", ["HEOS::R32[0.7]&R125[0.3]", "R407C"])
def test_a_mixture_or_pseudo_pure_blend_has_no_triple_point(fluid):
    diagram = PropertyDiagram(fluid, "ph", tp_limits=FULL)
    diagram.marked_points = ("critical", "triple")
    assert set(_marked(diagram)) == {"point/critical"}


def test_the_dot_takes_the_look_of_the_saturation_curve():
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    diagram.marked_points = ("critical",)
    style = _marked(diagram)["point/critical"].style
    saturation = diagram.theme.saturation
    assert style.face_color == saturation.color and style.edge_color == saturation.casing_color
    assert style.size_pt == pytest.approx(2.0 * saturation.width_pt + 3.0)
    diagram.set_line_style("saturation", color="#7a3cc8", casing_width_pt=0.0)
    style = _marked(diagram)["point/critical"].style
    assert style.face_color == "#7a3cc8" and style.edge_color is None


def test_a_psychrometric_chart_marks_nothing():
    from coolplot import PsychrometricChart
    chart = PsychrometricChart()
    assert not hasattr(chart, "marked_points")
    with pytest.raises(ValueError, match="only in charts of a fluid"):
        chart.spec.with_(marked_points=("critical",))


def test_the_svg_draws_the_dots():
    diagram = PropertyDiagram("Water", "Ts", tp_limits=FULL)
    diagram.marked_points = ("critical", "triple")
    svg = diagram.draw(SvgRenderer()).to_svg()
    assert svg.count("<circle") >= 3
