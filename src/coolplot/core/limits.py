# -*- coding: utf-8 -*-
"""The temperature and pressure region a diagram covers, as plain data.

The region is described by bounds on temperature and pressure, because
those are the quantities engineers think in. Turning relative bounds into
numbers needs the fluid and happens in :mod:`coolplot.thermo.limits`.

These limits define the *calculation domain*: isolines are computed inside
it. Zooming or panning only changes the visible window.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


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
