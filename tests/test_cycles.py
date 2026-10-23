# -*- coding: utf-8 -*-
"""Cycles: models, state resolution, paths and drawing them on a diagram."""
import json
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("CoolProp")
import CoolProp  # noqa: E402
from CoolProp.CoolProp import PropsSI  # noqa: E402

from coolplot import PropertyDiagram  # noqa: E402
from coolplot.core.cycle import Cycle, StateInput  # noqa: E402
from coolplot.render.svg import SvgRenderer  # noqa: E402
from coolplot.scene import Line, Markers, Text  # noqa: E402
from coolplot.spec import CycleSpec, DiagramSpec, FluidSpec  # noqa: E402
from coolplot.thermo import Fluid, state_point  # noqa: E402
from coolplot.thermo.cycles import (auto_kind, path_states, rankine, resolve_states,  # noqa: E402
                                    simple_compression, two_stage)


@pytest.fixture(scope="module")
def r290():
    return Fluid("HEOS::R290")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def test_simple_compression(r290):
    c = simple_compression(r290, T_evap_C=-5.0, T_cond_C=45.0, dT_sh_K=5.0, dT_sc_K=2.0, eta_is=0.7)
    s1, s2, s3, s4 = (c.state(n) for n in (1, 2, 3, 4))
    assert c.result["p_evap_Pa"] == pytest.approx(PropsSI("P", "T", 268.15, "Q", 1, "R290"))
    assert s1.T == pytest.approx(268.15 + 5.0, abs=1e-6) and s4.h == pytest.approx(s3.h)
    assert s3.T == pytest.approx(PropsSI("T", "P", s3.p, "Q", 0, "R290") - 2.0, abs=1e-6)
    h2s = PropsSI("H", "P", s2.p, "S", s1.s, "R290")
    assert (h2s - s1.h) / (s2.h - s1.h) == pytest.approx(0.7)
    assert c.result["COP_heating"] == pytest.approx(c.result["COP_cooling"] + 1.0)
    assert c.loops == ((1, 2, 3, 4, 1),)


def test_two_stage_flash_tank_balances(r290):
    c = two_stage(r290, -30.0, 45.0, "flash_tank")
    s = {n: c.state(n) for n in range(1, 9)}
    r = c.result["m_dot_ratio"]
    # Flash tank: what goes in comes out (per kg through the evaporator)
    assert s[2].h + r * s[6].h == pytest.approx(r * s[3].h + s[7].h)
    assert c.result["p_mid_Pa"] == pytest.approx(np.sqrt(c.result["p_evap_Pa"] * c.result["p_cond_Pa"]))
    assert c.result["COP_heating"] == pytest.approx(c.result["COP_cooling"] + 1.0)
    # Better than one stage over the same lift
    single = simple_compression(r290, -30.0, 45.0)
    assert c.result["COP_cooling"] > single.result["COP_cooling"]


def test_two_stage_economizer_balances(r290):
    c = two_stage(r290, -30.0, 45.0, "economizer")
    s = {n: c.state(n) for n in range(1, 10)}
    r = c.result["m_dot_ratio"]
    assert r * (s[9].h - s[8].h) == pytest.approx(s[5].h - s[6].h)
    assert (1.0 + r) * s[3].h == pytest.approx(s[2].h + r * s[9].h)
    assert c.loops == ((1, 2, 3, 4, 5, 6, 7, 1), (5, 8, 9, 3))
    with pytest.raises(ValueError):
        two_stage(r290, -30.0, 45.0, "cascade")


def test_rankine():
    c = rankine("Water", 40e5, 0.1e5, 400.0, eta_is_turbine=1.0, eta_is_pump=1.0)
    assert c.state(4).s == pytest.approx(c.state(3).s) and c.state(2).s == pytest.approx(c.state(1).s)
    assert 0.3 < c.result["eta_th"] < 0.4
    real = rankine("Water", 40e5, 0.1e5, 400.0)
    assert real.result["eta_th"] < c.result["eta_th"]


# ---------------------------------------------------------------------------
# States and paths
# ---------------------------------------------------------------------------
def test_resolve_states_with_via(r290):
    inputs = {1: StateInput((("p", 3e5), ("T", 273.15))),
              2: StateInput((("p", 15e5),), "compression", 0.7),
              3: StateInput((("p", 15e5), ("Q", 0.0))),
              4: StateInput((("p", 3e5),), "isenthalpic")}
    states = resolve_states(r290, inputs, [(1, 2, 3, 4, 1)])
    assert states[4].h == pytest.approx(states[3].h) and states[4].p == pytest.approx(3e5)
    reference = simple_compression(r290, -5.0, 45.0)   # same construction, other numbers
    assert reference.state(4).h == pytest.approx(reference.state(3).h)
    with pytest.raises(ValueError, match="no chain"):
        resolve_states(r290, {1: StateInput((("p", 3e5),), "isenthalpic")}, [])
    with pytest.raises(ValueError, match="depend on each other"):
        resolve_states(r290, {1: StateInput((("p", 3e5),), "isenthalpic"),
                              2: StateInput((("p", 2e5),), "isenthalpic")}, [(1, 2, 1)])
    with pytest.raises(ValueError):
        StateInput((("p", 3e5), ("T", 300.0)), "isenthalpic")   # two properties and a via
    with pytest.raises(ValueError):
        StateInput((("T", 300.0),), "compression")              # needs the outlet pressure


def test_isobaric_path_bends_on_the_dome(r290):
    a = state_point(r290, "p", 15e5, "T", 340.0)
    b = state_point(r290, "p", 15e5, "Q", 0.0)
    assert auto_kind(a, b) == "isobaric"
    path = path_states(r290, a, b, steps=10)
    assert path[0] == a and path[-1] == b
    h_dew = PropsSI("H", "P", 15e5, "Q", 1, "R290")
    assert np.min(np.abs([s.h - h_dew for s in path])) < 1e-6 * h_dew
    assert all(s.p == pytest.approx(15e5) for s in path)
    assert np.all(np.diff([s.h for s in path]) < 0.0)


def test_auto_kinds(r290):
    a = state_point(r290, "p", 3e5, "T", 273.15)
    assert auto_kind(a, state_point(r290, "p", 10e5, "s", a.s)) == "isentropic"
    assert auto_kind(a, state_point(r290, "p", 2e5, "h", a.h)) == "isenthalpic"
    assert auto_kind(a, state_point(r290, "p", 10e5, "T", 350.0)) == "polytropic"
    assert len(path_states(r290, a, state_point(r290, "p", 10e5, "T", 350.0), "straight")) == 2


# ---------------------------------------------------------------------------
# On the diagram
# ---------------------------------------------------------------------------
@pytest.fixture
def diagram():
    d = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    d.set_lines("Q", num=3)
    d.set_lines("T", values=[-20.0, 0.0, 20.0, 40.0], points=60, labels=True)
    return d


HEAT_PUMP = [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
             {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}]


def test_add_cycle_from_dicts(diagram):
    diagram.add_cycle("Heat pump", HEAT_PUMP)
    scene = diagram.update_scene()
    line, markers = scene["cycle/Heat pump/loop/0"], scene["cycle/Heat pump/states"]
    assert isinstance(line, Line) and isinstance(markers, Markers)
    assert line.legend == "Heat pump" and len(markers.x) == 4
    numbers = [scene["cycle/Heat pump/number/{0}".format(n)] for n in (1, 2, 3, 4)]
    assert all(isinstance(t, Text) and t.text == str(n) for n, t in zip((1, 2, 3, 4), numbers))
    # Values were given in bar and deg C
    states = diagram.cycle_states("Heat pump")
    assert states[1].p == pytest.approx(3e5) and states[1].T == pytest.approx(273.15)
    assert markers.y[0] == pytest.approx(3.0)
    # The condenser follows its isobar through the dome: many points at 15 bar
    assert np.sum(np.isclose(line.y, 15.0)) > 10


def test_add_cycle_from_arrays_and_models(diagram):
    diagram.add_cycle("measured", p=[3.0, 15.0, 15.0, 3.0], h=[580.0, 650.0, 320.0, 320.0], numbers=False)
    scene = diagram.update_scene()
    assert "cycle/measured/number/1" not in scene
    assert scene["cycle/measured/states"].x.tolist() == pytest.approx([580.0, 650.0, 320.0, 320.0])
    name = diagram.add_cycle(two_stage(diagram.fluid, -30.0, 45.0, "flash_tank"),
                             loops=[[1, 2, 7, 8, 1], [3, 4, 5, 6, 3]])
    scene = diagram.update_scene()
    assert name == "Two-stage, flash tank"
    assert {i.id for i in scene.group("cycle/" + name)} >= {"cycle/{0}/loop/0".format(name),
                                                            "cycle/{0}/loop/1".format(name)}
    # Each state is drawn and numbered once although two chains share none
    assert len(scene["cycle/{0}/states".format(name)].x) == 8


def test_moving_a_state_redraws_only_the_cycle(diagram):
    diagram.add_cycle("Heat pump", HEAT_PUMP)
    renderer = SvgRenderer()
    renderer.sync(diagram.update_scene())
    misses = diagram.cache.misses
    moved = [dict(s) for s in HEAT_PUMP]
    moved[1] = {"p": 16.0, "via": "compression", "eta_is": 0.7}
    moved[2] = {"p": 16.0, "Q": 0.0}
    diagram.add_cycle("Heat pump", moved)
    report = renderer.sync(diagram.update_scene())
    assert diagram.cache.misses == misses   # no isoline recalculated
    assert not report.axes_changed
    assert all(i.startswith("cycle/Heat pump/") or i.endswith("/label") for i in report.updated)
    assert "cycle/Heat pump/loop/0" in report.updated


def test_cycles_keep_labels_away(diagram):
    diagram.add_cycle("Heat pump", HEAT_PUMP)
    scene = diagram.update_scene()
    states = diagram.cycle_states("Heat pump")
    for label in (i for i in scene if i.role == "isoline_label"):
        # No isoline label sits right on a state of the cycle
        assert min(abs(label.x - s.h / 1e3) + abs(np.log10(label.y) - np.log10(s.p / 1e5))
                   for s in states.values()) > 1e-3


def test_view_includes_the_cycle():
    d = PropertyDiagram("Water", "Ts", tp_limits="ORC")
    d.add_cycle(rankine("Water", 40e5, 0.1e5, 400.0))
    axes = d.update_scene().axes
    assert axes.y_limits[1] > 400.0   # live steam at the limit of the region stays inside the frame


def test_bad_cycles_fail_early(diagram):
    with pytest.raises(ValueError):
        diagram.add_cycle("bad", HEAT_PUMP, loops=[[1, 2, 9, 1]])
    with pytest.raises(ValueError):
        diagram.add_cycle("bad", [{"p": 3.0}, {"p": 15.0, "T": 50.0}])
    with pytest.raises(ValueError, match="State 2"):
        diagram.add_cycle("bad", [{"p": 3.0, "T": 0.0}, {"p": 1e9, "T": 50.0}])
    assert diagram.spec.cycles == ()


def test_cycles_round_trip_through_json(diagram):
    diagram.add_cycle("Heat pump", HEAT_PUMP, paths={(1, 2): "straight"})
    diagram.add_cycle(simple_compression(diagram.fluid, -10.0, 35.0, name="model"))
    data = json.loads(json.dumps(diagram.spec.to_dict()))
    again = DiagramSpec.from_dict(data)
    assert again == diagram.spec
    assert isinstance(again.cycles[0], CycleSpec) and again.cycles[0].paths == (((1, 2), "straight"),)


def test_state_labels_follow_the_numbers_or_stand_alone(diagram):
    diagram.add_cycle("Heat pump", HEAT_PUMP, labels={2: "discharge", 4: "after the valve"})
    scene = diagram.update_scene()
    texts = {n: scene["cycle/Heat pump/number/{0}".format(n)].text for n in (1, 2, 3, 4)}
    assert texts == {1: "1", 2: "2: discharge", 3: "3", 4: "4: after the valve"}
    # Without numbers only the labelled states get a text
    diagram.add_cycle("Heat pump", HEAT_PUMP, numbers=False, labels={2: "discharge"})
    scene = diagram.update_scene()
    assert [t.text for t in scene.group("cycle/Heat pump/numbers")] == ["discharge"]
    # Labels survive moving a state and a round trip through JSON
    diagram.move_cycle_state("Heat pump", 3, 300.0, 15.0)
    assert dict(diagram.spec.cycles[0].labels) == {2: "discharge"}
    data = json.loads(json.dumps(diagram.spec.to_dict()))
    assert data["cycles"][0]["labels"] == [[2, "discharge"]]
    assert DiagramSpec.from_dict(data) == diagram.spec


def test_a_cycle_without_labels_keeps_its_old_record(diagram):
    diagram.add_cycle("Heat pump", HEAT_PUMP)
    assert "labels" not in diagram.spec.to_dict()["cycles"][0]


@pytest.mark.parametrize("labels, match", [({5: "x"}, "no state 5"), ({2: ""}, "non-empty"), ({2: 3}, "non-empty"),
                                           ({2.5: "x"}, "state numbers"), ({True: "x"}, "state numbers"),
                                           ([(2, "a"), (2, "b")], "labelled twice"), (0, "labels are"),
                                           (False, "labels are"), ("2: x", "labels are"), ([(2,)], "pair"),
                                           ({2: "\ud800"}, "not valid text")])
def test_bad_state_labels_are_refused(diagram, labels, match):
    with pytest.raises(ValueError, match=match):
        diagram.add_cycle("Heat pump", HEAT_PUMP, labels=labels)
    assert diagram.spec.cycles == ()


def test_cycle_object_defaults():
    s = StateInput((("p", 1e5), ("T", 300.0)))
    with pytest.raises(ValueError):
        Cycle("x", {1: None}, loops=[[1, 2]])
    spec = CycleSpec("c", {2: s, 1: s, 3: s})
    assert spec.loops == ((1, 2, 3, 1),)


# Regression tests from the adversarial review of 0.2 ------------------------

def test_cycles_belong_to_the_diagram_fluid():
    diagram = PropertyDiagram("HEOS::R134a", "ph", tp_limits="ACHP")
    with pytest.raises(ValueError, match="computed for"):
        diagram.add_cycle(simple_compression("HEOS::R290", -10.0, 40.0))
    diagram.add_cycle(simple_compression("R134a", -10.0, 40.0))   # same fluid, other spelling
    with pytest.warns(UserWarning, match="previous fluid"):
        diagram.fluid = "HEOS::R290"


# The fluid of a cycle and of its chart ------------------------------------------
# A cycle keeps its fluid's model (Cycle.fluid_model). Before 1.4 it kept only
# the name, which loses the basis of the fractions ("HEOS::R32[0.5]&R125[0.5]"
# given by mass reads by mole), interaction parameters set on a mixture and the
# fractions of an AbstractState; the chart then refused the cycle of its own
# fluid, or took a cycle of another one.

R32_R125_BY_MASS = FluidSpec(backend="HEOS", components=("R32", "R125"), fractions=(0.5, 0.5), basis="mass")
R32_R125_TUNED = FluidSpec(backend="HEOS", components=("R32", "R125"), fractions=(0.5, 0.5), basis="mass",
                           interactions=((0, 1, "betaT", 1.001),))
R515B_BY_MASS = FluidSpec(backend="HEOS", components=("R1234ze(E)", "R227EA"), fractions=(0.911, 0.089), basis="mass")


def _accepts(chart_fluid, cycle) -> bool:
    try:
        PropertyDiagram(chart_fluid, "ph").add_cycle(cycle)
    except ValueError as e:
        assert "computed for" in str(e)
        return False
    return True


def test_the_models_keep_the_model_of_their_fluid():
    for cycle, fluid in ((simple_compression(R32_R125_BY_MASS, -5.0, 35.0), R32_R125_BY_MASS),
                         (two_stage(R32_R125_BY_MASS, -30.0, 35.0), R32_R125_BY_MASS),
                         (rankine(R515B_BY_MASS, 2.0e6, 0.5e6), R515B_BY_MASS)):
        assert cycle.fluid_model == Fluid(fluid).model_key
        assert cycle.fluid_model[3] == "mass"


def test_a_cycle_of_a_mixture_by_mass_draws_on_its_chart():
    assert _accepts(R32_R125_BY_MASS, simple_compression(R32_R125_BY_MASS, -5.0, 35.0))
    assert _accepts(R515B_BY_MASS, rankine(R515B_BY_MASS, 2.0e6, 0.5e6))
    # The states are those of the mixture by mass: the evaporator outlet of R515B
    # against CoolProp, saturated at -5 deg C and superheated by 5 K
    state = Fluid(R515B_BY_MASS).state
    state.update(CoolProp.QT_INPUTS, 1.0, 268.15)
    state.update(CoolProp.PT_INPUTS, state.p(), 273.15)
    outlet = simple_compression(R515B_BY_MASS, -5.0, 45.0).state(1)
    assert outlet.h == pytest.approx(state.hmass(), rel=1e-9)


def test_interaction_parameters_tell_two_models_apart():
    tuned = simple_compression(R32_R125_TUNED, -5.0, 35.0)
    assert _accepts(R32_R125_TUNED, tuned)
    assert not _accepts(R32_R125_BY_MASS, tuned)
    assert not _accepts(R32_R125_TUNED, simple_compression(R32_R125_BY_MASS, -5.0, 35.0))
    # Both print as "HEOS::R32[0.5]&R125[0.5]": the message says what differs
    with pytest.raises(ValueError, match="another model of .* interaction parameters"):
        PropertyDiagram(R32_R125_BY_MASS, "ph").add_cycle(tuned)


def test_a_cycle_of_an_abstract_state_mixture_draws_on_its_chart():
    state = CoolProp.AbstractState("HEOS", "R32&R125")
    state.set_mole_fractions([0.6, 0.4])
    assert _accepts(state, simple_compression(state, -5.0, 35.0))


def test_the_same_mixture_by_mass_by_mole_or_as_a_blend_is_one_fluid():
    by_mass = Fluid(R32_R125_BY_MASS)
    blend = Fluid("R410A.mix")   # R32/R125 50/50 by mass
    mole = by_mass.state.get_mole_fractions()
    by_mole = Fluid("HEOS::R32[{0!r}]&R125[{1!r}]".format(*mole))
    assert by_mass.same_fluid(blend) and blend.same_fluid(by_mass)
    assert by_mass.same_fluid(by_mole) and by_mole.same_fluid(blend)
    assert Fluid("R290").same_fluid(Fluid("HEOS::Propane"))
    assert _accepts("R410A.mix", simple_compression(R32_R125_BY_MASS, -5.0, 35.0))
    assert _accepts(R32_R125_BY_MASS, simple_compression("R410A.mix", -5.0, 35.0))


def test_other_fluids_are_told_apart():
    by_mass = Fluid(R32_R125_BY_MASS)
    mole = by_mass.state.get_mole_fractions()
    nudged = Fluid("HEOS::R32[{0!r}]&R125[{1!r}]".format(mole[0] + 1e-6, mole[1] - 1e-6))
    assert not by_mass.same_fluid(nudged)                                # 1e-6 in a mole fraction
    assert not by_mass.same_fluid(Fluid("HEOS::R32[0.5]&R125[0.5]"))     # 50/50 by mole
    assert not by_mass.same_fluid(Fluid(R32_R125_TUNED))                 # interaction parameters
    assert not Fluid("R32").same_fluid(Fluid("R125"))
    assert not Fluid("INCOMP::MEG[0.3]").same_fluid(Fluid("INCOMP::MEG[0.4]"))
    assert Fluid("INCOMP::MEG[0.3]").same_fluid(Fluid("INCOMP::MEG[0.3]"))
    # A cycle that has only a name is checked by its name, as before 1.4
    named = Cycle("by name", simple_compression("HEOS::R290", -5.0, 35.0).states, fluid="HEOS::R290")
    assert _accepts("R290", named) and not _accepts("R32", named)


def test_the_tolerances_and_the_backend_are_kept():
    # Mole fractions to 1e-9: a difference of 1e-8 is another mixture, 1e-11 the same
    mole = Fluid(R32_R125_BY_MASS).state.get_mole_fractions()
    def nudged(delta):
        return Fluid("HEOS::R32[{0!r}]&R125[{1!r}]".format(mole[0] + delta, mole[1] - delta))
    assert not Fluid(R32_R125_BY_MASS).same_fluid(nudged(1e-8))
    assert Fluid(R32_R125_BY_MASS).same_fluid(nudged(1e-11))
    # Interaction parameters to 1e-12 relative: 1e-10 apart is another model
    near = FluidSpec(backend="HEOS", components=("R32", "R125"), fractions=(0.5, 0.5), basis="mass",
                     interactions=((0, 1, "betaT", 1.001 + 1e-10),))
    assert not Fluid(R32_R125_TUNED).same_fluid(Fluid(near))
    # Another backend is another fluid, even of the same substance
    assert not Fluid("HEOS::R290").same_fluid(Fluid("TTSE&HEOS::R290"))


def test_the_basis_is_named_only_for_mixtures_by_mass():
    from coolplot.chart import _fluid_text
    assert _fluid_text("HEOS::R32[0.5]&R125[0.5]", Fluid(R32_R125_BY_MASS).model_key).endswith("(fractions by mass)")
    pure_by_mass = FluidSpec(backend="HEOS", components=("R290",), basis="mass")
    assert _fluid_text("HEOS::R290", Fluid(pure_by_mass).model_key) == "HEOS::R290"
    assert _fluid_text("INCOMP::MEG[0.3]", Fluid("INCOMP::MEG[0.3]").model_key) == "INCOMP::MEG[0.3]"
    with pytest.raises(ValueError, match=r"computed for HEOS::R32, but this chart shows HEOS::R290\."):
        PropertyDiagram("HEOS::R290", "ph").add_cycle(simple_compression("HEOS::R32", -5.0, 35.0))


def test_a_cycle_keeps_a_hashable_model_and_is_checked_by_it_alone():
    model = Fluid(R32_R125_BY_MASS).model_key
    listed = Cycle("listed", simple_compression(R32_R125_BY_MASS, -5.0, 35.0).states,
                   fluid_model=[list(part) if isinstance(part, tuple) else part for part in model])
    assert listed.fluid_model == model and hash(listed) == hash(replace(listed))
    # A cycle with a model but no name is checked too
    assert _accepts(R32_R125_BY_MASS, listed) and not _accepts("R290", listed)


def test_a_cycle_of_another_mixture_names_the_basis():
    diagram = PropertyDiagram("HEOS::R32[0.5]&R125[0.5]", "ph")   # 50/50 by mole
    with pytest.raises(ValueError, match=r"computed for HEOS::R32\[0\.5\]&R125\[0\.5\] \(fractions by mass\), "
                                         r"but this chart shows HEOS::R32\[0\.5\]&R125\[0\.5\]\."):
        diagram.add_cycle(simple_compression(R32_R125_BY_MASS, -5.0, 35.0))


def test_models_reject_impossible_inputs():
    with pytest.raises(ValueError):
        simple_compression("R134a", 40.0, -10.0)
    with pytest.raises(ValueError):
        two_stage("R134a", 0.0, 0.0)
    with pytest.raises(ValueError, match="saturation"):
        rankine("Water", 50e5, 0.1e5, T_live_C=100.0)
