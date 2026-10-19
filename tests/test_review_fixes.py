# -*- coding: utf-8 -*-
"""Regression tests for the findings of the adversarial review of 0.2."""
import warnings
import xml.etree.ElementTree as ET

import numpy as np
import pytest

CoolProp = pytest.importorskip("CoolProp")

from coolplot import PropertyDiagram  # noqa: E402
from coolplot.compose.layout import Frame, keep_out_points  # noqa: E402
from coolplot.engine.plan import nice_log  # noqa: E402
from coolplot.render.svg import SvgRenderer  # noqa: E402
from coolplot.render.ticks import ticks as _ticks  # noqa: E402
from coolplot.thermo import DiagramType, Fluid, compute_isoline, compute_quality_line, get_tp_limits, resolve_tp_box  # noqa: E402,E501
from coolplot.thermo.cycles import rankine, simple_compression, two_stage  # noqa: E402

BLEND = "HEOS::R32[0.7]&R125[0.3]"


def test_difficult_saturation_states_do_not_change_other_results():
    blend = Fluid(BLEND)
    box = resolve_tp_box(blend, get_tp_limits("ACHP"))
    ph = DiagramType.parse("ph")
    before = compute_isoline(blend, ph, "s", 1500.0, box, points=12, solver="flash")
    # A dew point CoolProp only finds with the phase envelope built
    blend.update("p", 26.6e5, "Q", 1.0)
    assert blend.get("p") == pytest.approx(26.6e5) and blend.get("Q") == pytest.approx(1.0)
    after = compute_isoline(blend, ph, "s", 1500.0, box, points=12, solver="flash")
    np.testing.assert_array_equal(np.isnan(before.x), np.isnan(after.x))
    ok = np.isfinite(before.x)
    assert after.x[ok] == pytest.approx(before.x[ok], rel=1e-9)


def test_predefined_blends_are_mixtures():
    fluid = Fluid("HEOS::R407C.mix")
    assert not fluid.is_pure and len(fluid.model_key[1]) == 3
    assert fluid.phase_envelope() is not None


def test_bubble_line_closes_at_the_neighbouring_dew_point():
    fluid = Fluid("HEOS::CO2[0.5]&Propane[0.5]")
    ph = DiagramType.parse("ph")
    bubble, dew = compute_quality_line(fluid, ph, 0.0), compute_quality_line(fluid, ph, 1.0)
    assert (bubble.x[0], bubble.y[0]) == (dew.x[-1], dew.y[-1])


def test_cycles_belong_to_the_diagram_fluid():
    diagram = PropertyDiagram("HEOS::R134a", "ph", tp_limits="ACHP")
    with pytest.raises(ValueError, match="computed for"):
        diagram.add_cycle(simple_compression("HEOS::R290", -10.0, 40.0))
    diagram.add_cycle(simple_compression("R134a", -10.0, 40.0))   # same fluid, other spelling
    with pytest.warns(UserWarning, match="previous fluid"):
        diagram.fluid = "HEOS::R290"


def test_models_reject_impossible_inputs():
    with pytest.raises(ValueError):
        simple_compression("R134a", 40.0, -10.0)
    with pytest.raises(ValueError):
        two_stage("R134a", 0.0, 0.0)
    with pytest.raises(ValueError, match="saturation"):
        rankine("Water", 50e5, 0.1e5, T_live_C=100.0)


def test_rounded_families_never_vanish():
    assert len(nice_log(1.1, 1.19, 5)) >= 1 and len(nice_log(31.0, 39.0, 3)) >= 1
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    diagram.set_isolines("rho", range=(31.0, 39.0), rounding=True)
    assert len(diagram.update_scene().group("iso/rho")) >= 1


def test_labels_survive_a_log_view_from_zero():
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    diagram.set_isolines("T", num=8, rounding=True, labels=True)
    diagram.set_view(None, (0.0, 10.0))
    scene = diagram.update_scene()
    assert scene.axes.y_limits == pytest.approx((0.01, 10.0))
    assert any(i.role == "isoline_label" for i in scene)
    with pytest.raises(ValueError):
        diagram.set_view((float("nan"), 300.0))


def test_switching_the_calculation_preset_keeps_the_rest():
    diagram = PropertyDiagram("R290", "ph", theme="dark", settings="print")
    diagram.settings = diagram.settings.with_(labels={"mode": "margin"})
    diagram.settings = diagram.settings.with_(calc="interactive")
    assert diagram.settings.calc.points == 60
    assert diagram.theme.name == "dark" and diagram.settings.labels.mode == "margin"
    assert diagram.settings.page.width_pt == 504.0


def test_svg_margin_labels_stay_on_the_canvas():
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    diagram.title = "Margin labels"
    diagram.settings = diagram.settings.with_(labels={"mode": "margin"})
    diagram.set_isolines("T", num=8, rounding=True, labels=True)
    renderer = diagram.draw(SvgRenderer())
    root = ET.fromstring(renderer.to_svg())
    ns = "{http://www.w3.org/2000/svg}"
    labels = [g for g in root.iter(ns + "g") if (g.get("class") or "").find("cp-role-isoline_label") >= 0]
    assert labels
    for group in labels:
        text = next(group.iter(ns + "text"))
        size_px = float(text.get("font-size"))
        # Vertical text reading upwards from its anchor: its far end
        assert float(text.get("y")) - 0.6 * size_px * len(text.text) >= 0.0
    # The title (its bottom edge at y) sits above the far ends of the labels
    title = next(t for t in root.iter(ns + "text") if t.get("class") == "cp-title")
    far_ends = [float(t.get("y")) - 0.6 * float(t.get("font-size")) * len(t.text)
                for g in labels for t in g.iter(ns + "text")]
    assert float(title.get("y")) <= min(far_ends)


def test_svg_ticks_on_a_narrow_log_range():
    assert len(_ticks(1.5, 1.9, True)) >= 2


def test_markers_are_kept_out_as_points():
    frame = Frame((0.0, 1.0), (0.0, 1.0), False, False, 100.0, 100.0)
    px, _ = keep_out_points(frame, [([0.1, 0.9], [0.1, 0.9], False)])
    assert len(px) == 2
    px, _ = keep_out_points(frame, [([0.1, 0.9], [0.1, 0.9])])
    assert len(px) > 2


def test_no_warnings_from_a_plain_chart():
    diagram = PropertyDiagram("R290", "Ts", tp_limits="ACHP")
    diagram.set_default_isolines(num=6, rounding=True, labels=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        diagram.draw(SvgRenderer())


class _FailingState:
    """Stands in for a working state that cannot solve any input."""
    def update(self, *args):
        raise ValueError("no solution")


def test_a_rescued_single_phase_state_is_returned_as_requested():
    import CoolProp
    if int(CoolProp.__version__.split(".")[0]) < 8:
        pytest.skip("CoolProp before 8 does not solve this state on the guide state either")
    blend = Fluid(BLEND)
    blend.update("p", 10e5, "Q", 0.0)
    T_bubble_K = blend.get("T")
    assert blend.critical["T"] > T_bubble_K   # computed now, before the working state is replaced
    blend._state = _FailingState()   # every state now comes from the guide state
    # Subcooled liquid below the critical temperature: the consistency check
    # looks up the saturation states at its temperature on the guide state
    state = blend.update_pair(CoolProp.PT_INPUTS, 10e5, T_bubble_K - 10.0)
    assert state.T() == pytest.approx(T_bubble_K - 10.0) and state.p() == pytest.approx(10e5)
    assert blend.get("T") == pytest.approx(T_bubble_K - 10.0)


def test_a_clone_builds_its_own_phase_envelope():
    blend = Fluid(BLEND)
    assert blend.phase_envelope() is not None
    twin = blend.clone()
    assert twin.phase_envelope() is not None and twin.phase_envelope() is not blend.phase_envelope()


def test_a_configuration_change_drops_the_cached_cycles():
    from coolplot.engine import Engine
    from coolplot.spec import FluidSpec
    engine = Engine()
    spec = FluidSpec.parse("HEOS::R290")
    fluid = engine.fluid(spec)
    engine._cycles[(spec, "states")] = "old"
    engine._cycles[(FluidSpec.parse("HEOS::Water"), "states")] = "other fluid"
    fluid.configuration_changed = lambda: True   # as after CoolProp.set_config_*
    assert engine.fluid(spec) is not fluid
    assert list(engine._cycles.values()) == ["other fluid"]
