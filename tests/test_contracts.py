# -*- coding: utf-8 -*-
"""The records of docs/reference/contracts.md round-trip through JSON unchanged.

The spec, the curve record and the scene of a property diagram with
cycles and labels, of a psychrometric chart with an air process, and of
the conformance scene (every item type) are written as JSON, read back
and written again; the two texts have to be identical.
"""
import json

import numpy as np
import pytest

from coolplot.core.floats import same_arrays
from coolplot.testing import conformance_scene
from coolplot.scene import Scene, items_equal

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _twice(data) -> str:
    text = json.dumps(data, sort_keys=True)
    assert "NaN" not in text and "Infinity" not in text   # only null for missing values
    return text


def _scene_round_trip(scene: Scene):
    text = _twice(scene.to_dict())
    again = Scene.from_dict(json.loads(text))
    assert _twice(again.to_dict()) == text
    assert again.axes == scene.axes
    assert again.ids() == scene.draw_order()
    for item in scene:
        assert items_equal(again[item.id], item), item.id


def test_conformance_scene_round_trips():
    _scene_round_trip(conformance_scene())


def test_nan_becomes_null_and_back():
    from coolplot.scene import Line
    scene = Scene(items=[Line(id="a", x=[0.0, np.nan, 2.0], y=[1.0, np.inf, 3.0])])
    data = scene.to_dict()
    assert data["items"][0]["x"][1] is None and data["items"][0]["y"][1] is None
    again = Scene.from_dict(data)
    assert np.isnan(again["a"].x[1]) and np.isnan(again["a"].y[1])
    with pytest.raises(ValueError, match="item type"):
        Scene.from_dict({"items": [{"type": "circle", "id": "c"}]})


def _charts():
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram, PsychrometricChart
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    diagram.set_default_lines(labels=True)
    diagram.add_cycle("heat pump", [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
                                   {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}])
    chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))
    chart.set_default_lines()
    chart.add_cycle("Air conditioning", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}, {"T": 20, "W": 8.9}], closed=False)
    return diagram, chart


def test_specs_and_scenes_of_both_chart_kinds_round_trip():
    from coolplot import DiagramSpec
    for chart in _charts():
        text = _twice(chart.spec.to_dict())
        spec = DiagramSpec.from_dict(json.loads(text))
        assert spec == chart.spec and _twice(spec.to_dict()) == text
        _scene_round_trip(chart.update_scene())


def test_curve_records_round_trip():
    from coolplot.engine import plan
    from coolplot.thermo.isolines import Curve
    for chart in _charts():
        domain = chart.engine.domain(chart.spec)
        for request, curve in chart.engine.curves(chart.spec, domain, plan(chart.spec, domain))[:3]:
            text = _twice(curve.to_dict())
            again = Curve.from_dict(json.loads(text))
            assert _twice(again.to_dict()) == text
            assert same_arrays(again.x, curve.x) and again.method == curve.method


def test_complete_states_round_trip_whatever_the_key_order():
    from coolplot import DiagramSpec, StatePoint
    from coolplot.thermo.cycles import simple_compression
    assert StatePoint(T=1.0, p=2.0) == StatePoint(p=2.0, T=1.0)
    assert hash(StatePoint(T=1.0, p=2.0)) == hash(StatePoint(p=2.0, T=1.0))
    assert list(StatePoint(h=3.0, T=1.0)) == ["T", "h"] and len(StatePoint(h=3.0)) == 1
    diagram, chart = _charts()
    diagram.add_cycle(simple_compression("R290", T_evap_C=0.0, T_cond_C=40.0))
    chart.add_cycle("Copied", list(chart.cycle_states("Air conditioning").values()), closed=False)
    for c in (diagram, chart):
        text = _twice(c.spec.to_dict())
        assert DiagramSpec.from_dict(json.loads(text)) == c.spec


def test_states_of_the_other_chart_kind_are_refused():
    diagram, chart = _charts()
    air = list(chart.cycle_states("Air conditioning").values())[0]
    fluid = diagram.fluid.state_point("p", chart.p_Pa, "T", 300.0)   # at the chart's pressure, still refused
    with pytest.raises(ValueError, match="lacks"):
        diagram.add_cycle("air", [air, air])
    with pytest.raises(ValueError, match="lacks"):
        chart.add_cycle("fluid", [fluid, fluid], closed=False)
    with pytest.raises(ValueError, match="unknown properties \\['rho'\\], expected"):
        chart.add_cycle("fluid", [{"rho": 1.2, "T": 20}], closed=False)
    from coolplot import PropertyDiagram, PsychrometricChart
    with pytest.raises(ValueError, match="humid_air charts"):
        PsychrometricChart.from_spec(diagram.spec)
    with pytest.raises(ValueError, match="fluid charts"):
        PropertyDiagram.from_spec(chart.spec)
    with pytest.raises(ValueError, match="not offered"):
        from coolplot.core.diagram_type import DiagramType
        DiagramType("T", "W", "humid_air")
    chart.set_lines("RH", range=(0.0, 100.0), num=11)   # the excluded 0 % is simply left out
    assert [r.value_SI for r in __import__("coolplot.engine", fromlist=["plan"]).plan(
        chart.spec, chart.engine.domain(chart.spec)) if r.key == "RH"][0] == pytest.approx(0.1)
    with pytest.raises(ValueError, match="above 0"):
        chart.set_lines("RH", [0.0, 50.0])
    with pytest.raises(ValueError, match="fog"):
        PsychrometricChart(T_range=(0.0, 5.0), W_range=(20.0, 30.0)).update_scene()


def test_both_chart_kinds_share_the_pipeline():
    """A psychrometric chart is a DiagramSpec drawn by the same engine and composer."""
    from coolplot import Chart, DiagramSpec
    diagram, chart = _charts()
    assert isinstance(chart, Chart) and isinstance(diagram, Chart)
    assert type(chart.spec) is DiagramSpec is type(diagram.spec)
    assert chart.spec.diagram.kind == "humid_air" and chart.spec.diagram.name == "WT"
    assert type(chart.engine) is type(diagram.engine)
    ids = {i.id for i in chart.update_scene()}
    assert "iso/RH/0.5" in ids and "cycle/Air conditioning/states" in ids
    state = chart.cycle_states("Air conditioning")[2]
    assert state.RH == pytest.approx(0.95) and "W" in state and "rho" not in state


def test_a_diagram_type_without_a_short_name_round_trips():
    from coolplot import DiagramSpec
    from coolplot.core.diagram_type import DiagramType
    from coolplot.spec import FluidSpec
    spec = DiagramSpec(fluid=FluidSpec.parse("HEOS::R290"), diagram=DiagramType("T", "h"))
    assert spec.to_dict()["diagram"] == "Th"
    assert DiagramSpec.from_dict(json.loads(json.dumps(spec.to_dict()))) == spec
    with pytest.raises(ValueError, match="Unknown diagram type"):
        DiagramType.parse("Tq")


def test_regions_with_the_same_bounds_are_equal():
    from coolplot.core.limits import Region
    region = Region((("T", (263.15, 323.15)), ("W", (0.0, 0.03))))
    changed = region.with_range("T", 273.15, 313.15)
    same = Region((("W", (0.0, 0.03)), ("T", (273.15, 313.15))))
    assert changed == same and hash(changed) == hash(same)
    assert Region.from_dict(json.loads(json.dumps(changed.to_dict(), sort_keys=True))) == changed


def test_a_scene_record_with_a_repeated_id_is_refused():
    data = conformance_scene().to_dict()
    data["items"].append(dict(data["items"][0]))
    with pytest.raises(ValueError, match="Duplicate item id"):
        Scene.from_dict(data)
