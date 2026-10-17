# -*- coding: utf-8 -*-
"""Lines of constant property, computed in SI units.

Everything here is a plain function of its inputs: a fluid, a diagram type,
the constant value and the ranges to cover. The result is a :class:`Curve`
with x and y arrays in SI units. Nothing in this module knows about units,
styles or plotting libraries, which is what allows results to be cached and
reused across unit systems and renderers.

How a line is computed (see docs/architecture.md, "Numerics"):

* Temperature or pressure is stepped through its range in the T-p box of
  the chart, with steps chosen from the shape of the line in plot
  coordinates (:mod:`coolplot.thermo.stepping`): straight parts get few
  points, bends more. Nothing is computed outside the area the axes show
  (the ranges of the two axis quantities over the box) except the points
  that locate where the line enters or leaves it.
* Each point is a state with the constant and the stepped quantity as
  inputs. Mixtures are traced (:mod:`coolplot.thermo.tracer`), warm
  starting every point from the one before; pure fluids are flashed, which
  CoolProp does quickly and reliably for them.
* The two-phase region is handled by the phase boundary. An isotherm or
  isobar crosses it at one temperature or pressure: the single-phase parts
  stop at the bubble and dew states and the part in between is stepped in
  vapour quality, so that a blend's glide is drawn and a pure fluid's
  straight tie line is exact. Every other line crosses the boundary where
  the phase of its points changes; the saturation state there is found on
  the saturation curve (pure fluids) or on the phase envelope (mixtures)
  and inserted.

Points that CoolProp cannot compute leave a gap (NaN) in the line.
Renderers draw a gap there instead of inventing data, which makes
calculation problems visible.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

import numpy as np

import CoolProp
from CoolProp import CoolProp as CP

from ..core.quantities import get_quantity, quantity_key
from ..core.diagram_type import DiagramType
from .fluid import Fluid, parameter_index
from .limits import property_range_SI
from .stepping import Metric, Sample, trace
from .tracer import IsoLineTracer, _phases_are_distinct


@dataclass(frozen=True, eq=False)
class Curve:
    """x and y values of one line in SI units, with diagnostics

    ``n_failed`` counts the points CoolProp could not compute (they leave
    a gap), ``n_fallback`` the points the tracer handed back to a plain
    flash, ``n_inserted`` the saturation states inserted where the line
    enters or leaves the two-phase region. ``method`` says how the line
    was computed: "flash", "tracer" or "envelope". ``reason`` says why a
    line could not be computed at all (then x and y are empty).
    ``n_evaluated`` is the number of states computed for the line and
    ``n_outside`` how many of them lay outside the calculation domain.
    """
    x: np.ndarray
    y: np.ndarray
    n_failed: int = 0
    n_fallback: int = 0
    n_inserted: int = 0
    method: str = "flash"
    reason: str = ""
    n_evaluated: int = 0
    n_outside: int = 0

    def __post_init__(self):
        for name in ("x", "y"):
            arr = np.array(getattr(self, name), dtype=float)
            arr.flags.writeable = False
            object.__setattr__(self, name, arr)

    def __reduce__(self):
        # Rebuild through the constructor, so that a curve coming back from
        # a worker process has read-only arrays again.
        return (Curve, (self.x, self.y, self.n_failed, self.n_fallback, self.n_inserted, self.method, self.reason,
                        self.n_evaluated, self.n_outside))

    @property
    def n_valid(self) -> int:
        return int(np.sum(np.isfinite(self.x) & np.isfinite(self.y)))

    def to_dict(self) -> dict:
        """The curve record of docs/contracts.md; non-finite values become None."""
        return {"x": [float(v) if np.isfinite(v) else None for v in self.x],
                "y": [float(v) if np.isfinite(v) else None for v in self.y],
                "n_failed": self.n_failed, "n_fallback": self.n_fallback, "n_inserted": self.n_inserted,
                "method": self.method, "reason": self.reason,
                "n_evaluated": self.n_evaluated, "n_outside": self.n_outside}

    @classmethod
    def from_dict(cls, data: dict) -> "Curve":
        nan = float("nan")
        return cls([nan if v is None else v for v in data["x"]], [nan if v is None else v for v in data["y"]],
                   data.get("n_failed", 0), data.get("n_fallback", 0), data.get("n_inserted", 0),
                   data.get("method", "flash"), data.get("reason", ""),
                   data.get("n_evaluated", 0), data.get("n_outside", 0))

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

#: A state counts as inside the axes up to this fraction of the axis
#: range beyond their edges, so that a line that ends exactly on an edge
#: keeps its end point.
EDGE_TOLERANCE = 1e-7


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
    """Whether to trace: "auto" traces mixtures only, where a flash is slow."""
    if solver not in SOLVERS:
        raise ValueError("Unknown solver '{0}', expected one of {1}.".format(solver, SOLVERS))
    return solver == "tracer" or (solver == "auto" and not fluid.is_pure)


def _inside(metric: Optional[Metric], x: float, y: float) -> bool:
    """Whether a point lies in the area the axes show; everything is inside without a metric."""
    if metric is None:
        return True
    u, v = metric.point(x, y)
    return -EDGE_TOLERANCE <= u <= 1.0 + EDGE_TOLERANCE and -EDGE_TOLERANCE <= v <= 1.0 + EDGE_TOLERANCE


def _two_phase(Q: float) -> Optional[bool]:
    return bool(0.0 <= Q <= 1.0) if np.isfinite(Q) else None


def _metric(fluid: Fluid, diagram: DiagramType, tp_box, ranges) -> Metric:
    """Normalised plot coordinates of the chart, from the given or computed axis ranges."""
    found = {}
    for key in (diagram.x, diagram.y):
        if ranges is not None and key in ranges:
            found[key] = tuple(ranges[key])
        else:
            found[key] = property_range_SI(fluid, key, tp_box)
    return Metric(found[diagram.x], found[diagram.y], diagram.x_log, diagram.y_log)


class _Sweep:
    """The stepped quantity of a line mapped to a parameter u in 0..1

    Pressure is stepped logarithmically, temperature linearly, like the
    axes they are shown on.
    """

    def __init__(self, key: str, lo: float, hi: float):
        self.key = key
        self.lo, self.hi = float(lo), float(hi)
        self.log = get_quantity(key).log_scale and lo > 0.0 and hi > 0.0

    def value(self, u: float) -> float:
        if self.log:
            return self.lo * (self.hi / self.lo) ** u
        return self.lo + (self.hi - self.lo) * u

    def parameter(self, value: float) -> float:
        if self.log:
            return math.log(value / self.lo) / math.log(self.hi / self.lo)
        return (value - self.lo) / (self.hi - self.lo)


class _LineSolver:
    """The states of one isoline: traced with a flash as fallback, or flashed

    ``sample(w)`` computes the state where the stepped quantity equals
    ``w`` and returns it as a :class:`Sample` whose ``extra`` is
    (w, T, p, Q), or None if it cannot be computed.
    """

    def __init__(self, fluid: Fluid, iso_key: str, value_SI: float, sweep_key: str, diagram: DiagramType,
                 metric: Optional[Metric], solver: str):
        self.fluid = fluid
        self.value_SI = value_SI
        self.metric = metric
        iso_index, sweep_index = parameter_index(iso_key), parameter_index(sweep_key)
        # CoolProp expects the two inputs in a fixed order for each input
        # pair. Ask once which order applies; generate_update_pair returns
        # the values in the order the pair needs them, so a zero in first
        # place means the constant goes first.
        self.pair, first, _ = CP.generate_update_pair(iso_index, 0.0, sweep_index, 1.0)
        self.constant_first = (first == 0.0)
        inputs = (iso_index, sweep_index) if self.constant_first else (sweep_index, iso_index)
        self.out = (parameter_index(diagram.x), parameter_index(diagram.y), CoolProp.iT, CoolProp.iP)
        self.tracer = None
        if _use_tracer(fluid, solver) and IsoLineTracer.supports(*inputs):
            try:
                self.tracer = IsoLineTracer(fluid, inputs[0], inputs[1], iso_index)
            except Exception:
                self.tracer = None   # every point is flashed instead
        self.method = "tracer" if self.tracer is not None else "flash"
        self.n_fallback = 0

    def sample(self, w: float, careful: bool = True) -> Optional[Sample]:
        v1, v2 = (self.value_SI, w) if self.constant_first else (w, self.value_SI)
        if self.tracer is not None:
            try:
                self.tracer.update(v1, v2)
                sample = self._sample_of(self.tracer.state, w)
            except Exception:
                sample = None
            if sample is not None:
                return sample
            if not careful:
                return None   # a cheap look while the line is outside the domain
            self.n_fallback += 1
        try:
            # update_pair retries a mixture on the envelope-built scratch state
            # and refuses a state CoolProp got wrong, see Fluid.inconsistency
            state = self.fluid.update_pair(self.pair, v1, v2)
        except Exception:
            return None
        if self.tracer is not None:
            self.tracer.set_guess(state)
        return self._sample_of(state, w)

    def _sample_of(self, state, w: float) -> Optional[Sample]:
        values = [state.keyed_output(k) for k in self.out]
        if not all(np.isfinite(values)):
            return None
        x, y, T_K, p_Pa = values
        return Sample(x, y, _inside(self.metric, x, y), _two_phase(_quality_or_nan(state)),
                      (w, T_K, p_Pa, _quality_or_nan(state), state.rhomass()))


def _saturation_sample(fluid: Fluid, key: str, value_SI: float, quality: float, diagram: DiagramType,
                       metric: Optional[Metric], sweep_key: str) -> Optional[Sample]:
    """The saturation state at T or p = value_SI and the given quality, or None.

    The sample's ``extra`` is (w, T, p, Q, rho) with w its value of ``sweep_key``.
    """
    try:
        state = fluid.update(key, value_SI, "Q", quality)
        if not fluid.is_pure and not _phases_are_distinct(state):
            return None   # the trivial solution of the mixture solver, not a saturation state
        x, y, T_K, p_Pa = (state.keyed_output(parameter_index(k)) for k in (diagram.x, diagram.y, "T", "p"))
    except Exception:
        return None
    if not all(np.isfinite(v) for v in (x, y, T_K, p_Pa)):
        return None
    w = T_K if sweep_key == "T" else p_Pa
    return Sample(x, y, _inside(metric, x, y), True, (w, T_K, p_Pa, quality, state.rhomass()))


def compute_isoline(fluid: Fluid, diagram: DiagramType, iso_key: str, value_SI: float,
                    tp_box: Tuple[float, float, float, float], points: int = 250,
                    solver: str = "auto", margin: float = 1e-7, ranges=None) -> Curve:
    """Compute one line of constant ``iso_key`` in the axes of ``diagram``.

    The isoline quantity is held at ``value_SI`` while temperature or
    pressure (see :meth:`DiagramType.sweep_quantity`) is stepped through
    its range in ``tp_box`` = (T_min_K, T_max_K, p_min_Pa, p_max_Pa), see
    the module docstring. Both axis values are read from each resulting
    state. ``points`` sets the resolution: about the number of points a
    line across the whole chart gets, before its bends add more.

    ``solver`` is "flash" (one CoolProp flash per point), "tracer" (walk
    along the line, see :mod:`coolplot.thermo.tracer`, with a flash for
    every point the tracer refuses) or "auto" (tracer for mixtures only).
    ``ranges`` maps the two axis quantities to their (min, max) over the
    box, in SI units; without it they are computed from the box corners.
    Lines of constant quality are delegated to :func:`compute_quality_line`.
    """
    iso_key = quantity_key(iso_key)
    if iso_key == "Q":
        return compute_quality_line(fluid, diagram, value_SI, points, margin)
    sweep_key = diagram.sweep_quantity(iso_key)
    if sweep_key is None:
        raise ValueError("Lines of constant '{0}' cannot be drawn in a {1} diagram.".format(
            iso_key, diagram.name))
    return _build_line(fluid, diagram, iso_key, value_SI, tp_box, points, solver, ranges).curve()


def _build_line(fluid, diagram, iso_key, value_SI, tp_box, points, solver, ranges=None) -> "_Line":
    """The assembled line with its samples (T, p, Q, rho per point); the sweep tests check those."""
    sweep_key = diagram.sweep_quantity(iso_key)
    T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa = tp_box
    sweep = _Sweep(sweep_key, *((T_lo_K, T_hi_K) if sweep_key == "T" else (p_lo_Pa, p_hi_Pa)))
    metric = _metric(fluid, diagram, tp_box, ranges)
    solver_ = _LineSolver(fluid, iso_key, value_SI, sweep_key, diagram, metric, solver)
    line = _Line(fluid, diagram, iso_key, value_SI, sweep, metric, points, solver_)
    if iso_key in ("T", "p"):
        line.through_the_dome()
    else:
        line.across_the_dome()
    return line


class _Line:
    """Assembles one isoline from traced parts, see :func:`compute_isoline`."""

    def __init__(self, fluid, diagram, iso_key, value_SI, sweep, metric, points, solver):
        self.fluid, self.diagram = fluid, diagram
        self.iso_key, self.value_SI = iso_key, value_SI
        self.sweep, self.metric, self.points = sweep, metric, points
        self.solver = solver
        self.samples: List[Optional[Sample]] = []   # None marks a gap
        self.n_inserted = 0
        self.n_evaluated = self.n_outside = self.n_failed = 0
        self.stopped = ""   # why a part ended before the end of its range, if it did

    # Parts -------------------------------------------------------------
    def _evaluate(self, u: float, careful: bool) -> Optional[Sample]:
        return self.solver.sample(self.sweep.value(u), careful)

    def _part(self, u_lo: float, u_hi: float, start: Sample = None, end: Sample = None):
        """Step the single-phase part of the line between two parameters and keep its points."""
        if u_hi <= u_lo:
            return
        found = trace(self._evaluate, self.metric, self.points, u_lo, u_hi, start, end)
        self._count(found)
        self._extend(found.samples)

    def _count(self, found):
        self.n_evaluated += found.n_evaluated
        self.n_outside += found.n_outside
        self.n_failed += found.n_failed
        if found.stopped and not found.stopped.startswith("the end of the range"):
            self.stopped = found.stopped   # the line was cut short; the curve says so

    def _extend(self, samples):
        for sample in samples:
            if sample is not None and self.samples and self.samples[-1] is sample:
                continue   # the end of one part is the start of the next
            if sample is None and (not self.samples or self.samples[-1] is None):
                continue
            self.samples.append(sample)

    def through_the_dome(self):
        """An isotherm or isobar: single phase up to the dome, stepped in quality inside, single phase beyond."""
        dome = self._dome_interval()
        if dome is None:
            return self._part(0.0, 1.0)
        (w_a, q_a, sample_a), (w_b, q_b, sample_b) = dome
        u_a = min(max(self.sweep.parameter(w_a), 0.0), 1.0)
        u_b = min(max(self.sweep.parameter(w_b), 0.0), 1.0)
        if w_b < self.sweep.lo or w_a > self.sweep.hi:
            return self._part(0.0, 1.0)   # the dome lies outside the stepped range
        self._part(0.0, u_a, end=self._in_sweep_range(sample_a))
        self._quality_branch(q_a, sample_a, q_b, sample_b)
        self._part(u_b, 1.0, start=self._in_sweep_range(sample_b))

    def _in_sweep_range(self, sample: Optional[Sample]) -> Optional[Sample]:
        """The sample marked outside when its stepped quantity lies beyond the range of the T-p box.

        The dome part of an isobar in an h-s chart runs in temperature,
        which is no axis there; the box's temperature limits still apply.
        """
        if sample is None or self.sweep.lo <= sample.extra[0] <= self.sweep.hi:
            return sample
        return replace(sample, inside=False)

    def _dome_interval(self):
        """((w, Q, sample), (w, Q, sample)) of the saturation states the line meets, in order of w, or None.

        For a pure fluid both lie at the same temperature or pressure. A
        mixture's bubble and dew states come from the saturation solver,
        or from the phase envelope where that solver fails (near the
        critical point).
        """
        if not self.fluid.has_critical_point:
            return None
        ends = []
        for q in (0.0, 1.0):
            sample = _saturation_sample(self.fluid, self.iso_key, self.value_SI, q, self.diagram, self.metric,
                                        self.sweep.key)
            self.n_evaluated += 1
            if sample is not None:
                self.n_outside += 0 if sample.inside else 1
                ends.append((sample.extra[0], q, sample))
        if len(ends) < 2:
            ends = self._envelope_ends()
        if len(ends) != 2:
            return None
        ends.sort(key=lambda end: (end[0], end[1] if self.sweep.key == "T" else -end[1]))
        return ends[0], ends[1]

    def _envelope_ends(self):
        """Bubble and dew states of a mixture isotherm or isobar, interpolated on the phase envelope."""
        envelope = self.fluid.phase_envelope()
        if envelope is None:
            return []
        found = {}
        for w, q, sample in _envelope_crossings(envelope, self.diagram, self.iso_key, self.value_SI,
                                                self.sweep.key, self.metric):
            found.setdefault(q, (w, q, sample))
        return [found[q] for q in (0.0, 1.0) if q in found]

    def _quality_branch(self, q_a: float, sample_a: Sample, q_b: float, sample_b: Sample):
        """The part of an isotherm or isobar inside the dome, stepped in vapour quality."""
        def evaluate(u, careful):
            q = q_a + (q_b - q_a) * u
            return self._in_sweep_range(_saturation_sample(self.fluid, self.iso_key, self.value_SI, q, self.diagram,
                                                           self.metric, self.sweep.key))
        sample_a, sample_b = self._in_sweep_range(sample_a), self._in_sweep_range(sample_b)
        found = trace(evaluate, self.metric, self.points, 0.0, 1.0, sample_a, sample_b, skip_failures=True)
        self._count(found)
        self.n_inserted += sum(1 for s in found.samples if s is sample_a or s is sample_b)
        self._extend(found.samples)

    def across_the_dome(self):
        """Any other line: stepped straight through, with the saturation states inserted where the phase changes."""
        self._part(0.0, 1.0)
        if not self.fluid.has_critical_point:
            return
        envelope = self.fluid.phase_envelope()
        if envelope is not None:
            crossings = _envelope_crossings(envelope, self.diagram, self.iso_key, self.value_SI, self.sweep.key,
                                            self.metric, (self.sweep.lo, self.sweep.hi))
            self._merge(crossings)
        else:
            self._insert_pure_crossings()

    def _insert_pure_crossings(self):
        """Solve for the saturation state between two points of different phase and insert it."""
        merged: List[Optional[Sample]] = []
        for i, sample in enumerate(self.samples):
            merged.append(sample)
            after = self.samples[i + 1] if i + 1 < len(self.samples) else None
            if sample is None or after is None or sample.two_phase is None or after.two_phase is None \
                    or sample.two_phase == after.two_phase:
                continue
            q_inside = sample.extra[3] if sample.two_phase else after.extra[3]
            # Try the nearer saturation line first; the other one if that fails
            for q in sorted((0.0, 1.0), key=lambda b: abs(b - q_inside)):
                crossing = _solve_crossing(self.fluid, self.diagram, self.iso_key, self.value_SI, self.sweep.key,
                                           sample.extra[0], after.extra[0], q, self.metric)
                if crossing is not None:
                    merged.append(crossing[2])
                    self.n_inserted += 1
                    break
        self.samples = merged

    def _merge(self, crossings):
        """Insert saturation states by their value of the stepped quantity.

        A crossing interpolated on the phase envelope is accurate to about
        1e-5 of the property, a hundredth of a line width; where the
        saturation solver answers it is refined to the exact state between
        the two neighbouring points of the line.
        """
        for w, q, crossing in sorted(crossings, key=lambda c: c[0]):
            position = len(self.samples)
            for i, sample in enumerate(self.samples):
                if sample is not None and sample.extra[0] > w:
                    position = i
                    break
            before = self.samples[position - 1] if position > 0 else None
            after = self.samples[position] if position < len(self.samples) else None
            if before is not None and after is not None:
                exact = _solve_crossing(self.fluid, self.diagram, self.iso_key, self.value_SI, self.sweep.key,
                                        before.extra[0], after.extra[0], q, self.metric)
                if exact is not None:
                    crossing = exact[2]
            self.samples.insert(position, crossing)
            self.n_inserted += 1

    # Result --------------------------------------------------------------
    def curve(self) -> Curve:
        while self.samples and self.samples[-1] is None:
            self.samples.pop()
        x = np.array([np.nan if s is None else s.x for s in self.samples], dtype=float)
        y = np.array([np.nan if s is None else s.y for s in self.samples], dtype=float)
        reason = self.stopped
        if len(self.samples) < 2 and self.n_failed == 0 and self.n_outside > 0:
            x_lo, x_hi = self.metric.x_range
            y_lo, y_hi = self.metric.y_range
            area = "{0} = {1:.6g}..{2:.6g}, {3} = {4:.6g}..{5:.6g} (SI)".format(
                self.diagram.x, x_lo, x_hi, self.diagram.y, y_lo, y_hi)
            reason = "{0} point(s) of the line lie in the area the axes show, {1}".format(len(self.samples), area)
        return Curve(x, y, self.n_failed, self.solver.n_fallback, self.n_inserted, self.solver.method, reason,
                     self.n_evaluated, self.n_outside)


# ---------------------------------------------------------------------------
# Saturation states on an isoline
# ---------------------------------------------------------------------------
def _saturation_state(fluid: Fluid, sat_key: str, sat_value: float, quality: float, diagram: DiagramType,
                      iso_key: str):
    """(iso value, x, y, T, p, rho) of the saturation state at T or p = sat_value, or None.

    Through :meth:`Fluid.update`, which retries a mixture on the scratch
    state with the phase envelope built; a mixture's trivial solution
    (both phases at one density) is refused.
    """
    try:
        state = fluid.update(sat_key, sat_value, "Q", quality)
        if not fluid.is_pure and not _phases_are_distinct(state):
            return None
        result = tuple(state.keyed_output(parameter_index(k))
                       for k in (iso_key, diagram.x, diagram.y, "T", "p", "rho"))
    except Exception:
        return None
    return result if all(np.isfinite(result)) else None


def _solve_crossing(fluid, diagram, iso_key, value_SI, sweep_key, a, b, quality, metric):
    """Sweep value in [a, b] where the saturation state has iso_key == value_SI.

    Regula falsi with the Illinois modification, which converges quickly
    and never leaves the bracket. Returns (sweep value, quality, Sample)
    or None.
    """
    ends = [_saturation_state(fluid, sweep_key, v, quality, diagram, iso_key) for v in (a, b)]
    if None in ends:
        return None

    def result(w, found):
        return (w, quality, Sample(found[1], found[2], _inside(metric, found[1], found[2]), None,
                                   (w, found[3], found[4], quality, found[5])))
    fa, fb = ends[0][0] - value_SI, ends[1][0] - value_SI
    if fa == 0.0:
        return result(a, ends[0])
    if fb == 0.0:
        return result(b, ends[1])
    if fa * fb > 0.0:
        return None
    found = None
    for _ in range(60):
        c = b - fb * (b - a) / (fb - fa)
        state = _saturation_state(fluid, sweep_key, c, quality, diagram, iso_key)
        if state is None:
            return None
        fc = state[0] - value_SI
        found = result(c, state)
        if fc == 0.0 or abs(b - a) <= 1e-12 * abs(c):
            break
        if fc * fb < 0.0:
            a, fa = b, fb
        else:
            fa *= 0.5
        b, fb = c, fc
        if abs(fc) <= 1e-10 * max(abs(value_SI), 1.0):
            break
    return found


def _envelope_crossings(envelope, diagram, iso_key, value_SI, sweep_key, metric, sweep_range=None):
    """Where an isoline crosses the phase envelope of a mixture.

    The envelope has about 300 closely spaced points. Between two
    neighbours where the isoline quantity passes ``value_SI`` the crossing
    is interpolated linearly, which is accurate to well below the line
    width. Returns (sweep value, quality, Sample) triples; with
    ``sweep_range`` only crossings inside that range of the stepped
    quantity.
    """
    k = envelope.values(iso_key)
    columns = [envelope.values(key) for key in (sweep_key, diagram.x, diagram.y, "T", "p", "rho")]
    found = []
    f = k - value_SI
    for i in range(len(f) - 1):
        a, b = f[i], f[i + 1]
        if not (np.isfinite(a) and np.isfinite(b)) or a * b > 0.0 or a == b:
            continue
        if b == 0.0 and i + 1 < len(f) - 1:
            continue   # an exact hit on a point is counted once, by the next pair
        t = a / (a - b)
        w, x, y, T_K, p_Pa, rho = [v[i] + t * (v[i + 1] - v[i]) for v in columns]
        if not all(np.isfinite((w, x, y, T_K, p_Pa, rho))):
            continue
        if sweep_range is not None and not sweep_range[0] <= w <= sweep_range[1]:
            continue
        quality = envelope.Q[i] if t < 0.5 else envelope.Q[i + 1]
        found.append((w, quality, Sample(x, y, _inside(metric, x, y), None, (w, T_K, p_Pa, quality, rho))))
    return found


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
    envelope (about 300), independent of ``points``. A mixture's line of
    intermediate quality runs up to the hottest point of the envelope
    (the critical point, or for a blend with a wide glide the
    cricondentherm a few hundredths of a kelvin above it), which is
    appended as its last point so that it meets the dome there.
    """
    if not 0.0 <= quality <= 1.0:
        raise ValueError("The vapour quality has to be between 0 and 1, not {0}.".format(quality))
    fluid = _base_backend_fluid(fluid)
    if not fluid.has_critical_point:
        raise ValueError("{0} has no two-phase region (CoolProp provides no critical point for it), so lines of "
                         "constant quality cannot be drawn.".format(fluid.name))
    if not fluid.is_pure:
        if quality in (0.0, 1.0):
            curve = _envelope_line(fluid, diagram, quality)
            if curve is not None:
                return curve
        envelope = fluid.phase_envelope()
        if envelope is not None and envelope.closed:
            return _mixture_quality_line(fluid, diagram, quality, points, margin, envelope)
    T_lo_K, T_hi_K = fluid.saturation_range("T", margin)
    T_K = T_lo_K + (T_hi_K - T_lo_K) * _saturation_grid(points, spacing)
    x, y, n_failed = _saturation_states(fluid, diagram, quality, T_K)
    if fluid.is_pure:
        crit = fluid.critical
        x_crit, y_crit = crit.get(diagram.x, np.nan), crit.get(diagram.y, np.nan)
        if np.isfinite(x_crit) and np.isfinite(y_crit):
            x = np.append(x, x_crit)
            y = np.append(y, y_crit)
    return Curve(x, y, n_failed, n_evaluated=len(T_K))


def _saturation_grid(points: int, spacing: str) -> np.ndarray:
    """Positions 0..1 of the temperatures of a quality line, denser towards 1 with "critical" spacing."""
    u = np.linspace(0.0, 1.0, points)
    if spacing == "critical":
        return 1.0 - (1.0 - u) ** 2
    if spacing != "linear":
        raise ValueError("Unknown saturation spacing '{0}'.".format(spacing))
    return u


def _saturation_states(fluid: Fluid, diagram: DiagramType, quality: float, T_K: np.ndarray):
    """(x, y, n_failed) of the saturation states at the given temperatures and quality."""
    x_index = parameter_index(diagram.x)
    y_index = parameter_index(diagram.y)
    x = np.full_like(T_K, np.nan)
    y = np.full_like(T_K, np.nan)
    n_failed = 0
    for i, T in enumerate(T_K):
        try:
            # update() retries a mixture on the envelope-built scratch state
            state = fluid.update("T", T, "Q", quality)
            if not fluid.is_pure and not _phases_are_distinct(state):
                raise ValueError("trivial solution")
            x[i] = state.keyed_output(x_index)
            y[i] = state.keyed_output(y_index)
        except Exception:
            n_failed += 1
    return x, y, n_failed


def _mixture_quality_line(fluid: Fluid, diagram: DiagramType, quality: float, points: int, margin: float,
                          envelope) -> Curve:
    """A line of intermediate quality of a mixture, stepped in temperature up to the top of the envelope.

    The saturation solver fails now and then in the last kelvins below
    the critical point; such a point is left out rather than left as a
    gap, and the line ends at the top of the envelope, which is the
    critical point of a closed envelope.
    """
    T_lo_K = fluid.saturation_range("T", margin)[0]
    T_hi_K = envelope.top("T")
    # The steps are measured against the extent of the dome itself; every
    # saturation state up to the top is part of the line (no metric to clip by)
    ranges = {}
    for key in (diagram.x, diagram.y):
        values = envelope.values(key)
        ranges[key] = (float(np.nanmin(values)), float(np.nanmax(values)))
        if not ranges[key][0] < ranges[key][1]:
            ranges[key] = (ranges[key][0] - 1.0, ranges[key][0] + 1.0)
    metric = Metric(ranges[diagram.x], ranges[diagram.y], diagram.x_log, diagram.y_log)
    top = Sample(envelope.top(diagram.x), envelope.top(diagram.y), True, True,
                 (T_hi_K, T_hi_K, envelope.top("p"), quality))

    def evaluate(u, careful):
        return _saturation_sample(fluid, "T", T_lo_K + (T_hi_K - T_lo_K) * u, quality, diagram, None, "T")
    found = trace(evaluate, metric, points, 0.0, 1.0, end=top, skip_failures=True)
    x = np.array([np.nan if s is None else s.x for s in found.samples], dtype=float)
    y = np.array([np.nan if s is None else s.y for s in found.samples], dtype=float)
    stopped = "" if found.stopped.startswith("the end of the range") else found.stopped
    return Curve(x, y, found.n_failed, reason=stopped, n_evaluated=found.n_evaluated)


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
