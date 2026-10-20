# -*- coding: utf-8 -*-
"""Cycles: models, state resolution, paths and drawing them on a diagram."""
import json

import numpy as np
import pytest

pytest.importorskip("CoolProp")
from CoolProp.CoolProp import PropsSI  # noqa: E402

from coolplot import PropertyDiagram  # noqa: E402
from coolplot.core.cycle import Cycle, StateInput  # noqa: E402
from coolplot.render.svg import SvgRenderer  # noqa: E402
from coolplot.scene import Line, Markers, Text  # noqa: E402
from coolplot.spec import CycleSpec, DiagramSpec  # noqa: E402
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


def test_cycle_object_defaults():
    s = StateInput((("p", 1e5), ("T", 300.0)))
    with pytest.raises(ValueError):
        Cycle("x", {1: None}, loops=[[1, 2]])
    spec = CycleSpec("c", {2: s, 1: s, 3: s})
    assert spec.loops == ((1, 2, 3, 1),)
