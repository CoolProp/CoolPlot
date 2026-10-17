# -*- coding: utf-8 -*-
"""Lines of constant property, computed in SI units.

Everything here is a plain function of its inputs: a fluid, a diagram type,
the constant value and the ranges to cover. The result is a :class:`Curve`
with x and y arrays in SI units. Nothing in this module knows about units,
styles or plotting libraries, which is what allows results to be cached and
reused across unit systems and renderers.

Points that CoolProp cannot compute are kept as NaN. Renderers draw a gap
there instead of inventing data, which makes calculation problems visible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

import CoolProp
from CoolProp import CoolProp as CP

from ..core.quantities import get_quantity, quantity_key
from ..core.diagram_type import DiagramType
from .fluid import Fluid, parameter_index
from .tracer import TRACER_AVAILABLE, IsoLineTracer, _phases_are_distinct


@dataclass(frozen=True, eq=False)
class Curve:
    """x and y values of one line in SI units, with diagnostics

    ``n_failed`` counts the points CoolProp could not compute; they are NaN
    in x and y. ``n_fallback`` counts the points the tracer handed back to
    a plain flash, ``n_inserted`` the saturation states inserted where the
    line enters or leaves the two-phase region. ``method`` says how the
    line was computed: "flash", "tracer" or "envelope". ``reason`` says why
    a line could not be computed at all (then x and y are empty).
    """
    x: np.ndarray
    y: np.ndarray
    n_failed: int = 0
    n_fallback: int = 0
    n_inserted: int = 0
    method: str = "flash"
    reason: str = ""

    def __post_init__(self):
        for name in ("x", "y"):
            arr = np.array(getattr(self, name), dtype=float)
            arr.flags.writeable = False
            object.__setattr__(self, name, arr)

    def __reduce__(self):
        # Rebuild through the constructor, so that a curve coming back from
        # a worker process has read-only arrays again.
        return (Curve, (self.x, self.y, self.n_failed, self.n_fallback, self.n_inserted, self.method, self.reason))

    @property
    def n_valid(self) -> int:
        return int(np.sum(np.isfinite(self.x) & np.isfinite(self.y)))

    def to_dict(self) -> dict:
        """The curve record of docs/contracts.md; non-finite values become None."""
        return {"x": [float(v) if np.isfinite(v) else None for v in self.x],
                "y": [float(v) if np.isfinite(v) else None for v in self.y],
                "n_failed": self.n_failed, "n_fallback": self.n_fallback, "n_inserted": self.n_inserted,
                "method": self.method, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict) -> "Curve":
        nan = float("nan")
        return cls([nan if v is None else v for v in data["x"]], [nan if v is None else v for v in data["y"]],
                   data.get("n_failed", 0), data.get("n_fallback", 0), data.get("n_inserted", 0),
                   data.get("method", "flash"), data.get("reason", ""))

    @property
    def n_gaps(self) -> int:
        """Invalid points between the first and the last valid one.

        Failures at the ends of a line only make it shorter, which is
        expected, for example where a quality line of a mixture stops
        short of the critical point. Gaps inside a line are worth a warning.
        """
        valid = np.flatnonzero(np.isfinite(self.x) & np.isfinite(self.y))
        if len(valid) < 2:
            return 0
        return int(valid[-1] - valid[0] + 1 - len(valid))


SOLVERS = ("auto", "tracer", "flash")

#: Input pairs that CoolProp 6 and 7 can flash for mixtures.
_MIXTURE_PAIRS_BEFORE_8 = (CoolProp.PT_INPUTS, CoolProp.PQ_INPUTS, CoolProp.QT_INPUTS)


def _quality_or_nan(state) -> float:
    """The vapour quality of a state, NaN where the backend has none (incompressibles)."""
    try:
        return float(state.keyed_output(CoolProp.iQ))
    except Exception:
        return np.nan


def value_grid(key: str, lo: float, hi: float, num: int) -> np.ndarray:
    """Evenly spaced values, logarithmically for quantities shown on log axes."""
    if get_quantity(key).log_scale and lo > 0.0 and hi > 0.0:
        return np.geomspace(lo, hi, num)
    return np.linspace(lo, hi, num)


def _use_tracer(fluid: Fluid, solver: str) -> bool:
    """Whether to trace: "auto" traces mixtures only, where a flash is slow.

    Before CoolProp 8 the tracer is never used, see
    :data:`coolplot.thermo.tracer.TRACER_AVAILABLE`.
    """
    if solver not in SOLVERS:
        raise ValueError("Unknown solver '{0}', expected one of {1}.".format(solver, SOLVERS))
    if not TRACER_AVAILABLE:
        return False
    return solver == "tracer" or (solver == "auto" and not fluid.is_pure)


def compute_isoline(fluid: Fluid, diagram: DiagramType, iso_key: str, value_SI: float,
                    tp_box: Tuple[float, float, float, float], points: int = 250,
                    solver: str = "auto", margin: float = 1e-7) -> Curve:
    """Compute one line of constant ``iso_key`` in the axes of ``diagram``.

    The isoline quantity is held at ``value_SI`` while temperature or
    pressure (see :meth:`DiagramType.sweep_quantity`) steps through its
    range in ``tp_box`` = (T_min_K, T_max_K, p_min_Pa, p_max_Pa). Both axis
    values are read from each resulting state.

    Where the line enters or leaves the two-phase region, the saturation
    state is inserted, so the line has its kink exactly on the saturation
    curve instead of cutting the corner between two grid points. For an
    isobar in a T-s chart, for example, that is the horizontal part inside
    the dome.

    ``solver`` is "flash" (one CoolProp flash per point), "tracer" (walk
    along the line, see :mod:`coolplot.thermo.tracer`, with a flash for
    every point the tracer refuses) or "auto" (tracer for mixtures only).
    Lines of constant quality are delegated to :func:`compute_quality_line`.
    """
    iso_key = quantity_key(iso_key)
    if iso_key == "Q":
        return compute_quality_line(fluid, diagram, value_SI, points, margin)
    sweep_key = diagram.sweep_quantity(iso_key)
    if sweep_key is None:
        raise ValueError("Lines of constant '{0}' cannot be drawn in a {1} diagram.".format(
            iso_key, diagram.name))
    T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa = tp_box
    if sweep_key == "T":
        sweep = value_grid("T", T_lo_K, T_hi_K, points)
    else:
        sweep = value_grid("p", p_lo_Pa, p_hi_Pa, points)

    # CoolProp expects the two inputs in a fixed order for each input pair.
    # Ask once which order applies; generate_update_pair returns the values
    # in the order the pair needs them, so a zero in first place means the
    # constant goes first.
    iso_index, sweep_index = parameter_index(iso_key), parameter_index(sweep_key)
    pair, first, _ = CP.generate_update_pair(iso_index, 0.0, sweep_index, 1.0)
    constant_first = (first == 0.0)
    inputs = (iso_index, sweep_index) if constant_first else (sweep_index, iso_index)
    out_indices = (parameter_index(diagram.x), parameter_index(diagram.y))

    if not fluid.is_pure and not TRACER_AVAILABLE and pair not in _MIXTURE_PAIRS_BEFORE_8:
        # The h,p / s,p / rho,T flashes of CoolProp 6 and 7 do not support mixtures
        return Curve([], [], 0, method="flash", reason=(
            "lines of constant {0} of a blend need CoolProp 8 (the flashes of CoolProp {1} that they need do not "
            "support mixtures); isotherms, isobars and quality lines work".format(
                iso_key, getattr(CoolProp, "__version__", "?"))))

    tracer = None
    if _use_tracer(fluid, solver) and IsoLineTracer.supports(*inputs):
        try:
            tracer = IsoLineTracer(fluid, inputs[0], inputs[1], iso_index)
        except Exception:
            tracer = None   # every point is flashed instead

    x = np.full_like(sweep, np.nan)
    y = np.full_like(sweep, np.nan)
    quality = np.full_like(sweep, np.nan)
    n_failed = n_fallback = 0
    for i, sweep_value in enumerate(sweep):
        v1, v2 = (value_SI, sweep_value) if constant_first else (sweep_value, value_SI)
        if tracer is not None:
            try:
                tracer.update(v1, v2)
                x[i], y[i] = (tracer.keyed_output(k) for k in out_indices)
                quality[i] = _quality_or_nan(tracer)
                if np.isfinite(x[i]) and np.isfinite(y[i]):
                    continue
            except Exception:
                pass
            n_fallback += 1
        try:
            # update_pair retries a mixture on the envelope-built scratch state
            # and refuses a state CoolProp got wrong, see Fluid.inconsistency
            state = fluid.update_pair(pair, v1, v2)
            x[i], y[i] = (state.keyed_output(k) for k in out_indices)
            quality[i] = _quality_or_nan(state)
            if tracer is not None:
                tracer.set_guess(state)
        except Exception:
            x[i] = y[i] = np.nan
            n_failed += 1  # stays NaN, see the module docstring

    inserted = _saturation_crossings(fluid, diagram, iso_key, value_SI, sweep_key, sweep, quality, margin)
    if inserted:
        x, y = _insert(sweep, x, y, inserted, sweep_key)
    return Curve(x, y, n_failed, n_fallback, len(inserted), "tracer" if tracer is not None else "flash")


# ---------------------------------------------------------------------------
# Saturation states on an isoline
# ---------------------------------------------------------------------------
def _saturation_state(fluid: Fluid, sat_key: str, sat_value: float, quality: float, diagram: DiagramType,
                      iso_key: str):
    """(iso value, x, y) of the saturation state at T or p = sat_value, or None."""
    pair = CoolProp.QT_INPUTS if sat_key == "T" else CoolProp.PQ_INPUTS
    state = fluid.state
    try:
        if sat_key == "T":
            state.update(pair, quality, sat_value)
        else:
            state.update(pair, sat_value, quality)
        result = tuple(state.keyed_output(parameter_index(k)) for k in (iso_key, diagram.x, diagram.y))
    except Exception:
        return None
    return result if all(np.isfinite(result)) else None


def _solve_crossing(fluid, diagram, iso_key, value_SI, sweep_key, a, b, quality):
    """Sweep value in [a, b] where the saturation state has iso_key == value_SI.

    Regula falsi with the Illinois modification, which converges quickly
    and never leaves the bracket. Returns (sweep value, x, y) or None.
    """
    ends = [_saturation_state(fluid, sweep_key, v, quality, diagram, iso_key) for v in (a, b)]
    if None in ends:
        return None
    fa, fb = ends[0][0] - value_SI, ends[1][0] - value_SI
    if fa == 0.0:
        return a, ends[0][1], ends[0][2]
    if fb == 0.0:
        return b, ends[1][1], ends[1][2]
    if fa * fb > 0.0:
        return None
    result = None
    for _ in range(60):
        c = b - fb * (b - a) / (fb - fa)
        found = _saturation_state(fluid, sweep_key, c, quality, diagram, iso_key)
        if found is None:
            return None
        fc = found[0] - value_SI
        result = (c, found[1], found[2])
        if fc == 0.0 or abs(b - a) <= 1e-12 * abs(c):
            break
        if fc * fb < 0.0:
            a, fa = b, fb
        else:
            fa *= 0.5
        b, fb = c, fc
        if abs(fc) <= 1e-10 * max(abs(value_SI), 1.0):
            break
    return result


def _saturation_crossings(fluid, diagram, iso_key, value_SI, sweep_key, sweep, quality, margin):
    """Saturation states where the isoline meets the saturation curve.

    Returns a list of (sweep value, quality, x, y).

    * For an isotherm or isobar the bubble and dew states at the constant
      itself are inserted, if it is below the critical value.
    * For any other isoline, a crossing lies between two neighbouring
      points of which one is two-phase (0 <= quality <= 1) and the other is
      not. It is found by a one-dimensional solve along the saturation
      curve.
    * For a mixture, the crossings are found along the phase envelope,
      because the saturation flash of a mixture fails near the critical
      point, exactly where an isoline is most likely to meet the dome.
    """
    if not fluid.has_critical_point:
        return []   # no saturation curve, nothing to cross (incompressibles)
    envelope = fluid.phase_envelope()
    if envelope is not None:
        return _envelope_crossings(envelope, diagram, iso_key, value_SI, sweep_key, sweep)
    found = []
    if iso_key in ("T", "p"):
        try:
            lo, hi = fluid.saturation_range(iso_key, margin)
        except Exception:
            return found
        if not lo <= value_SI <= hi:
            return found
        sweep_lo, sweep_hi = min(sweep[0], sweep[-1]), max(sweep[0], sweep[-1])
        for q in (0.0, 1.0):
            try:
                fluid.update(iso_key, value_SI, "Q", q)
                sweep_value = fluid.get(sweep_key)
                x, y = fluid.get(diagram.x), fluid.get(diagram.y)
            except Exception:
                continue
            if sweep_lo <= sweep_value <= sweep_hi and np.isfinite(x) and np.isfinite(y):
                found.append((sweep_value, q, x, y))
        return found

    two_phase = (quality >= 0.0) & (quality <= 1.0)
    for i in range(len(sweep) - 1):
        if not (np.isfinite(quality[i]) and np.isfinite(quality[i + 1])) or two_phase[i] == two_phase[i + 1]:
            continue
        q_inside = quality[i] if two_phase[i] else quality[i + 1]
        # Try the nearer saturation line first; the other one if that fails
        for q in sorted((0.0, 1.0), key=lambda b: abs(b - q_inside)):
            crossing = _solve_crossing(fluid, diagram, iso_key, value_SI, sweep_key, sweep[i], sweep[i + 1], q)
            if crossing is not None:
                found.append((crossing[0], q, crossing[1], crossing[2]))
                break
    return found


def _envelope_crossings(envelope, diagram, iso_key, value_SI, sweep_key, sweep):
    """Where an isoline crosses the phase envelope of a mixture.

    The envelope has about 300 closely spaced points. Between two
    neighbours where the isoline quantity passes ``value_SI`` the crossing
    is interpolated linearly, which is accurate to well below the line
    width. Only crossings inside the swept range are returned.
    """
    k = envelope.values(iso_key)
    s_values = envelope.values(sweep_key)
    x_values, y_values = envelope.values(diagram.x), envelope.values(diagram.y)
    sweep_lo, sweep_hi = min(sweep[0], sweep[-1]), max(sweep[0], sweep[-1])
    found = []
    f = k - value_SI
    for i in range(len(f) - 1):
        a, b = f[i], f[i + 1]
        if not (np.isfinite(a) and np.isfinite(b)) or a * b > 0.0 or a == b:
            continue
        if b == 0.0 and i + 1 < len(f) - 1:
            continue   # an exact hit on a point is counted once, by the next pair
        t = a / (a - b)
        point = [v[i] + t * (v[i + 1] - v[i]) for v in (s_values, x_values, y_values)]
        if not all(np.isfinite(point)) or not sweep_lo <= point[0] <= sweep_hi:
            continue
        quality = envelope.Q[i] if t < 0.5 else envelope.Q[i + 1]
        found.append((point[0], quality, point[1], point[2]))
    return found


def _insert(sweep, x, y, inserted, sweep_key):
    """Merge inserted states into the line, ordered by the sweep value.

    For a pure fluid the bubble and dew states of an isotherm or isobar have
    the same sweep value. The tie is broken by the direction of the sweep:
    stepping up in temperature goes from liquid to vapour (bubble first),
    stepping up in pressure from vapour to liquid (dew first).
    """
    increasing = sweep[-1] >= sweep[0]
    keys = [(s, 0, 0.0) for s in sweep]
    rows = list(zip(keys, x, y))
    for sweep_value, q, xi, yi in inserted:
        tie = q if sweep_key == "T" else -q
        rows.append(((sweep_value, 1, tie), xi, yi))

    def order(row):
        s, kind, tie = row[0]
        return (s if increasing else -s, kind, tie)
    rows.sort(key=order)
    return np.array([r[1] for r in rows]), np.array([r[2] for r in rows])


# ---------------------------------------------------------------------------
# Lines of constant quality
# ---------------------------------------------------------------------------
def _base_backend_fluid(fluid: Fluid) -> Fluid:
    """For a tabular backend such as "BICUBIC&HEOS", the same fluid on "HEOS".

    Tables are inaccurate near the critical point, which makes the dome
    close with a kink. The saturation curve is drawn with the equation of
    state the tables were built from.
    """
    backend = fluid.model_key[0]
    if "&" in backend and backend.split("&", 1)[0].upper() in ("BICUBIC", "TTSE"):
        return fluid.with_backend(backend.split("&", 1)[1])
    return fluid


def compute_quality_line(fluid: Fluid, diagram: DiagramType, quality: float, points: int = 250,
                         margin: float = 1e-7, spacing: str = "critical") -> Curve:
    """Line of constant vapour quality from the lowest temperature to the critical point.

    Quality 0 is the bubble line and quality 1 the dew line. With
    ``spacing="critical"`` the temperature steps get denser towards the
    critical point, where the line bends most; "linear" spaces them evenly.
    ``margin`` is passed to :meth:`Fluid.saturation_range`. For pure fluids
    every quality line ends at the critical point, which is appended so
    that the saturation dome closes.

    The bubble and dew lines of a mixture come from CoolProp's phase
    envelope, which follows the dome through the critical region where
    the saturation flash fails. They have as many points as the refined
    envelope (about 300), independent of ``points``.
    """
    if not 0.0 <= quality <= 1.0:
        raise ValueError("The vapour quality has to be between 0 and 1, not {0}.".format(quality))
    fluid = _base_backend_fluid(fluid)
    if not fluid.has_critical_point:
        raise ValueError("{0} has no two-phase region (CoolProp provides no critical point for it), so lines of "
                         "constant quality cannot be drawn.".format(fluid.name))
    if not fluid.is_pure and quality in (0.0, 1.0):
        curve = _envelope_line(fluid, diagram, quality)
        if curve is not None:
            return curve
    T_lo_K, T_hi_K = fluid.saturation_range("T", margin)
    u = np.linspace(0.0, 1.0, points)
    if spacing == "critical":
        u = 1.0 - (1.0 - u) ** 2
    elif spacing != "linear":
        raise ValueError("Unknown saturation spacing '{0}'.".format(spacing))
    T_K = T_lo_K + (T_hi_K - T_lo_K) * u

    x_index = parameter_index(diagram.x)
    y_index = parameter_index(diagram.y)
    state = fluid.state
    x = np.full_like(T_K, np.nan)
    y = np.full_like(T_K, np.nan)
    n_failed = 0
    for i, T in enumerate(T_K):
        try:
            state.update(CoolProp.QT_INPUTS, quality, T)
            if not fluid.is_pure and not _phases_are_distinct(state):
                raise ValueError("trivial solution")
            x[i] = state.keyed_output(x_index)
            y[i] = state.keyed_output(y_index)
        except Exception:
            n_failed += 1

    if fluid.is_pure:
        crit = fluid.critical
        x_crit, y_crit = crit.get(diagram.x, np.nan), crit.get(diagram.y, np.nan)
        if np.isfinite(x_crit) and np.isfinite(y_crit):
            x = np.append(x, x_crit)
            y = np.append(y, y_crit)
    return Curve(x, y, n_failed)


def _envelope_line(fluid: Fluid, diagram: DiagramType, quality: float):
    """Bubble (0) or dew (1) line of a mixture from the phase envelope, or None.

    See :class:`coolplot.thermo.fluid.PhaseEnvelope` for how the states
    are obtained. The bubble line also gets the dew point next to it in
    the trace, which closes the dome across the critical region between
    the two branches.
    """
    envelope = fluid.phase_envelope()
    if envelope is None:
        return None
    Q = envelope.Q
    dew = np.flatnonzero(Q == 1.0)
    bubble = np.flatnonzero(Q == 0.0)
    if len(dew) < 2 or len(bubble) < 2:
        return None
    if quality == 1.0:
        rows = dew
    elif dew[-1] + 1 == bubble[0]:
        # The usual trace order: up the dew line, down the bubble line. The
        # dew point next to the first bubble point closes the dome.
        rows = np.concatenate(([dew[-1]], bubble))
    elif bubble[-1] + 1 == dew[0]:
        rows = np.concatenate((bubble, [dew[0]]))
    else:
        rows = bubble
    x = envelope.values(diagram.x)[rows]
    y = envelope.values(diagram.y)[rows]
    n_failed = int(np.sum(~(np.isfinite(x) & np.isfinite(y))))
    if n_failed > len(rows) // 2:
        return None
    return Curve(x, y, n_failed, method="envelope")
