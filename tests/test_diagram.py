# -*- coding: utf-8 -*-
"""PropertyDiagram: settings in, scene out, with selective recalculation."""
import warnings

import numpy as np
import pytest

pytest.importorskip("CoolProp")

from coolplot import DiagramSpec, ProcessSpec, PropertyDiagram  # noqa: E402
from coolplot.core.floats import same_numbers  # noqa: E402
from coolplot.render.svg import SvgRenderer  # noqa: E402
from coolplot.scene import Line, Markers, Text  # noqa: E402
from coolplot.thermo import process_path, state_point  # noqa: E402


@pytest.fixture
def diagram():
    d = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    d.set_lines("Q", num=3)
    d.set_lines("T", values=[-20.0, 0.0, 20.0, 40.0], points=60)
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
    diagram.set_line_style("T", color="blue")
    report = renderer.sync(diagram.update_scene())
    assert diagram.cache.misses == misses
    assert sorted(report.updated) == sorted(i.id for i in diagram.scene.group("iso/T"))
    assert report.unchanged == 3 and not report.axes_changed


def test_the_saturation_curve_can_lose_its_casing():
    """set_line_style("saturation", ...) restyles the dome only, set_line_style("Q", ...) the quality lines."""
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP", settings="interactive")
    chart.set_lines("Q", num=5)
    chart.set_lines("T", num=4)
    scene = chart.update_scene()
    assert {i.style.casing_width_pt for i in scene if i.role == "saturation"} == {1.0}   # the default theme's casing
    renderer = SvgRenderer()
    renderer.sync(scene)
    misses = chart.cache.misses
    chart.set_line_style("Saturation", casing_width_pt=0)   # the key in any case
    chart.set_line_style("Q", color="#7a3cc8")
    report = renderer.sync(chart.update_scene())
    assert chart.cache.misses == misses   # restyled, nothing computed
    dome = [i for i in chart.scene if i.role == "saturation"]
    assert dome and all(i.style.casing_width_pt == 0.0 and i.style.color == "#0b0b0b" for i in dome)
    assert {i.style.color for i in chart.scene if i.role == "quality"} == {"#7a3cc8"}
    assert {i.style.color for i in chart.scene if i.id.startswith("iso/T/")} != {"#7a3cc8"}
    assert sorted(report.updated) == sorted(i.id for i in chart.scene if i.role in ("saturation", "quality"))
    svg = renderer.to_svg()
    dome_elements = svg.split('data-item="iso/Q/0"')[1].split("</g>")[0]
    assert "cp-casing" not in dome_elements and "cp-casing" not in svg   # no casing, also not in the legend
    # Saved and read back with the chart; without changes the theme's look returns
    assert DiagramSpec.from_dict(chart.spec.to_dict()).style_override("saturation") == {"casing_width_pt": 0}
    chart.set_line_style("saturation")
    assert {i.style.casing_width_pt for i in chart.update_scene() if i.role == "saturation"} == {1.0}


def test_adding_a_line_computes_only_that_line(diagram):
    renderer = SvgRenderer()
    renderer.sync(diagram.update_scene())
    misses = diagram.cache.misses
    diagram.set_lines("T", values=[-20.0, 0.0, 20.0, 40.0, 60.0], points=60)
    report = renderer.sync(diagram.update_scene())
    assert diagram.cache.misses == misses + 1
    assert report.added == ["iso/T/333.15"] and report.updated == []


def test_zoom_needs_no_calculation(diagram):
    diagram.update_scene()
    misses = diagram.cache.misses
    diagram.set_view(x_limits=(200.0, 700.0), y_limits=(1.0, 50.0))
    scene = diagram.update_scene()
    assert diagram.cache.misses == misses
    assert same_numbers(scene.axes.x_limits, (200.0, 700.0))
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

    # A process of complete states, as kept in the spec (contracts.md, "processes")
    diagram.spec = diagram.spec.with_process(ProcessSpec("cycle", *map(tuple, cycle(15e5))))
    scene = diagram.update_scene()
    assert isinstance(scene["process/cycle/line"], Line)
    assert isinstance(scene["process/cycle/points"], Markers)
    renderer.sync(scene)

    misses = diagram.cache.misses
    diagram.spec = diagram.spec.with_process(ProcessSpec("cycle", *map(tuple, cycle(18e5))))
    report = renderer.sync(diagram.update_scene())
    assert diagram.cache.misses == misses
    assert sorted(report.updated) == ["process/cycle/line", "process/cycle/points"]


def test_labels_follow_lines(diagram):
    diagram.settings = diagram.settings.with_(labels={"mode": "edge"})   # the full label, along its line
    diagram.set_lines("T", values=[0.0], labels=True)
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
        diagram.set_lines("p")  # an isobar is a horizontal line in a ph chart
    with pytest.raises(ValueError):
        PropertyDiagram("R290", "ab")


def test_matplotlib_round_trip(tmp_path, diagram):
    pytest.importorskip("matplotlib")
    from coolplot.render.mpl import MatplotlibRenderer
    renderer = MatplotlibRenderer(use_pyplot=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        diagram.draw(renderer)
    renderer.save(str(tmp_path / "r290.png"))
    assert (tmp_path / "r290.png").stat().st_size > 1000


# Regression tests from the adversarial review of 0.2 ------------------------

def test_no_warnings_from_a_plain_chart():
    diagram = PropertyDiagram("R290", "Ts", tp_limits="ACHP")
    diagram.set_default_lines(num=6, rounding=True, labels=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        diagram.draw(SvgRenderer())


def test_save_chooses_the_writer_by_extension(tmp_path):
    """SVG and HTML need no matplotlib; everything else goes through it."""
    from coolplot import PropertyDiagram
    diagram = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    diagram.set_lines("T", num=3)
    diagram.save(tmp_path / "chart.svg")
    diagram.save(tmp_path / "chart.html")
    diagram.save(tmp_path / "chart.png", dpi=50)
    assert (tmp_path / "chart.svg").read_text().startswith("<?xml") or "<svg" in (tmp_path / "chart.svg").read_text()
    assert "<html" in (tmp_path / "chart.html").read_text().lower()
    assert (tmp_path / "chart.png").stat().st_size > 1000


def test_svg_and_html_saves_use_the_page_size(tmp_path):
    """The canvas follows settings.page, as for matplotlib, unless a size is given.

    An SVG file states the page size in points (252 x 189 pt); an HTML page
    has it in pixels (336 x 252 px).
    """
    import re
    from coolplot import PropertyDiagram
    diagram = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP", settings="publication")
    diagram.set_lines("T", num=3)
    size = re.compile(r'<svg [^>]*width="([\d.]+(?:pt)?)" height="([\d.]+(?:pt)?)"')
    diagram.save(tmp_path / "chart.svg")
    assert size.search((tmp_path / "chart.svg").read_text()).groups() == ("252pt", "189pt")
    diagram.save(tmp_path / "chart.html")
    assert size.search((tmp_path / "chart.html").read_text()).groups() == ("336", "252")
    diagram.save(tmp_path / "wide.svg", width=500, height=300, unit="px")
    assert size.search((tmp_path / "wide.svg").read_text()).groups() == ("500", "300")
    diagram.save(tmp_path / "wide.html", width=500, height=300)
    assert size.search((tmp_path / "wide.html").read_text()).groups() == ("500", "300")


def test_changing_the_diagram_type_drops_families_it_cannot_draw():
    d = PropertyDiagram("HEOS::R290", "Ts", units="engineering", tp_limits="ACHP")
    d.set_lines("h", num=3, points=40)
    d.set_lines("p", num=3, points=40)
    d.diagram_type = "ph"   # h and p are the axes of a p-h diagram
    assert d.spec.isolines == ()
    d.set_lines("T", num=3, points=40)
    d.update_scene()   # draws without the dropped families


# The saturation curve (1.2) ------------------------------------------------

def _saturation_ids(chart):
    return [i.id for i in chart.update_scene() if i.role == "saturation"]


def test_the_saturation_curve_is_drawn_without_quality_lines():
    from coolplot import PropertyDiagram
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    d.set_lines("T", num=5)
    assert d.show_saturation is True and _saturation_ids(d) == ["iso/Q/0", "iso/Q/1"]
    d.set_lines("Q", values=[0.2, 0.5])   # quality values that leave out 0 and 1
    assert _saturation_ids(d) == ["iso/Q/0", "iso/Q/1"]
    ids = [i.id for i in d.update_scene() if i.id.startswith("iso/Q/") and not i.id.endswith("/label")]
    assert ids == ["iso/Q/0.2", "iso/Q/0.5", "iso/Q/0", "iso/Q/1"]   # next to the family's own lines


def test_the_saturation_curve_can_be_hidden():
    from coolplot import PropertyDiagram
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    d.set_lines("Q", num=11)   # 0 to 1 with the saturation curve
    d.show_saturation = False
    assert _saturation_ids(d) == []
    assert len([i for i in d.update_scene() if i.role == "quality"]) == 9


def test_a_spec_saved_before_1_2_keeps_its_look():
    from coolplot import PropertyDiagram
    from coolplot.spec import DiagramSpec
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    d.set_lines("T", num=5)
    record = d.spec.to_dict()
    assert record["show_saturation"] is True
    del record["show_saturation"]   # a record of 1.1
    old = DiagramSpec.from_dict(record)
    assert old.show_saturation is None
    d.spec = old
    assert _saturation_ids(d) == []   # no quality lines set, no curve, as in 1.1
    d.set_lines("Q", num=11)
    assert _saturation_ids(d) == ["iso/Q/0", "iso/Q/1"]   # the values decide
    with pytest.raises(ValueError, match="True, False or None"):
        d.show_saturation = "yes"


def test_an_incompressible_has_no_saturation_curve():
    from coolplot import PropertyDiagram
    d = PropertyDiagram("INCOMP::MEG[0.3]", "Ts", tp_limits=[260.0, 360.0, 1e5, 1e6])
    d.set_lines("p", num=4)
    assert _saturation_ids(d) == []


def test_a_psychrometric_chart_draws_saturated_air():
    from coolplot import PsychrometricChart
    c = PsychrometricChart()
    c.set_lines("h", num=5)
    assert _saturation_ids(c) == ["iso/RH/1"]


def test_a_range_is_two_values():
    """A single number or three numbers are refused with a message, not a numpy error."""
    from coolplot import PsychrometricChart
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP", settings="interactive")
    for bad in (50, [0, 10, 20]):
        with pytest.raises(ValueError, match="A range is two values"):
            chart.set_lines("T", num=5, range=bad)
    with pytest.raises(ValueError, match="A range is two values"):
        PsychrometricChart(T_range=20)


def test_states_may_come_in_any_mapping():
    from types import MappingProxyType
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP", settings="interactive")
    chart.add_cycle("c", MappingProxyType({1: MappingProxyType({"p": 3.0, "T": 0.0}),
                                           2: {"p": 15.0, "via": "compression", "eta_is": 0.7}}), closed=False)
    assert sorted(chart.cycle_states("c")) == [1, 2]
