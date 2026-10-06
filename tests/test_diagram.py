# -*- coding: utf-8 -*-
"""PropertyDiagram: settings in, scene out, with selective recalculation."""
import warnings

import numpy as np
import pytest

pytest.importorskip("CoolProp")

from CoolPlot import PropertyDiagram  # noqa: E402
from CoolPlot.render.svg import SvgRenderer  # noqa: E402
from CoolPlot.scene import Line, Markers, Text  # noqa: E402
from CoolPlot.thermo import process_path, state_point  # noqa: E402


@pytest.fixture
def diagram():
    d = PropertyDiagram("HEOS::R290", "ph", units="EUR", tp_limits="ACHP")
    d.set_isolines("Q", num=3)
    d.set_isolines("T", values=[-20.0, 0.0, 20.0, 40.0], points=60)
    return d


def test_scene_content(diagram):
    scene = diagram.update_scene()
    assert sorted(i.group for i in scene if isinstance(i, Line)) == ["iso/Q"] * 3 + ["iso/T"] * 4
    assert "iso/T/273.15" in scene
    assert scene.axes.y_log and not scene.axes.x_log
    assert scene.axes.x_label == "Specific enthalpy h / kJ/kg"
    # Coordinates are in display units: kJ/kg and bar
    line = scene["iso/T/273.15"]
    assert 100.0 < np.nanmax(line.x) < 1000.0
    assert 0.25 <= np.nanmin(line.y) and np.nanmax(line.y) < 200.0


def test_unit_change_recomputes_nothing(diagram):
    diagram.update_scene()
    renderer = SvgRenderer()
    renderer.sync(diagram.scene)
    misses = diagram.cache.misses
    diagram.units = "SI"
    report = renderer.sync(diagram.update_scene())
    assert diagram.cache.misses == misses
    assert report.axes_changed and len(report.updated) == 7
    assert np.nanmax(diagram.scene["iso/T/273.15"].x) > 1e5  # now J/kg


def test_style_change_redraws_only_that_family(diagram):
    renderer = SvgRenderer()
    renderer.sync(diagram.update_scene())
    misses = diagram.cache.misses
    diagram.set_isoline_style("T", color="blue")
    report = renderer.sync(diagram.update_scene())
    assert diagram.cache.misses == misses
    assert sorted(report.updated) == sorted(i.id for i in diagram.scene.group("iso/T"))
    assert report.unchanged == 3 and not report.axes_changed


def test_adding_a_line_computes_only_that_line(diagram):
    renderer = SvgRenderer()
    renderer.sync(diagram.update_scene())
    misses = diagram.cache.misses
    diagram.set_isolines("T", values=[-20.0, 0.0, 20.0, 40.0, 60.0], points=60)
    report = renderer.sync(diagram.update_scene())
    assert diagram.cache.misses == misses + 1
    assert report.added == ["iso/T/333.15"] and report.updated == []


def test_zoom_needs_no_calculation(diagram):
    diagram.update_scene()
    misses = diagram.cache.misses
    diagram.set_view(x_limits=(200.0, 700.0), y_limits=(1.0, 50.0))
    scene = diagram.update_scene()
    assert diagram.cache.misses == misses
    assert scene.axes.x_limits == (200.0, 700.0)
    diagram.units = "KSI"
    assert diagram.update_scene().axes.y_limits == pytest.approx((100.0, 5000.0))


def test_moving_a_cycle_touches_only_the_cycle(diagram):
    fluid = diagram.fluid
    renderer = SvgRenderer()

    def cycle(p_high_Pa):
        evap_out = state_point(fluid, "p", 3e5, "T", 270.0)
        comp_out = state_point(fluid, "p", p_high_Pa, "s", evap_out.s)
        cond_out = state_point(fluid, "p", p_high_Pa, "Q", 0.0)
        valve_out = state_point(fluid, "p", 3e5, "h", cond_out.h)
        line = (process_path(fluid, evap_out, comp_out, ("p", "s"), 10)
                + [cond_out, valve_out, evap_out])
        return line, [evap_out, comp_out, cond_out, valve_out]

    diagram.set_process("cycle", *cycle(15e5))
    scene = diagram.update_scene()
    assert isinstance(scene["process/cycle/line"], Line)
    assert isinstance(scene["process/cycle/points"], Markers)
    renderer.sync(scene)

    misses = diagram.cache.misses
    diagram.set_process("cycle", *cycle(18e5))
    report = renderer.sync(diagram.update_scene())
    assert diagram.cache.misses == misses
    assert sorted(report.updated) == ["process/cycle/line", "process/cycle/points"]


def test_labels_follow_lines(diagram):
    diagram.set_isolines("T", values=[0.0], labels=True)
    label = diagram.update_scene()["iso/T/273.15/label"]
    assert isinstance(label, Text)
    assert label.text == "T=0 deg C"
    assert label.direction is not None


def test_state_at_cursor(diagram):
    state = diagram.state_at(500.0, 5.0)  # h in kJ/kg, p in bar
    assert state.h == pytest.approx(5e5)
    assert state.p == pytest.approx(5e5)


def test_invalid_requests(diagram):
    with pytest.raises(ValueError):
        diagram.set_isolines("p")  # an isobar is a horizontal line in a ph chart
    with pytest.raises(ValueError):
        PropertyDiagram("R290", "ab")


def test_matplotlib_round_trip(tmp_path, diagram):
    pytest.importorskip("matplotlib")
    from CoolPlot.render.mpl import MatplotlibRenderer
    renderer = MatplotlibRenderer(use_pyplot=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        diagram.draw(renderer)
    renderer.save(str(tmp_path / "r290.png"))
    assert (tmp_path / "r290.png").stat().st_size > 1000
