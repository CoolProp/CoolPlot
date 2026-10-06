# -*- coding: utf-8 -*-
"""Property calculations, checked against CoolProp directly."""
import numpy as np
import pytest

CoolProp = pytest.importorskip("CoolProp")
from CoolProp.CoolProp import PropsSI  # noqa: E402

from CoolPlot.thermo import (DiagramType, Fluid, Relative, TpLimits, compute_isoline,  # noqa: E402
                             compute_quality_line, get_tp_limits, process_path, state_point)


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
    assert r290.critical["p"] == pytest.approx(PropsSI("pcrit", "R290"), rel=1e-9)
    T_lo_K, T_hi_K = r290.saturation_range("T")
    assert T_lo_K > PropsSI("Ttriple", "R290") and T_hi_K < r290.critical["T"]
    twin = r290.clone()
    assert twin.state is not r290.state and twin.model_key == r290.model_key


def test_tp_limits(r290):
    T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa = get_tp_limits("ACHP").resolve(r290)
    assert (T_lo_K, T_hi_K, p_lo_Pa) == (173.15, 493.15, 0.25e5)
    assert p_hi_Pa == pytest.approx(2.25 * r290.critical["p"], rel=1e-6)
    custom = TpLimits(250.0, Relative(1.1), 1e5, 5e6).resolve(r290)
    assert custom[1] == pytest.approx(1.1 * r290.critical["T"], rel=1e-6)
    with pytest.raises(ValueError):
        TpLimits(400.0, 300.0).resolve(r290)


def test_isotherm_matches_propssi(r290):
    ph = DiagramType.parse("ph")
    box = get_tp_limits("ACHP").resolve(r290)
    curve = compute_isoline(r290, ph, "T", 300.0, box, points=40)
    assert curve.n_failed == 0
    # Every point is a state at 300 K with the computed (p, h)
    for h, p in zip(curve.x[::7], curve.y[::7]):
        assert PropsSI("T", "P", p, "H", h, "R290") == pytest.approx(300.0, abs=1e-6)


def test_isentrope_in_ts_is_vertical_free(r290):
    # Constant enthalpy in a Ts chart, which older versions computed with
    # the slow (h, s) input pair
    ts = DiagramType.parse("Ts")
    box = get_tp_limits("ACHP").resolve(r290)
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
