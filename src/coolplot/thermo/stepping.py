# -*- coding: utf-8 -*-
"""Walking along a line with steps chosen from its shape on the page.

A line of constant property is a curve; what matters for drawing it is
how it looks in the axes of the chart. :func:`trace` steps a parameter
(temperature, pressure or vapour quality) from one end of its range to
the other and picks every step so that the drawn segment stays short
and the line does not turn by much between two points. Straight parts
are covered in few steps, bends get more. Points are measured in
*normalised plot coordinates*: each axis range maps to 0..1, with the
logarithm taken for log axes, so a step of 0.01 is one percent of the
chart whatever the units.

Steps also stop at the calculation domain (the T-p box of the chart):
where the line leaves it, the exit point is found by bisection and the
line continues, outside, with large steps only to see whether it comes
back. No point is computed outside the box that is not needed to find
where the line enters or leaves it.

This module knows nothing about fluids. The caller supplies an
``evaluate(u, careful)`` function that returns a :class:`Sample` or None
when the point cannot be computed; ``careful`` is False while the walk
only looks for the line outside the box, where a cheap attempt is enough.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


@dataclass(frozen=True)
class Metric:
    """Normalised plot coordinates: the axis ranges of a chart mapped to 0..1

    ``x_range`` and ``y_range`` are (low, high) in SI units; ``x_log`` and
    ``y_log`` say whether the axis is logarithmic. A log axis with a
    non-positive range is treated as linear.
    """
    x_range: Tuple[float, float]
    y_range: Tuple[float, float]
    x_log: bool = False
    y_log: bool = False

    @staticmethod
    def _scale(value: float, lo: float, hi: float, log: bool) -> float:
        if log and lo > 0.0 and hi > 0.0 and value > 0.0:
            return (math.log10(value) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
        return (value - lo) / (hi - lo)

    def point(self, x: float, y: float) -> Tuple[float, float]:
        """(x, y) in SI units as a point of the unit square (or beyond it)."""
        return (self._scale(x, self.x_range[0], self.x_range[1], self.x_log),
                self._scale(y, self.y_range[0], self.y_range[1], self.y_log))


@dataclass(frozen=True)
class Sample:
    """One computed point of a line

    ``x`` and ``y`` are the axis values in SI units, ``inside`` whether the
    state lies in the calculation domain, ``two_phase`` whether it lies in
    the two-phase region (None if unknown). ``extra`` is whatever the
    caller wants to keep with the point, for example the state's T and p.
    """
    x: float
    y: float
    inside: bool = True
    two_phase: Optional[bool] = None
    extra: tuple = ()


@dataclass
class Trace:
    """What :func:`trace` found: the accepted points in order of the parameter

    A None in ``samples`` marks a gap: the line left the domain, or could
    not be computed, between the points on either side of it.
    """
    u: List[float] = field(default_factory=list)
    samples: List[Optional[Sample]] = field(default_factory=list)
    n_evaluated: int = 0
    n_outside: int = 0
    n_failed: int = 0
    stopped: str = ""

    def add(self, u: float, sample: Optional[Sample]):
        """Append an accepted point, or a gap marker (None) unless one is there already."""
        if sample is None and (not self.samples or self.samples[-1] is None):
            return   # one gap marker is enough, and never one at the start
        self.u.append(u)
        self.samples.append(sample)

    def close(self):
        """Drop a trailing gap marker."""
        while self.samples and self.samples[-1] is None:
            self.u.pop()
            self.samples.pop()


#: Largest turn between two consecutive segments, in degrees. A full
#: circle drawn with this turn per segment has 72 segments.
MAX_ANGLE_DEG = 5.0
#: Longest step as a multiple of 1/points, in normalised plot coordinates:
#: a straight line across the chart gets about points / STEP_FACTOR points,
#: bends get more from the angle rule.
STEP_FACTOR = 2.5
#: The parameter is never stepped by less than this fraction of its range:
#: a kink is located to this resolution, which is far below a pixel.
MIN_STEP = 1e-4
#: Nor by more than this fraction.
MAX_STEP = 1.0 / 8.0
#: While the line is outside the domain the step starts at this fraction
#: of the range and doubles at every point up to SCAN_MAX, so that a long
#: outside stretch costs a handful of points. A stretch inside the domain
#: shorter than SCAN_MAX can be missed while scanning; a chart whose axes
#: are the ranges of the domain gives no line that leaves and comes back.
SCAN_STEP = 1.0 / 64.0
SCAN_MAX = 1.0 / 32.0
#: A domain edge is located to this fraction of the parameter range.
EDGE_TOLERANCE = 1e-3


def trace(evaluate: Callable, metric: Metric, points: int, u_lo: float = 0.0, u_hi: float = 1.0,
          start: Sample = None, end: Sample = None, max_angle_deg: float = MAX_ANGLE_DEG,
          skip_failures: bool = False) -> Trace:
    """Walk the parameter from ``u_lo`` to ``u_hi``, see the module docstring.

    ``points`` sets the resolution: the number of points a straight line
    across the whole chart gets, before bends add more. ``start`` and
    ``end`` are the samples at the two ends when the caller knows them
    (saturation states, for example); they are used instead of evaluating
    there. A point that cannot be computed normally ends the piece with a
    gap, after the walk has closed in on where the failures begin; with
    ``skip_failures`` it is simply left out, for a line whose ends are
    known to be joined (the part of an isobar inside the dome, say). At
    most about eight times ``points`` evaluations are made.
    """
    walk = _Walk(evaluate, metric, points, u_lo, u_hi, start, end, max_angle_deg, skip_failures)
    walk.run()
    return walk.trace


class _Walk:
    """The state of one call to :func:`trace`"""

    def __init__(self, evaluate, metric, points, u_lo, u_hi, start, end, max_angle_deg, skip_failures):
        self.evaluate = evaluate
        self.skip_failures = skip_failures
        self.metric = metric
        self.u_lo, self.u_hi = float(u_lo), float(u_hi)
        self.span = self.u_hi - self.u_lo
        self.start, self.end = start, end
        self.points = max(int(points), 2)
        self.max_length = STEP_FACTOR / self.points
        self.max_angle = float(max_angle_deg)
        self.max_cos = math.cos(math.radians(max_angle_deg))
        self.budget = 8 * self.points + 100
        self.trace = Trace()
        self.previous = None        # (u, sample, normalised point) of the last accepted point inside
        self.direction = None       # unit vector of the last accepted segment
        self.last_length = 0.0      # of the last accepted step, normalised
        self.last_turn = 0.0        # cosine of the turn at the last accepted point
        self.last_outside_u = None  # where the line was last seen outside (scan mode)

    # Evaluation --------------------------------------------------------
    def sample_at(self, u: float, careful: bool = True) -> Optional[Sample]:
        """The sample at ``u``: a known end, or one evaluation."""
        if self.start is not None and u == self.u_lo:
            return self.start
        if self.end is not None and u == self.u_hi:
            return self.end
        self.trace.n_evaluated += 1
        sample = self.evaluate(u, careful)
        if sample is None:
            if careful:
                self.trace.n_failed += 1
            else:
                self.trace.n_outside += 1   # a cheap look that found nothing, while the line is outside
        elif not sample.inside:
            self.trace.n_outside += 1
        return sample

    def over_budget(self) -> bool:
        if self.trace.n_evaluated < self.budget:
            return False
        self.trace.stopped = "the evaluation budget of {0} points is used up".format(self.budget)
        return True

    # Geometry ----------------------------------------------------------
    def normalised(self, sample: Sample) -> Tuple[float, float]:
        return self.metric.point(sample.x, sample.y)

    def step_ok(self, point, sample: Sample) -> bool:
        """Whether a step from the previous point to this one is short and straight enough."""
        if self.previous is None:
            return True
        px, py = self.previous[2]
        dx, dy = point[0] - px, point[1] - py
        length = math.hypot(dx, dy)
        if not math.isfinite(length):
            return False
        if length > self.max_length:
            return False
        if self.direction is None or length < 1e-12:
            return True
        if self.previous[1].two_phase is not None and sample.two_phase is not None \
                and sample.two_phase != self.previous[1].two_phase:
            return True   # the line crosses the phase boundary: a real kink, not a bad step
        cos = (dx * self.direction[0] + dy * self.direction[1]) / length
        return cos >= self.max_cos

    def accept(self, u: float, sample: Sample, point):
        self.last_length, self.last_turn = 0.0, 1.0
        if self.previous is not None:
            px, py = self.previous[2]
            length = math.hypot(point[0] - px, point[1] - py)
            if length > 1e-12:
                direction = ((point[0] - px) / length, (point[1] - py) / length)
                if self.direction is not None:
                    self.last_turn = direction[0] * self.direction[0] + direction[1] * self.direction[1]
                self.direction = direction
                self.last_length = length
        self.previous = (u, sample, point)
        self.trace.add(u, sample)

    # The walk ----------------------------------------------------------
    def run(self):
        """Alternate between fine steps inside the domain and scanning outside until the end."""
        u = self.u_lo
        sample = self.sample_at(u)
        inside = sample is not None and sample.inside
        if inside:
            self.accept(u, sample, self.normalised(sample))
        else:
            self.last_outside_u = u
        while u < self.u_hi and not self.over_budget():
            u, inside = self.walk_inside(u) if inside else self.scan_outside(u)
        if u >= self.u_hi and not self.trace.stopped:
            self.trace.stopped = "the end of the range"
        self.trace.close()

    def walk_inside(self, u: float):
        """Fine steps while the line is inside the domain; returns (u, whether still inside)."""
        du = self.span / self.points
        min_du = self.span * MIN_STEP
        while u < self.u_hi and not self.over_budget():
            u_try = min(u + du, self.u_hi)
            sample = self.sample_at(u_try)
            if sample is None:
                if self.skip_failures:
                    # Leave the point out; a stretch of failures is crossed
                    # in growing steps, so it costs a handful of points
                    u = u_try
                    du = min(du * 2.0, self.span * MAX_STEP)
                    continue
                if du > min_du:
                    du *= 0.5
                    continue
                # Cannot get past this point: leave a gap and look further on
                self.trace.add(u_try, None)
                self.last_outside_u = u_try
                return u_try, False
            if not sample.inside:
                self.leave_domain(u, u_try)
                return u_try, False
            point = self.normalised(sample)
            if not self.step_ok(point, sample) and du > min_du:
                du *= 0.5
                continue
            self.accept(u_try, sample, point)
            u = u_try
            du = self.next_step(du)
        return u, True

    def next_step(self, du: float) -> float:
        """The step to try next: aimed at four fifths of the longest and sharpest allowed

        A step that would be rejected costs an evaluation, so the step is
        shrunk ahead of a bend and grown only moderately on a straight.
        """
        factor = 1.5
        if self.last_length > 0.0:
            factor = min(factor, 0.8 * self.max_length / self.last_length)
        turn = math.degrees(math.acos(min(max(self.last_turn, -1.0), 1.0)))
        if turn > 0.0:
            factor = min(factor, 0.8 * self.max_angle / turn)
        return min(max(du * factor, du * 0.25), self.span * MAX_STEP)

    def leave_domain(self, u_in: float, u_out: float):
        """The line left the domain between u_in and u_out: put its last point on the edge."""
        u_edge, sample = self.bisect_edge(u_in, u_out)
        if sample is not None:
            self.accept(u_edge, sample, self.normalised(sample))
        self.trace.add(u_out, None)
        self.last_outside_u = u_out

    def bisect_edge(self, u_in: float, u_out: float):
        """(u, sample) of the last point inside between an inside and an outside parameter."""
        found = None
        tolerance = self.span * EDGE_TOLERANCE
        while abs(u_out - u_in) > tolerance and not self.over_budget():
            u_mid = 0.5 * (u_in + u_out)
            sample = self.sample_at(u_mid)
            if sample is not None and sample.inside:
                u_in, found = u_mid, sample
            else:
                u_out = u_mid
        return u_in, found

    def scan_outside(self, u: float):
        """Growing steps while the line is outside the domain or cannot be computed; returns (u, inside)."""
        du = self.span * SCAN_STEP
        while u < self.u_hi and not self.over_budget():
            u_try = min(u + du, self.u_hi)
            sample = self.sample_at(u_try, careful=False)
            if sample is not None and sample.inside:
                self.enter_domain(u, u_try, sample)
                return u_try, True
            u = u_try
            du = min(du * 2.0, self.span * SCAN_MAX)
        return u, False

    def enter_domain(self, u_out: float, u_in: float, sample: Sample):
        """The line came back between u_out and u_in: start the piece on the edge."""
        self.previous = None
        self.direction = None
        u_edge, edge_sample = self.bisect_edge(u_in, u_out)
        if edge_sample is not None and u_edge != u_in:
            self.accept(u_edge, edge_sample, self.normalised(edge_sample))
        self.accept(u_in, sample, self.normalised(sample))
