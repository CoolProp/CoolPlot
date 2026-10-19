# -*- coding: utf-8 -*-
"""Planning isolines, computing them once, and composing the scene."""
import warnings

import numpy as np
import pytest

from coolplot.engine.plan import Domain, isoline_id, isoline_values_SI, nice_linear, nice_log, plan, snap
from coolplot.spec import DiagramSpec, IsolineSet

DOMAIN = Domain((200.0, 400.0, 1e5, 4e6),
                (("T", (200.0, 400.0)), ("p", (1e5, 4e6)), ("h", (1e5, 7e5)), ("s", (1e3, 3e3)),
                 ("rho", (1.0, 700.0)), ("Q", (0.0, 1.0))))


def test_nice_linear_steps():
    assert nice_linear(-73.15, 126.85, 11).tolist() == [-60.0, -40.0, -20.0, 0.0, 20.0, 40.0, 60.0, 80.0,
                                                        100.0, 120.0]
    assert nice_linear(0.0, 1.0, 11).tolist() == pytest.approx(np.linspace(0, 1, 11))
    values = nice_linear(1.03, 2.97, 5)
    assert np.allclose(np.diff(values), 0.5)


def test_nice_log_mantissas():
    assert nice_log(1.0, 40.0, 6).tolist() == [1.0, 2.0, 5.0, 10.0, 20.0]
    dense = nice_log(1.0, 40.0, 12)
    assert dense.tolist() == [1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0]
    assert nice_log(0.0, 10.0, 5).tolist() == nice_linear(0.0, 10.0, 5).tolist()   # no log of zero


def test_rounding_happens_in_display_units():
    spec = DiagramSpec("R290", units="EUR", isolines=(IsolineSet("T", num=11, rounding=True),))
    values_C = spec.units["T"].from_SI(isoline_values_SI(spec, spec.isolines[0], DOMAIN))
    assert np.allclose(values_C % 20.0, 0.0) or np.allclose(values_C % 10.0, 0.0)
    spec = DiagramSpec("R290", diagram="Ts", units="EUR", isolines=(IsolineSet("p", num=6, rounding=True),))
    values_bar = spec.units["p"].from_SI(isoline_values_SI(spec, spec.isolines[0], DOMAIN))
    assert values_bar.tolist() == pytest.approx([1.0, 2.0, 5.0, 10.0, 20.0])


def test_ids_are_snapped_and_unique():
    # -20 deg C converted to K carries rounding noise; it is the same line as 253.15 K
    assert isoline_id("T", -20.0 + 273.15) == isoline_id("T", 253.15) == "iso/T/253.15"
    spec = DiagramSpec("R290", isolines=(IsolineSet("T", values_SI=(253.15, -20.0 + 273.15, 300.0, 300.001)),))
    requests = plan(spec, DOMAIN)
    assert [r.item_id for r in requests] == ["iso/T/253.15", "iso/T/300", "iso/T/300.001"]
    assert snap(0.1 + 0.2) == 0.3


def test_plan_uses_settings_and_overrides():
    spec = DiagramSpec("R290", settings="interactive",
                       isolines=(IsolineSet("Q", num=3), IsolineSet("T", num=2, points=33, labels=True)))
    requests = plan(spec, DOMAIN)
    assert [(r.key, r.points) for r in requests] == [("Q", 100)] * 3 + [("T", 33)] * 2
    assert [r.labels for r in requests] == [False] * 3 + [True] * 2
    unsorted = DiagramSpec("R290", isolines=(IsolineSet("Q", values_SI=(1.0, 0.0, 1.5)),))
    assert [r.value_SI for r in plan(unsorted, DOMAIN)] == [0.0, 1.0]


# ---------------------------------------------------------------------------
# With CoolProp
# ---------------------------------------------------------------------------
@pytest.fixture
def diagram():
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    d.set_isolines("Q", num=3)
    d.set_isolines("T", values=[0.0, 20.0], points=40, labels=True)
    return d


def test_calc_settings_recompute_only_what_they_affect(diagram):
    diagram.update_scene()
    misses = diagram.cache.misses
    diagram.settings = diagram.settings.with_(labels={"digits": 2}, page={"font_scale": 1.2})
    diagram.update_scene()
    assert diagram.cache.misses == misses
    diagram.settings = diagram.settings.with_(calc={"saturation_points": 60})
    diagram.update_scene()
    assert diagram.cache.misses == misses + 3   # the quality lines only


def test_font_scale_reaches_every_text(diagram):
    base = diagram.update_scene()
    label_pt = base["iso/T/273.15/label"].style.font.size_pt
    tick_pt = base.axes.style.tick_label.font.size_pt
    diagram.settings = diagram.settings.with_(page={"font_scale": 2.0})
    scene = diagram.update_scene()
    assert scene["iso/T/273.15/label"].style.font.size_pt == pytest.approx(2.0 * label_pt)
    assert scene.axes.style.tick_label.font.size_pt == pytest.approx(2.0 * tick_pt)


def test_label_settings_change_texts(diagram):
    assert diagram.update_scene()["iso/T/293.15/label"].text == "T=20 deg C"
    diagram.settings = diagram.settings.with_(labels={"show_units": False})
    assert diagram.update_scene()["iso/T/293.15/label"].text == "T=20"


def test_state_snapshot_is_independent_of_the_users_state():
    CoolProp = pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram
    state = CoolProp.AbstractState("HEOS", "R32&R125")
    state.set_mole_fractions([0.7, 0.3])
    state.set_binary_interaction_double(0, 1, "betaT", 1.01)
    d = PropertyDiagram(state, "ph", tp_limits="ACHP")
    assert d.spec.fluid.fractions == (0.7, 0.3)
    assert (0, 1, "betaT", 1.01) in d.spec.fluid.interactions
    state.set_mole_fractions([0.2, 0.8])   # must not leak into the diagram
    assert d.fluid.state.get_mole_fractions() == pytest.approx([0.7, 0.3])
    assert d.fluid.state.get_binary_interaction_double(0, 1, "betaT") == pytest.approx(1.01)


def test_incompressible_fraction_is_applied():
    pytest.importorskip("CoolProp")
    from CoolProp.CoolProp import PropsSI
    from coolplot.thermo import Fluid
    fluid = Fluid("INCOMP::MEG[0.3]")
    fluid.update("T", 300.0, "p", 1e5)
    assert fluid.get("rho") == pytest.approx(PropsSI("D", "T", 300.0, "P", 1e5, "INCOMP::MEG[0.3]"))
    assert fluid.get("rho") != pytest.approx(PropsSI("D", "T", 300.0, "P", 1e5, "INCOMP::MEG[0.1]"))


def test_failing_curves_warn_once(diagram):
    from coolplot.engine.plan import CurveRequest
    from coolplot.thermo import Curve
    engine, spec = diagram.engine, diagram.spec
    domain = engine.domain(spec)
    bad = CurveRequest("iso/T/1", "T", 1.0, 10)
    engine.cache.get_or_compute(engine.cache_key(spec, domain, bad), lambda: Curve([np.nan] * 10, [np.nan] * 10, 10))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert engine.curves(spec, domain, [bad]) == []
        assert engine.curves(spec, domain, [bad]) == []
    assert len(caught) == 1 and "Skipping" in str(caught[0].message)


def test_changing_the_diagram_type_keeps_what_fits(diagram):
    diagram.set_isolines("s", num=3)
    diagram.diagram_type = "Ts"
    assert [s.key for s in diagram.spec.isolines] == ["Q"]   # T and s are axes now
    diagram.update_scene()


def test_two_diagrams_share_an_engine():
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram
    ph = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    ts = PropertyDiagram("R290", "Ts", tp_limits="ACHP", engine=ph.engine)
    assert ts.fluid is ph.fluid
    ph.set_isolines("Q", num=2)
    ts.set_isolines("Q", num=2)
    ph.update_scene()
    ts.update_scene()
    assert ph.cache.misses == 4   # same values, different axes


# ---------------------------------------------------------------------------
# 0.3.1: CoolProp's global state and the cache
# ---------------------------------------------------------------------------
def test_a_changed_reference_state_never_serves_old_curves():
    from CoolProp.CoolProp import set_reference_state
    from coolplot import PropertyDiagram

    def first_h(diagram):
        line = [i for i in diagram.update_scene((400.0, 300.0)) if i.id.startswith("iso/T")][0]
        return line.x[0]

    first = PropertyDiagram("R134a", "ph")
    first.set_isolines("T", values=[20.0])
    h_default = first_h(first)
    try:
        set_reference_state("R134a", "NBP")
        second = PropertyDiagram("R134a", "ph", cache=first.cache)   # shares the cache
        second.set_isolines("T", values=[20.0])
        assert first_h(second) != pytest.approx(h_default)            # not the stale curve
        assert first_h(first) == pytest.approx(h_default)             # the old engine still has old states
        first.refresh()
        assert first_h(first) == pytest.approx(first_h(second))
    finally:
        set_reference_state("R134a", "DEF")


def test_a_changed_configuration_rebuilds_the_fluid():
    import CoolProp.CoolProp as CP
    from coolplot.engine import Engine
    from coolplot.spec import FluidSpec
    engine = Engine()
    spec = FluidSpec.parse("R134a")
    before = engine.fluid(spec)
    assert engine.fluid(spec) is before
    # Through the JSON string, which every CoolProp version offers the same way
    import json
    config = json.loads(CP.get_config_as_json_string())
    changed = dict(config, NORMALIZE_GAS_CONSTANTS=not config["NORMALIZE_GAS_CONSTANTS"])
    try:
        CP.set_config_as_json_string(json.dumps(changed))
        assert engine.fluid(spec) is not before
    finally:
        CP.set_config_as_json_string(json.dumps(config))


def test_a_curve_that_cannot_be_computed_names_its_reason():
    from coolplot.thermo.isolines import Curve
    import pickle
    curve = Curve([], [], reason="needs CoolProp 8")
    assert pickle.loads(pickle.dumps(curve)).reason == "needs CoolProp 8"
