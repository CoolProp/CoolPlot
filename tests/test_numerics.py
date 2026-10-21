# -*- coding: utf-8 -*-
"""Isolines through the two-phase region, the tracer and the mixture dome."""
import numpy as np
import pytest

CoolProp = pytest.importorskip("CoolProp")
from CoolProp.CoolProp import PropsSI  # noqa: E402

from coolplot.thermo import (DiagramType, Fluid, compute_isoline, compute_quality_line,  # noqa: E402
                             get_tp_limits, resolve_tp_box)

TS = DiagramType.parse("Ts")
PH = DiagramType.parse("ph")


@pytest.fixture(scope="module")
def r290():
    return Fluid("HEOS::R290")


@pytest.fixture(scope="module")
def blend():
    return Fluid("HEOS::R32[0.7]&R125[0.3]")


def test_isobar_runs_horizontally_through_the_dome(r290):
    box = resolve_tp_box(r290, get_tp_limits("ACHP"))
    p_Pa = 5e5
    curve = compute_isoline(r290, TS, "p", p_Pa, box, points=50)
    assert curve.n_inserted == 2 and curve.n_failed == 0
    T_sat_K = PropsSI("T", "P", p_Pa, "Q", 0, "R290")
    s_liq, s_vap = (PropsSI("S", "P", p_Pa, "Q", q, "R290") for q in (0, 1))
    i = int(np.argmin(np.abs(curve.x - s_liq)))
    j = int(np.argmin(np.abs(curve.x - s_vap)))
    # The bubble and dew states are on the line, exactly, with the tie line
    # between them at the saturation temperature
    assert curve.x[i] == pytest.approx(s_liq, rel=1e-9) and curve.x[j] == pytest.approx(s_vap, rel=1e-9)
    assert j > i + 1 and curve.y[i:j + 1] == pytest.approx(T_sat_K, rel=1e-9)
    # T rises monotonically along the isobar; s too
    assert np.all(np.diff(curve.y) >= -1e-9) and np.all(np.diff(curve.x) > 0.0)


def test_isotherm_in_ph_has_its_kinks_on_the_dome(r290):
    box = resolve_tp_box(r290, get_tp_limits("ACHP"))
    curve = compute_isoline(r290, PH, "T", 280.0, box, points=30)
    assert curve.n_inserted == 2
    h_liq, h_vap = (PropsSI("H", "T", 280.0, "Q", q, "R290") for q in (0, 1))
    for h in (h_liq, h_vap):
        assert np.min(np.abs(curve.x - h)) < 1e-6 * h


def test_isenthalp_meets_the_bubble_line_exactly(r290):
    box = resolve_tp_box(r290, get_tp_limits("ACHP"))
    h = 3e5
    curve = compute_isoline(r290, TS, "h", h, box, points=40)
    assert curve.n_inserted >= 1
    # Some point lies on the bubble line: its (T, s) is a saturated liquid state
    s_liq = np.array([PropsSI("S", "T", T, "Q", 0, "R290") for T in curve.y if 170.0 < T < 369.0])
    s_line = np.array([s for s, T in zip(curve.x, curve.y) if 170.0 < T < 369.0])
    assert np.min(np.abs(s_line - s_liq)) < 1e-6 * np.max(s_liq)


def test_tracer_agrees_with_flash_and_is_faster(blend):
    import time
    from coolplot.thermo.isolines import _LineSolver
    box = resolve_tp_box(blend, get_tp_limits("ACHP"))
    t0 = time.perf_counter()
    traced = compute_isoline(blend, TS, "h", 4e5, box, points=25, solver="tracer")
    t1 = time.perf_counter()
    flashed = compute_isoline(blend, TS, "h", 4e5, box, points=25, solver="flash")
    t2 = time.perf_counter()
    assert traced.method == "tracer" and flashed.method == "flash"
    assert traced.n_valid >= 20 and flashed.n_valid >= 20
    assert (t1 - t0) < (t2 - t1)
    # The two lines step the pressure differently, so compare the two ways
    # of computing a point at the same pressures: inside and outside the dome
    tracer = _LineSolver(blend, "h", 4e5, "p", TS, None, "tracer")
    flash = _LineSolver(blend, "h", 4e5, "p", TS, None, "flash")
    compared = 0
    for p_Pa in np.geomspace(1e5, 3e6, 7):
        a, b = tracer.sample(p_Pa), flash.sample(p_Pa)
        assert a is not None and a.extra[-1] == "tracer"
        if b is None:
            continue   # CoolProp's H-p flash of a mixture refuses some two-phase states (CoolProp master)
        compared += 1
        assert (a.x, a.y) == pytest.approx((b.x, b.y), rel=1e-8)
    assert compared >= 5


def test_auto_solver_traces_mixtures_only(r290, blend):
    box = resolve_tp_box(r290, get_tp_limits("ACHP"))
    assert compute_isoline(r290, TS, "p", 5e5, box, points=10).method == "flash"
    box = resolve_tp_box(blend, get_tp_limits("ACHP"))
    assert compute_isoline(blend, TS, "p", 5e5, box, points=10).method == "tracer"
    with pytest.raises(ValueError):
        compute_isoline(blend, TS, "p", 5e5, box, points=10, solver="newton")


def test_mixture_dome_from_the_phase_envelope(blend):
    bubble = compute_quality_line(blend, PH, 0.0)
    dew = compute_quality_line(blend, PH, 1.0)
    assert bubble.method == dew.method == "envelope"
    assert bubble.n_failed == 0 and dew.n_failed == 0
    # The dome closes: the bubble line starts where the dew line ends
    assert (bubble.x[0], bubble.y[0]) == (dew.x[-1], dew.y[-1])
    # Every point is an envelope state: in a T-rho chart the bubble line
    # runs through the envelope's temperatures and bulk densities (CoolProp
    # keeps the bulk phase in the "vap" fields on both branches)
    state = CoolProp.AbstractState("HEOS", "R32&R125")
    state.set_mole_fractions([0.7, 0.3])
    state.build_phase_envelope("veryfine")
    data = state.get_phase_envelope_data()
    on_bubble = np.array(data.Q) == 0.0
    trho = compute_quality_line(blend, DiagramType.parse("Trho"), 0.0)
    assert trho.y[1:] == pytest.approx(np.array(data.T)[on_bubble], rel=1e-12)
    assert trho.x[1:] == pytest.approx(np.array(data.rhomolar_vap)[on_bubble] * state.molar_mass(), rel=1e-12)
    assert bubble.y[1:] == pytest.approx(np.array(data.p)[on_bubble], rel=1e-12)
    # The bulk on the bubble line is liquid: at the same temperature the
    # bubble state agrees with a QT flash (away from the critical point)
    i = len(bubble.x) * 3 // 4
    T_K = trho.y[i]
    blend.update("T", T_K, "Q", 0.0)
    assert (blend.get("h"), blend.get("p")) == pytest.approx((bubble.x[i], bubble.y[i]), rel=1e-4)


def test_tabular_backend_draws_the_dome_with_its_equation_of_state():
    try:
        tabular = Fluid("BICUBIC&HEOS::R290")
    except Exception:
        pytest.skip("tabular backends are not available")
    reference = compute_quality_line(Fluid("HEOS::R290"), PH, 1.0, points=40)
    curve = compute_quality_line(tabular, PH, 1.0, points=40)
    assert curve.x == pytest.approx(reference.x, rel=1e-9, nan_ok=True)


def test_gaps_count_only_inside_the_line():
    from coolplot.thermo import Curve
    nan = float("nan")
    assert Curve([nan, 1, 2, nan, 4, nan, nan], [nan, 1, 2, nan, 4, nan, nan], n_failed=4).n_gaps == 1
    assert Curve([1, 2, nan], [1, 2, nan]).n_gaps == 0


def test_blend_lines_meet_the_dome_near_the_critical_point(blend):
    # The saturation flash of the blend fails above about 340 K, so these
    # crossings can only come from the phase envelope
    box = resolve_tp_box(blend, get_tp_limits("ACHP"))
    isochore = compute_isoline(blend, PH, "rho", 300.0, box, points=40)
    assert isochore.n_inserted == 1
    isotherm = compute_isoline(blend, PH, "T", 340.0, box, points=40)
    assert isotherm.n_inserted == 2
    # The two inserted states of the isotherm sit at 340 K on the envelope
    envelope = blend.phase_envelope()
    T_env, p_env = envelope.values("T"), envelope.values("p")
    for quality in (0.0, 1.0):
        branch = envelope.Q == quality
        order = np.argsort(T_env[branch])
        p_sat = np.interp(340.0, T_env[branch][order], p_env[branch][order])
        assert np.min(np.abs(isotherm.y - p_sat)) < 1e-4 * p_sat
    assert envelope is not None and len(envelope) > 100
    assert np.all(np.isfinite(envelope.values("h")))


def test_pure_fluids_have_no_envelope(r290):
    assert r290.phase_envelope() is None


def test_a_straight_line_across_the_chart_gets_about_half_the_resolution():
    # The documented meaning of Settings.calc.points: a straight line that
    # crosses the whole chart gets about points / 2 points
    from coolplot.thermo.stepping import Metric, Sample, trace
    metric = Metric((0.0, 1.0), (0.0, 1.0))
    for points in (100, 250, 500):
        line = trace(lambda u, careful: Sample(u, 0.5), metric, points)
        n = len([s for s in line.samples if s is not None])
        assert abs(n - points / 2) <= 0.1 * points / 2


def test_a_line_where_no_state_can_be_computed_says_so(r290):
    """A failed look while scanning outside counts as outside, so the reason
    has to come from the evaluations that worked: here none did."""
    box = resolve_tp_box(r290, get_tp_limits("ACHP"))
    curve = compute_isoline(r290, PH, "T", -50.0, box, points=20)
    assert np.count_nonzero(np.isfinite(curve.x)) == 0
    assert curve.reason.startswith("none of the")


def test_states_computed_outside_the_axes_are_reported_as_such():
    """A failed evaluation followed by states that lie outside the axes: the
    reason says where the states are, not that none could be computed."""
    from types import SimpleNamespace
    from coolplot.thermo.isolines import _Line
    from coolplot.thermo.stepping import Metric, Sample, trace

    def evaluate(u, careful):
        if u == 0.0:
            return None                          # the first, careful look fails
        return Sample(u, 2.0, inside=False)      # the rest lie above the chart

    metric = Metric((0.0, 1.0), (0.0, 1.0))
    found = trace(evaluate, metric, 20)
    assert found.n_failed >= 1 and found.n_outside_ok >= 1
    assert not [s for s in found.samples if s is not None]

    solver = SimpleNamespace(n_fallback=0, method="flash")
    line = _Line(None, PH, "T", 300.0, None, metric, 20, solver)
    line._count(found)
    assert "lie in the area the axes show" in line.curve().reason


def test_a_quality_residual_that_is_not_a_number_stops_the_solver():
    from coolplot.thermo.tracer import IsoLineTracer
    tracer = object.__new__(IsoLineTracer)        # only the regula falsi is exercised
    tracer._quality_residual = lambda quality, bracket: float("nan")
    with pytest.raises(ValueError, match="not a number"):
        tracer._bracketed_quality({}, -1.0, 1.0, 2.0)


def test_a_saturation_density_that_is_not_a_number_leaves_the_root_undecided():
    """A NaN vapour density made the inside-the-dome test false, so a root
    inside the dome was taken as outside it."""
    from coolplot.thermo.tracer import IsoLineTracer

    class NanVapour:
        quality = 0.0
        def update(self, pair, quality, T):
            self.quality = quality
        def rhomolar(self):
            return 10000.0 if self.quality == 0.0 else float("nan")
        def p(self):
            return 1e6

    tracer = object.__new__(IsoLineTracer)        # only the dome check is exercised
    tracer._dome_T_limit = None
    tracer._sat = NanVapour()
    tracer._is_plausible_saturation = lambda T, p: True
    tracer._far_from_the_dome = lambda T, rhomolar: False
    with pytest.raises(ValueError, match="not a number"):
        tracer._check_outside_the_dome(300.0, 5000.0)


def test_a_crossing_that_does_not_converge_is_no_crossing(r290, monkeypatch):
    """Saturation states that come back NaN inside the bracket never converge;
    the solver used to return its last iterate (at a NaN sweep value) as the crossing."""
    import coolplot.thermo.isolines as isolines
    ends = {300.0: (-1.0, 0.0, 0.0, 300.0, 1e6, 1.0), 310.0: (1.0, 0.0, 0.0, 310.0, 1e6, 1.0)}
    nan_state = (float("nan"),) * 6
    monkeypatch.setattr(isolines, "_saturation_state",
                        lambda fluid, key, value, quality, diagram, iso_key: ends.get(value, nan_state))
    assert isolines._solve_crossing(r290, PH, "h", 0.0, "T", 300.0, 310.0, 0.0, None) is None


def test_dome_ends_with_the_same_sweep_value_are_ordered_by_quality():
    from coolplot.thermo.isolines import _dome_end_comes_first, _same_sweep_value
    assert _same_sweep_value(300.0, 300.0 * (1.0 + 1e-15))
    assert not _same_sweep_value(300.0, 300.001)
    w_noisy = 300.0 * (1.0 + 1e-15)                                 # the liquid end, a few bits above the vapour end
    assert _dome_end_comes_first(w_noisy, 0.0, 300.0, 1.0, True)        # sweep in T: liquid first
    assert not _dome_end_comes_first(w_noisy, 0.0, 300.0, 1.0, False)   # sweep in p: vapour first
    assert _dome_end_comes_first(300.0, 1.0, 300.001, 0.0, True)        # distinct sweep values decide


def test_sign_tests_and_cache_keys_without_float_equality():
    from coolplot.thermo.floats import is_zero, same_bits, sign_of
    assert [sign_of(v) for v in (-2.0, 0.0, -0.0, 3.0)] == [-1, 0, 0, 1]
    assert sign_of(np.float64(-1e-300)) == -1          # numpy scalars from the envelope arrays
    assert same_bits(300.0, 300.0) and same_bits(np.float64(300.0), 300.0)
    assert not same_bits(300.0, np.nextafter(300.0, 400.0))
    assert not same_bits(0.0, -0.0)
    assert same_bits(float("nan"), float("nan"))      # the same failed input is the same cache entry
    assert is_zero(0.0) and is_zero(-0.0) and is_zero(np.float64(0.0))
    assert not is_zero(5e-324) and not is_zero(float("nan")) and not is_zero(float("inf"))
    from coolplot.thermo.native import _same_number
    assert _same_number(0.0, -0.0) and _same_number(0.5, 0.5) and not _same_number(0.5, np.nextafter(0.5, 1.0))
    assert not _same_number(float("nan"), float("nan"))       # as with ==: NaN is not the default


def test_a_state_whose_saturated_outputs_fail_is_not_two_phases():
    from coolplot.thermo.tracer import _phases_are_distinct

    class Failing:
        def saturated_liquid_keyed_output(self, key):
            raise ValueError("no saturated states")
        saturated_vapor_keyed_output = saturated_liquid_keyed_output
    assert not _phases_are_distinct(Failing())


def test_a_limit_that_is_not_a_number_is_refused(r290):
    from coolplot.core.limits import Relative, TpLimits
    with pytest.raises(ValueError, match="not a number"):
        resolve_tp_box(r290, TpLimits(float("nan"), 400.0, 1e5, 1e7))
    with pytest.raises(ValueError, match="not a number"):
        resolve_tp_box(r290, TpLimits(Relative(float("nan")), 400.0, 1e5, 1e7))


def test_a_quality_line_without_states_says_why(r290, monkeypatch):
    import coolplot.thermo.isolines as isolines

    def no_states(fluid, diagram, quality, T_K):
        nan = np.full_like(T_K, np.nan)
        return nan, nan.copy(), len(T_K)
    monkeypatch.setattr(isolines, "_saturation_states", no_states)
    curve = compute_quality_line(r290, PH, 0.5, points=10)
    assert curve.reason == "none of the 10 states of the line could be computed"
