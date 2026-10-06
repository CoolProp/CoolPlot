# -*- coding: utf-8 -*-
"""The region of states a property plot covers.

The region is described by bounds on temperature and pressure because those
are the quantities engineers think in. The axis ranges of any diagram are
derived from these bounds by evaluating the plotted quantities at the four
corners of the T-p rectangle.

These limits define the *calculation domain*: isolines are computed inside
it. Zooming or panning in an interactive plot changes only the visible
window in the scene and does not need new property calculations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Union

import numpy as np

from ..quantities import quantity_key
from .diagram_type import DiagramType
from .fluid import Fluid


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

    def resolve(self, fluid: Fluid) -> Tuple[float, float, float, float]:
        """Absolute (T_min_K, T_max_K, p_min_Pa, p_max_Pa) for one fluid."""
        T_sat_lo_K, T_sat_hi_K = fluid.saturation_range("T")
        p_sat_lo_Pa, p_sat_hi_Pa = fluid.saturation_range("p")

        def absolute(bound, sat_value, fallback):
            if bound is None:
                return fallback
            if isinstance(bound, Relative):
                return bound.factor * sat_value
            return float(bound)

        T_lo_K = absolute(self.T_min, T_sat_lo_K, 0.0)
        T_hi_K = absolute(self.T_max, T_sat_hi_K, np.inf)
        p_lo_Pa = absolute(self.p_min, p_sat_lo_Pa, 0.0)
        p_hi_Pa = absolute(self.p_max, p_sat_hi_Pa, np.inf)

        # Never leave the validity range of the equation of state
        if fluid.T_min_K is not None:
            T_lo_K = max(T_lo_K, fluid.T_min_K)
        if fluid.T_max_K is not None:
            T_hi_K = min(T_hi_K, fluid.T_max_K)
        if fluid.p_min_Pa is not None:
            p_lo_Pa = max(p_lo_Pa, fluid.p_min_Pa)
        if fluid.p_max_Pa is not None:
            p_hi_Pa = min(p_hi_Pa, fluid.p_max_Pa)
        if not (T_lo_K < T_hi_K and p_lo_Pa < p_hi_Pa):
            raise ValueError("Empty plotting region T=[{0}, {1}] K, p=[{2}, {3}] Pa.".format(
                T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa))
        return T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa


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


def property_range_SI(fluid: Fluid, key: str, tp_box: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """Smallest and largest value of a quantity on the corners of the T-p box."""
    key = quantity_key(key)
    T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa = tp_box
    if key == "T":
        return T_lo_K, T_hi_K
    if key == "p":
        return p_lo_Pa, p_hi_Pa
    if key == "Q":
        return 0.0, 1.0
    values = []
    for T_K in (T_lo_K, T_hi_K):
        for p_Pa in (p_lo_Pa, p_hi_Pa):
            try:
                fluid.update("p", p_Pa, "T", T_K)
                values.append(fluid.get(key))
            except Exception:
                pass  # a corner outside the EOS range just does not contribute
    values = [v for v in values if np.isfinite(v)]
    if len(values) < 2:
        raise ValueError("Could not determine the range of '{0}' for {1}.".format(key, fluid.name))
    return min(values), max(values)


def axis_ranges_SI(fluid: Fluid, diagram: DiagramType, tp_box) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """((x_min, x_max), (y_min, y_max)) of a diagram in SI units."""
    return (property_range_SI(fluid, diagram.x, tp_box),
            property_range_SI(fluid, diagram.y, tp_box))
