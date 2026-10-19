# -*- coding: utf-8 -*-
"""Property calculations, checked against CoolProp directly."""
import numpy as np
import pytest

CoolProp = pytest.importorskip("CoolProp")
from CoolProp.CoolProp import PropsSI  # noqa: E402

from coolplot.thermo import (DiagramType, Fluid, Relative, TpLimits, compute_isoline,  # noqa: E402
                             compute_quality_line, get_tp_limits, process_path, resolve_tp_box,
                             state_point)


@pytest.fixture(scope="module")
def r290():
    return Fluid("HEOS::R290")


def test_diagram_type_parsing():
    ph = DiagramType.parse("ph")
    assert (ph.y, ph.x) == ("p", "h")
    assert ph.y_log and not ph.x_log
    assert DiagramType.parse("TS") == DiagramType.parse("Ts") == DiagramType("T", "s")
    assert DiagramType.parse("prho") == DiagramType.parse("PD")
    with pytest.raises(ValueError):
        DiagramType.parse("xy")


def test_isolines_offered_per_diagram():
    ph = DiagramType.parse("ph")
    assert not ph.supports("p") and not ph.supports("h")  # straight lines
    assert set(ph.supported_isolines()) >= {"T", "s", "rho", "Q"}
    assert ph.sweep_quantity("T") == "p"
    assert DiagramType.parse("Ts").sweep_quantity("h") == "p"


def test_fluid_constants(r290):
    assert r290.critical["T"] == pytest.approx(PropsSI("Tcrit", "R290"), rel=1e-9)
    # CoolProp 6.8 reports p_critical from the equation of state, which
    # differs from the tabulated value of PropsSI by about 8 ppm for R290.
    assert r290.critical["p"] == pytest.approx(PropsSI("pcrit", "R290"), rel=1e-4)
    T_lo_K, T_hi_K = r290.saturation_range("T")
    assert T_lo_K > PropsSI("Ttriple", "R290") and T_hi_K < r290.critical["T"]
    twin = r290.clone()
    assert twin.state is not r290.state and twin.model_key == r290.model_key


def test_tp_limits(r290):
    T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa = resolve_tp_box(r290, get_tp_limits("ACHP"))
    assert (T_lo_K, T_hi_K, p_lo_Pa) == (173.15, 493.15, 0.25e5)
    assert p_hi_Pa == pytest.approx(2.25 * r290.critical["p"], rel=1e-6)
    custom = resolve_tp_box(r290, TpLimits(250.0, Relative(1.1), 1e5, 5e6))
    assert custom[1] == pytest.approx(1.1 * r290.critical["T"], rel=1e-6)
    with pytest.raises(ValueError):
        resolve_tp_box(r290, TpLimits(400.0, 300.0))


def test_isotherm_matches_propssi(r290):
    ph = DiagramType.parse("ph")
    box = resolve_tp_box(r290, get_tp_limits("ACHP"))
    curve = compute_isoline(r290, ph, "T", 300.0, box, points=40)
    assert curve.n_failed == 0
    # Every point is a state at 300 K with the computed (p, h)
    for h, p in zip(curve.x[::7], curve.y[::7]):
        assert PropsSI("T", "P", p, "H", h, "R290") == pytest.approx(300.0, abs=1e-6)


def test_isentrope_in_ts_is_vertical_free(r290):
    # Constant enthalpy in a Ts chart, which older versions computed with
    # the slow (h, s) input pair
    ts = DiagramType.parse("Ts")
    box = resolve_tp_box(r290, get_tp_limits("ACHP"))
    curve = compute_isoline(r290, ts, "h", 6e5, box, points=30)
    assert curve.n_valid >= 25
    ok = np.isfinite(curve.x)
    T_K, s = curve.y[ok][3], curve.x[ok][3]
    assert PropsSI("H", "T", T_K, "S", s, "R290") == pytest.approx(6e5, rel=1e-6)


def test_saturation_dome_closes_at_critical_point(r290):
    ph = DiagramType.parse("ph")
    bubble = compute_quality_line(r290, ph, 0.0, points=50)
    dew = compute_quality_line(r290, ph, 1.0, points=50)
    assert bubble.n_failed == 0 and dew.n_failed == 0
    assert bubble.x[-1] == dew.x[-1] == pytest.approx(r290.critical["h"])
    assert bubble.y[-1] == pytest.approx(r290.critical["p"])
    assert bubble.x[0] < dew.x[0]
    with pytest.raises(ValueError):
        compute_quality_line(r290, ph, 1.5)


def test_process_path(r290):
    start = state_point(r290, "p", 3e5, "T", 270.0)
    end = state_point(r290, "p", 15e5, "s", start.s)
    path = process_path(r290, start, end, along=("p", "s"), steps=5)
    assert len(path) == 5
    assert path[0].T == pytest.approx(start.T)
    assert path[-1].p == pytest.approx(15e5)
    assert all(p.s == pytest.approx(start.s) for p in path)
    assert path[2]["P"] == path[2].p  # alias access


# ---------------------------------------------------------------------------
# 0.3.1: states CoolProp gets wrong, limits of mixtures, incompressibles
# ---------------------------------------------------------------------------
def _needs_coolprop_8():
    from coolplot.thermo.tracer import TRACER_AVAILABLE
    if not TRACER_AVAILABLE:
        pytest.skip("CoolProp 6 and 7 cannot flash rho,T for mixtures at all")


def test_inconsistent_mixture_states_are_refused():
    _needs_coolprop_8()
    # CoolProp 8 answers (rho = 100 kg/m3, T = 264.16 K) of R407C, a two-phase
    # state, with a "gas" whose pressure belongs to another density
    from coolplot.thermo.fluid import Fluid
    fluid = Fluid("HEOS::R407C.mix")
    fluid.update("rho", 100.0, "T", 250.0)
    assert 0.0 <= fluid.get("Q") <= 1.0           # a proper two-phase answer passes
    with pytest.raises(ValueError, match="inconsistent state"):
        fluid.update("rho", 100.0, "T", 264.16)
    # Pure fluids are not checked and single-phase mixture states pass
    Fluid("R134a").update("rho", 100.0, "T", 300.0)
    fluid.update("p", 5e5, "T", 320.0)
    assert fluid.get("Q") < 0.0


def test_flash_isochore_of_a_blend_round_trips():
    _needs_coolprop_8()
    import CoolProp
    from CoolProp.CoolProp import AbstractState
    from coolplot.core.diagram_type import DiagramType
    from coolplot.core.limits import get_tp_limits
    from coolplot.thermo.fluid import Fluid
    from coolplot.thermo.isolines import compute_isoline
    from coolplot.thermo.limits import resolve_tp_box
    fluid = Fluid("HEOS::R407C.mix")
    box = resolve_tp_box(fluid, get_tp_limits("DEF"))
    curve = compute_isoline(fluid, DiagramType.parse("ph"), "rho", 100.0, box, 25, "flash")
    check = AbstractState("HEOS", "R407C.mix")
    checked = 0
    for h, p in zip(curve.x, curve.y):
        if np.isfinite(h) and np.isfinite(p):
            check.update(CoolProp.HmassP_INPUTS, h, p)
            assert check.rhomass() == pytest.approx(100.0, rel=1e-3)
            checked += 1
    assert checked >= 15   # the refused states leave gaps, they are not drawn wrong


def test_mixtures_start_at_the_highest_component_triple_point():
    from coolplot.thermo.fluid import Fluid
    # CoolProp reports the mole-weighted average for a mixture (129 K for
    # R32/R1234yf); R32 is solid below 136.3 K. Older CoolProp versions limit
    # R1234yf to 220 K, so the expected value is taken from the components.
    for blend, components in (("HEOS::R32[0.5]&R1234yf[0.5]", ("R32", "R1234yf")),
                              ("HEOS::R32[0.697615]&R125[0.302385]", ("R32", "R125"))):
        expected = max(Fluid(name).T_min_K for name in components)
        assert Fluid(blend).T_min_K == pytest.approx(expected, abs=0.01)
    assert Fluid("R32").T_triple_K == pytest.approx(136.34, abs=0.01)
    assert Fluid("HEOS::R32[0.697615]&R125[0.302385]").T_triple_K == pytest.approx(172.52, abs=0.01)


def test_incompressibles_plot_with_absolute_limits():
    from coolplot import PropertyDiagram
    with pytest.raises(ValueError, match="absolute temperature and pressure limits"):
        PropertyDiagram("INCOMP::MEG[0.3]", "Ts").update_scene()
    diagram = PropertyDiagram("INCOMP::MEG[0.3]", "Ts", tp_limits=[260.0, 370.0, 1e5, 1e6])
    diagram.set_isolines("p", num=4)
    diagram.set_isolines("h", num=4)
    scene = diagram.update_scene((400.0, 300.0))
    lines = [item for item in scene if item.group.startswith("iso/")]
    assert len(lines) == 8 and all(np.isfinite(line.x).sum() >= 100 for line in lines)
    with pytest.raises(ValueError, match="no two-phase region"):
        diagram.set_isolines("Q", num=3)
        diagram.update_scene()


def test_blend_lines_that_need_coolprop_8_are_skipped_with_a_reason(monkeypatch):
    import warnings
    from coolplot import PropertyDiagram
    from coolplot.thermo import isolines
    monkeypatch.setattr(isolines, "TRACER_AVAILABLE", False)   # as on CoolProp 6 and 7
    diagram = PropertyDiagram("HEOS::R32[0.697615]&R125[0.302385]", "ph", tp_limits="ACHP")
    diagram.set_isolines("T", values=[0.0])
    diagram.set_isolines("s", values=[1.5])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        scene = diagram.update_scene((400.0, 300.0))
    assert [i.group for i in scene if i.group.startswith("iso/")] == ["iso/T"]
    assert any("need CoolProp 8" in str(w.message) for w in caught)
