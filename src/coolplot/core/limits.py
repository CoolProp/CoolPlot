# -*- coding: utf-8 -*-
"""The region a chart covers, as plain data.

A property diagram covers a region described by bounds on temperature
and pressure (:class:`TpLimits`), because those are the quantities
engineers think in. Other charts give absolute bounds on their own
quantities (:class:`Region`). Turning relative bounds into
numbers needs the fluid and happens in :mod:`coolplot.thermo.limits`.

These limits define the *calculation domain*: isolines are computed inside
it. Zooming or panning only changes the visible window.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple, Union

from .quantities import quantity_key


@dataclass(frozen=True)
class Relative:
    """A bound given relative to the saturation range of the fluid

    A lower bound is ``factor`` times the lowest saturation value, an upper
    bound is ``factor`` times the highest one (just below the critical
    point). Relative(2.25) as an upper pressure bound means 2.25 p_crit.
    """
    factor: float


Bound = Union[None, float, Relative]


@dataclass(frozen=True)
class TpLimits:
    """Temperature bounds in K and pressure bounds in Pa

    Each bound is an absolute SI value, a :class:`Relative` factor, or None
    to use the limit of the equation of state.
    """
    T_min: Bound = None
    T_max: Bound = None
    p_min: Bound = None
    p_max: Bound = None


TP_LIMITS = {
    "NONE": TpLimits(),
    "DEF": TpLimits(Relative(1.01), Relative(2.25), Relative(1.01), Relative(2.25)),
    "ACHP": TpLimits(173.15, 493.15, 0.25e5, Relative(2.25)),
    "ORC": TpLimits(273.15, 673.15, 0.25e5, Relative(2.25)),
}


def get_tp_limits(limits) -> TpLimits:
    """Accept a TpLimits, a preset name, or a sequence [T_min, T_max, p_min, p_max] in SI."""
    if isinstance(limits, TpLimits):
        return limits
    if isinstance(limits, str):
        try:
            return TP_LIMITS[limits.upper()]
        except KeyError:
            raise ValueError("Unknown limits preset '{0}', expected one of {1}.".format(
                limits, sorted(TP_LIMITS)))
    if len(limits) == 4:
        return TpLimits(*limits)
    raise ValueError("Expected a TpLimits, a preset name or four values.")


#: What CoolProp's HAPropsSI covers: temperatures in K, total pressures in Pa.
HUMID_AIR_T_LIMITS_K = (173.15, 623.15)
HUMID_AIR_P_LIMITS_PA = (1e4, 1e7)


def within(value: float, limits) -> bool:
    """limits[0] <= value <= limits[1], allowing for rounding (-100 deg C is 173.14999... K)."""
    slack = 1e-9 * max(abs(limits[0]), abs(limits[1]))
    return limits[0] - slack <= value <= limits[1] + slack


@dataclass(frozen=True)
class Region:
    """Absolute bounds on quantities, in SI units, for charts that are not
    described by a T-p box, such as the psychrometric chart (dry-bulb
    temperature and humidity ratio at one total pressure)

    ``bounds`` holds (key, (low, high)) pairs, for example
    (("T", (263.15, 323.15)), ("W", (0.0, 0.03))).
    """
    bounds: Tuple[Tuple[str, Tuple[float, float]], ...]

    def __post_init__(self):
        items = self.bounds.items() if isinstance(self.bounds, dict) else self.bounds
        bounds = []
        for key, (low, high) in items:
            low, high = sorted((float(low), float(high)))
            if not (math.isfinite(low) and math.isfinite(high)) or not high > low:
                raise ValueError("The bounds of '{0}' have to be two different finite values, not {1}.".format(
                    key, (low, high)))
            bounds.append((quantity_key(key), (low, high)))
        if len({k for k, _ in bounds}) != len(bounds):
            raise ValueError("A quantity is bounded twice in {0}.".format(bounds))
        object.__setattr__(self, "bounds", tuple(bounds))

    def range_SI(self, key: str) -> Tuple[float, float]:
        key = quantity_key(key)
        for k, lo_hi in self.bounds:
            if k == key:
                return lo_hi
        raise KeyError("The region has no bounds on '{0}'.".format(key))

    def with_range(self, key: str, low: float, high: float) -> "Region":
        """A copy with the bounds of one quantity replaced or added."""
        key = quantity_key(key)
        kept = tuple((k, v) for k, v in self.bounds if k != key)
        return Region(kept + ((key, (float(low), float(high))),))

    def to_dict(self) -> dict:
        return {"bounds": {k: list(v) for k, v in self.bounds}}

    @classmethod
    def from_dict(cls, data: dict) -> "Region":
        return cls(tuple((k, tuple(v)) for k, v in data["bounds"].items()))
