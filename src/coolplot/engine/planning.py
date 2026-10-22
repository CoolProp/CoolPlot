# -*- coding: utf-8 -*-
"""Which curves a diagram needs, decided without any property calculation.

:func:`plan` reads a :class:`coolplot.spec.DiagramSpec` and the calculation
:class:`Domain` and lists one :class:`CurveRequest` per isoline. It is a
pure function: the same inputs always give the same requests, which makes
the choice of isoline values easy to test and lets an application inspect
what would be computed before anything is computed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from ..core.floats import same_number
from ..core.quantities import get_quantity
from ..spec.diagram import DiagramSpec, IsolineSet, SaturationAnchor

# Mantissas for round values on a logarithmic scale, from coarse to fine.
# For each family the set whose number of values is closest to the
# requested number is used.
_LOG_MANTISSAS = (
    (1.0,),
    (1.0, 2.0, 5.0),
    (1.0, 1.5, 2.0, 3.0, 5.0, 7.0),
    (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0),
)

# Round steps on a linear scale: 1, 2, 2.5 or 5 times a power of ten.
_LINEAR_STEPS = (1.0, 2.0, 2.5, 5.0, 10.0)


@dataclass(frozen=True)
class Domain:
    """The calculation region of a diagram in SI units

    ``tp_box`` is (T_min_K, T_max_K, p_min_Pa, p_max_Pa). ``ranges_SI``
    holds (min, max) of every quantity over that region, as pairs
    (key, (min, max)) so the value stays hashable. ``anchored`` holds the
    values of the families placed by saturation states, as pairs
    ((key, SaturationAnchor), ((saturation_SI, value_SI), ...)); the
    engine computes them with the region, because they need property calls
    and :func:`plan` makes none. ``saturation`` says whether the chart has a
    saturation curve at all (humid air, or a fluid with a critical point;
    not an incompressible liquid).
    """
    tp_box: Tuple[float, float, float, float]
    ranges_SI: Tuple[Tuple[str, Tuple[float, float]], ...]
    anchored: Tuple[Tuple[Tuple[str, SaturationAnchor], Tuple[Tuple[float, float], ...]], ...] = ()
    saturation: bool = False

    def range_SI(self, key: str) -> Tuple[float, float]:
        """(min, max) of quantity ``key`` over the region, in SI units."""
        ranges = dict(self.ranges_SI)
        if key not in ranges:
            raise ValueError("The range of '{0}' could not be determined for this fluid; "
                             "give the isoline values or a range explicitly.".format(key))
        return ranges[key]

    def anchor_pairs(self, key: str, anchor: SaturationAnchor) -> Tuple[Tuple[float, float], ...]:
        """(saturation value, line value) of every line of the family ``key`` placed by ``anchor``, in SI units."""
        for (k, a), pairs in self.anchored:
            if k == key and a == anchor:
                return pairs
        raise ValueError("The calculation region has no values for the lines of constant '{0}' placed by "
                         "saturation states; it was made for another spec.".format(key))


@dataclass(frozen=True)
class CurveRequest:
    """One isoline to compute: constant ``key`` at ``value_SI`` with ``points`` points

    ``anchor_SI`` is the saturation temperature or pressure the line passes
    through when its family is placed by saturation states, else None.
    """
    item_id: str
    key: str
    value_SI: float
    points: int
    labels: bool = False
    anchor_SI: Optional[float] = None


def snap(value: float) -> float:
    """Round to 12 significant digits.

    Values converted from display units carry rounding noise, e.g. -20 deg C
    becomes 253.14999999999998 K. Snapping makes such values identical to
    the intended 253.15 K, so that they get the same item id and the same
    cache entry, and duplicates are recognised.
    """
    return float("{0:.12g}".format(value))


def isoline_id(key: str, value_SI: float) -> str:
    """Stable item id of an isoline, independent of units and styles.

    The value is snapped to 12 significant digits first (see :func:`snap`),
    so two values that get the same id are the same isoline.
    """
    return "iso/{0}/{1:.12g}".format(key, snap(value_SI))


def linear_grid(lo: float, hi: float, num: int) -> np.ndarray:
    """``num`` evenly spaced values from lo to hi."""
    return np.linspace(lo, hi, num) if num > 1 else np.array([0.5 * (lo + hi)])


def log_grid(lo: float, hi: float, num: int) -> np.ndarray:
    """``num`` values from lo to hi with a constant ratio between neighbours."""
    return np.geomspace(lo, hi, num) if num > 1 else np.array([math.sqrt(lo * hi)])


def nice_linear(lo: float, hi: float, num: int) -> np.ndarray:
    """Round values with a constant step of 1, 2, 2.5 or 5 times a power of ten.

    The step is chosen so that about ``num`` values fall between lo and hi;
    all values are whole multiples of the step, e.g. -20, -10, 0, 10.
    """
    if not (math.isfinite(lo) and math.isfinite(hi)):
        raise ValueError("Cannot round values over the range ({0}, {1}).".format(lo, hi))
    if not hi > lo:
        return np.array([lo])
    raw = (hi - lo) / max(num - 1, 1)
    power = 10.0 ** math.floor(math.log10(raw))
    # Pick the round step closest to the raw step on a log scale
    step = min((m * power for m in _LINEAR_STEPS), key=lambda s: abs(math.log(s / raw)))
    first, last = math.ceil(lo / step - 1e-9), math.floor(hi / step + 1e-9)
    values = np.arange(first, last + 1) * step
    decimals = max(0, -int(math.floor(math.log10(step))) + 1)
    return np.round(values, decimals)


def nice_log(lo: float, hi: float, num: int) -> np.ndarray:
    """Round values m * 10^k, with the mantissa set giving about ``num`` values.

    For example 1, 2, 5, 10, 20, 50 bar, or 1, 1.5, 2, 3, 5, 7, 10 bar for
    denser lines. The spacing looks even on a logarithmic axis.
    """
    if not (hi > lo > 0.0):
        return nice_linear(lo, hi, num)
    candidates = [_log_values(mantissas, lo, hi) for mantissas in _LOG_MANTISSAS]
    candidates = [values for values in candidates if len(values)]
    if not candidates:
        return nice_linear(lo, hi, num)   # a range narrower than the finest mantissa step
    return min(candidates, key=lambda values: abs(len(values) - num))


def _log_values(mantissas, lo: float, hi: float) -> np.ndarray:
    """m * 10^k for the mantissas and every decade from lo to hi, inside the range."""
    k_lo, k_hi = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
    values = [float("{0:.6g}".format(m * 10.0 ** k)) for k in range(k_lo, k_hi + 1) for m in mantissas]
    return np.array(sorted(v for v in values if lo * (1 - 1e-9) <= v <= hi * (1 + 1e-9)))


def isoline_values_SI(spec: DiagramSpec, iso_set: IsolineSet, domain: Domain) -> np.ndarray:
    """The constant values of one family in SI units, snapped and without duplicates."""
    key = iso_set.key
    if iso_set.values_SI is not None:
        values = np.asarray(iso_set.values_SI, dtype=float)
    elif iso_set.anchor is not None:
        values = np.asarray([v for _, v in domain.anchor_pairs(key, iso_set.anchor)], dtype=float)
    else:
        lo, hi = iso_set.range_SI or domain.range_SI(key)
        log = get_quantity(key).log_scale and lo > 0.0
        if iso_set.rounding:
            values = _round_values(spec.units[key], lo, hi, iso_set.num, log)
        else:
            values = log_grid(lo, hi, iso_set.num) if log else linear_grid(lo, hi, iso_set.num)
    snapped = sorted({snap(float(v)) for v in np.atleast_1d(values) if np.isfinite(v)})
    return np.array(snapped)


def _round_values(unit, lo: float, hi: float, num: int, log: bool) -> np.ndarray:
    """About ``num`` round values between lo and hi (SI), rounded in display
    units so that labels read 25 deg C, not 298.15 K."""
    lo_d, hi_d = sorted(float(v) for v in unit.from_SI([lo, hi]))
    values_d = nice_log(lo_d, hi_d, num) if log else nice_linear(lo_d, hi_d, num)
    if len(values_d) == 0:   # no round value in a very narrow range
        values_d = np.array([0.5 * (lo_d + hi_d)])
    return unit.to_SI(values_d)


def plan(spec: DiagramSpec, domain: Domain) -> Tuple[CurveRequest, ...]:
    """All isolines the diagram needs, in the order of the families in the spec.

    The saturation curve is the pair of quality lines 0 and 1 (fluids) or
    the line of 100 % relative humidity (humid air). With
    ``spec.show_saturation`` True it is drawn whatever values the family is
    given, also without the family; with False it is left out; with None
    (a spec saved before 1.2) the family's values decide, as they did.
    """
    calc = spec.settings.calc
    boundary_family = next((f for f in spec.diagram.families if f.on_boundary), None)
    show = spec.show_saturation
    add_saturation = show is True and domain.saturation and boundary_family is not None
    requests = []

    def saturation_requests(planned_values):
        """The lines of the saturation curve the family did not plan itself."""
        key = boundary_family.key
        points = calc.saturation_points if key == "Q" else calc.points
        return [CurveRequest(isoline_id(key, b), key, float(b), points, False)
                for b in boundary_family.boundary if not any(same_number(b, v) for v in planned_values)]

    for iso_set in spec.isolines:
        family = spec.diagram.family(iso_set.key)
        default_points = calc.saturation_points if iso_set.key == "Q" else calc.points
        points = iso_set.points or default_points
        saturation = {}
        if iso_set.anchor is not None:
            # The first saturation state that gives a value names its line
            for saturation_SI, value_SI in domain.anchor_pairs(iso_set.key, iso_set.anchor):
                saturation.setdefault(snap(value_SI), saturation_SI)
        planned = []
        for value_SI in isoline_values_SI(spec, iso_set, domain):
            if not family.has_line(value_SI):
                continue   # a quality outside 0 to 1, or a relative humidity of 0, has no line
            if show is False and any(same_number(value_SI, b) for b in family.boundary):
                continue   # the saturation curve is hidden
            planned.append(float(value_SI))
            requests.append(CurveRequest(isoline_id(iso_set.key, value_SI), iso_set.key, float(value_SI),
                                         points, iso_set.labels, saturation.get(float(value_SI))))
        if add_saturation and family.key == boundary_family.key:
            requests.extend(saturation_requests(planned))   # next to the family's own lines
            add_saturation = False
    if add_saturation:   # the family is not drawn: the saturation curve comes last
        requests.extend(saturation_requests([]))
    return tuple(requests)
