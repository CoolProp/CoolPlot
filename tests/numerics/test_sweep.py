# -*- coding: utf-8 -*-
"""Sweeps over every line family of every diagram type, for a few fluids.

These are the acceptance checks of the 0.7 numerics (docs/v1_plan.md):
every point of a line is a state that CoolProp confirms, lines have no
gaps or kinks, and almost nothing is computed outside the chart. They
take minutes per fluid and run only with ``pytest --run-slow``.
"""
import numpy as np
import pytest

CoolProp = pytest.importorskip("CoolProp")
from CoolProp.CoolProp import PropsSI  # noqa: E402

from coolplot.core.diagram_type import DiagramType  # noqa: E402
from coolplot.core.limits import get_tp_limits  # noqa: E402
from coolplot.core.quantities import get_quantity  # noqa: E402
from coolplot.engine.plan import nice_linear, nice_log  # noqa: E402
from coolplot.thermo.fluid import Fluid, build_state  # noqa: E402
from coolplot.thermo.isolines import _build_line, _metric, compute_quality_line  # noqa: E402
from coolplot.thermo.limits import property_range_SI, resolve_tp_box  # noqa: E402
from coolplot.thermo.tracer import _phases_are_distinct  # noqa: E402

pytestmark = pytest.mark.slow

TYPES = ("ph", "Ts", "hs", "ps", "prho", "Trho", "pT")
CP_NAME = {"T": "T", "p": "P", "h": "Hmass", "s": "Smass", "rho": "Dmass", "u": "Umass"}
CP_INDEX = {"T": CoolProp.iT, "p": CoolProp.iP, "h": CoolProp.iHmass, "s": CoolProp.iSmass,
            "rho": CoolProp.iDmass, "u": CoolProp.iUmass}


def _values(fluid, key, box, num=5):
    lo, hi = property_range_SI(fluid, key, box)
    values = nice_log(lo, hi, num) if get_quantity(key).log_scale and lo > 0.0 else nice_linear(lo, hi, num)
    return list(values[:: max(1, len(values) // num)])[:num + 1]


def _span(fluid, key, box):
    lo, hi = property_range_SI(fluid, key, box)
    return hi - lo


def _normalised(curve, diagram, fluid, box):
    """The valid points of a curve in normalised plot coordinates."""
    metric = _metric(fluid, diagram, box, None)
    ok = np.isfinite(curve.x) & np.isfinite(curve.y)
    points = np.array([metric.point(x, y) for x, y in zip(curve.x[ok], curve.y[ok])])
    return points


def _largest_turn_deg(points):
    """The largest turn between consecutive segments of a polyline, in degrees.

    Segments shorter than a hundredth of a percent of the chart are left
    out: a turn between two sub-pixel segments is invisible.
    """
    if len(points) < 3:
        return 0.0
    d = np.diff(points, axis=0)
    length = np.hypot(d[:, 0], d[:, 1])
    keep = length > 1e-4
    d = d[keep] / length[keep, None]
    if len(d) < 2:
        return 0.0
    cos = np.clip(np.sum(d[:-1] * d[1:], axis=1), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos)).max())


def _lines(fluid, box):
    for name in TYPES:
        diagram = DiagramType.parse(name)
        for key in diagram.supported_isolines():
            if key == "Q":
                continue
            for value in _values(fluid, key, box):
                yield diagram, key, float(value)


@pytest.fixture(scope="module", params=["HEOS::R290", "HEOS::CO2"])
def pure(request):
    # ACHP limits for both: with the default limits the p-h chart of CO2
    # has no liquid region on its h axis (the corner at T_min, p_max lies
    # below the melting line and does not contribute to the range), so
    # most of its lines lie outside the axes
    fluid = Fluid(request.param)
    return fluid, resolve_tp_box(fluid, get_tp_limits("ACHP"))


@pytest.fixture(scope="module", params=["HEOS::R410A.mix", "HEOS::R32[0.7]&R125[0.3]"])
def blend(request):
    fluid = Fluid(request.param)
    return fluid, resolve_tp_box(fluid, get_tp_limits("DEF"))


def _on_the_saturation_curve(fluid, T_K, p_Pa):
    """Whether a state sits on the saturation curve, where an inverse flash may answer from either side."""
    try:
        if T_K >= fluid.critical["T"]:
            return False
        p_sat = PropsSI("P", "T", T_K, "Q", 0, fluid.name)
    except Exception:
        return False
    return abs(p_Pa - p_sat) <= 1e-6 * p_sat


def test_pure_fluid_lines_round_trip_and_are_smooth(pure):
    """Every point of every line is a state at the line's constant.

    Each sample of the line is re-evaluated from its (T, p) or (p, Q)
    with a different input pair, which confirms it to 1e-8; the drawn
    points are also sent through CoolProp's inverse flash (T from h and
    p, say), which is looser (1e-7 for h,s inputs) and ambiguous on the
    saturation curve, so those points are left out of that check.
    """
    fluid, box = pure
    outside = [0, 0]
    for diagram, key, value in _lines(fluid, box):
        line = _build_line(fluid, diagram, key, value, box, 250, "auto")
        curve = line.curve()
        where = "{0} {1}={2:g}".format(diagram.name, key, value)
        assert curve.n_gaps == 0, where
        assert curve.n_outside <= 128, where   # a cap on the scanning: 32 points per part outside, plus the edges
        assert curve.reason == "" or curve.n_valid < 2, where
        outside[0] += curve.n_outside
        outside[1] += curve.n_evaluated
        if curve.n_valid < 2:
            continue   # a line that touches the axes' area at one point
        points = _normalised(curve, diagram, fluid, box)
        assert _largest_turn_deg(points) < 160.0, where   # no reversals; a hairpin on the dome is real
        span = _span(fluid, key, box)
        for sample in line.samples:
            if sample is None:
                continue
            w, T_K, p_Pa, Q, rho, source = sample.extra
            inputs = ("P", p_Pa, "Q", Q) if 0.0 <= Q <= 1.0 else ("P", p_Pa, "T", T_K)
            try:
                forward = [PropsSI(CP_NAME[k], *inputs, fluid.name) for k in (key, diagram.x, diagram.y)]
            except Exception:
                continue   # the checking flash refuses the state (below the triple pressure at T_min, say)
            # CoolProp's flashes agree with each other to about 1e-8 of the range
            assert forward[0] == pytest.approx(value, abs=1e-7 * span), where
            assert forward[1] == pytest.approx(sample.x, rel=1e-7), where
            assert forward[2] == pytest.approx(sample.y, rel=1e-7), where
            if _on_the_saturation_curve(fluid, T_K, p_Pa):
                continue
            try:
                back = PropsSI(CP_NAME[key], CP_NAME[diagram.x], sample.x, CP_NAME[diagram.y], sample.y, fluid.name)
            except Exception:
                continue   # the inverse flash itself failed; nothing to compare with
            assert back == pytest.approx(value, abs=1e-6 * span), where
    assert outside[0] <= 0.1 * outside[1]   # over the whole sweep, a tenth of the evaluations at most


def test_blend_lines_are_confirmed_states_and_are_smooth(blend):
    """Every point of every traced line is a state at the line's constant.

    Each sample of the line is re-evaluated from the (T, rho) root the
    tracer converged on, an explicit evaluation of the equation of state
    with the phase imposed, or from (p, Q) for a two-phase point.
    CoolProp's p,T flash of a mixture is not a usable check: next to the
    bubble line it can return a state with h = -12 MJ/kg without raising.
    """
    fluid, box = blend
    check = build_state(fluid.model_key)
    check.build_phase_envelope("veryfine")   # the p,Q flash near the critical point needs its guesses
    outside = [0, 0]
    for diagram, key, value in _lines(fluid, box):
        line = _build_line(fluid, diagram, key, value, box, 250, "auto")
        curve = line.curve()
        where = "{0} {1}={2:g}".format(diagram.name, key, value)
        assert curve.method == "tracer", where
        assert curve.n_gaps <= 2, where
        assert curve.n_outside <= 128, where
        assert curve.reason == "" or curve.n_valid < 2, where
        outside[0] += curve.n_outside
        outside[1] += curve.n_evaluated
        if curve.n_valid < 2:
            continue
        points = _normalised(curve, diagram, fluid, box)
        assert _largest_turn_deg(points) < 160.0, where
        confirmed = unverifiable = 0
        for sample in line.samples:
            if sample is None:
                continue
            w, T_K, p_Pa, Q, rho, source = sample.extra
            if 0.0 <= Q <= 1.0:
                check.unspecify_phase()
                check.update(CoolProp.PQ_INPUTS, p_Pa, Q)
                if not _phases_are_distinct(check):
                    unverifiable += 1   # the checking flash itself collapsed onto the trivial solution
                    continue
            else:
                check.specify_phase(CoolProp.iphase_gas)
                check.update(CoolProp.DmassT_INPUTS, rho, T_K)
            # The tracer's points reproduce their axis values to 1e-6 and
            # their constant to 1e-5 (the Newton residual is scaled by how
            # much the constant moves over T and rho, so the pressure of a
            # compressed liquid at 0.1 bar may be off by 3e-6 while s and
            # T are exact; the p,Q flash of a two-phase point has its own
            # 1e-6). A point the tracer handed to a cold flash carries
            # CoolProp's mixture flash tolerance, which near the critical
            # point reaches 1e-3 even between a flashed state's own h and
            # its (T, rho).
            key_tolerance, xy_tolerance = (1e-5, 1e-6) if source == "tracer" else (1e-2, 1e-2)
            assert check.keyed_output(CP_INDEX[key]) == pytest.approx(value, rel=key_tolerance), where
            assert (check.keyed_output(CP_INDEX[diagram.x]), check.keyed_output(CP_INDEX[diagram.y])) == \
                pytest.approx((sample.x, sample.y), rel=xy_tolerance), where
            confirmed += 1
        assert unverifiable <= 0.05 * (confirmed + unverifiable) + 2, where
    assert outside[0] <= 0.1 * outside[1]


def test_quality_lines_reach_the_top_of_the_dome(blend):
    fluid, box = blend
    envelope = fluid.phase_envelope()
    assert envelope is not None and envelope.closed
    for name in ("ph", "Ts"):
        diagram = DiagramType.parse(name)
        for quality in (0.25, 0.5, 0.75):
            curve = compute_quality_line(fluid, diagram, quality)
            assert curve.n_valid >= 50 and curve.n_gaps == 0
            assert (curve.x[-1], curve.y[-1]) == (envelope.top(diagram.x), envelope.top(diagram.y))
            # The last computed state before the top is within a few kelvin of it
            if name == "Ts":
                assert curve.y[-2] >= envelope.top("T") - 5.0
