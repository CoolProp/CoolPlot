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
from typing import Iterable, Iterator, Mapping, Sequence, Tuple, Union

from .cycle import Cycle
from .quantities import quantity_key
from .state import StatePoint


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

    @classmethod
    def around(cls, *sources: object, dT_margin_K: float = 40.0, p_factor: float = 2.0) -> "TpLimits":
        """The region around the states of cycles, with a margin

        The presets cover the whole fluid or a typical application; a
        region around the states of the cycles on a chart keeps the lines
        where the cycles are, with round values at a step that suits them.

        Parameters
        ----------
        *sources
            Cycles (:class:`coolplot.core.cycle.Cycle`), states
            (:class:`coolplot.core.state.StatePoint` or dicts with ``T`` in
            K and ``p`` in Pa), or collections of them, by number or by
            name, e.g. what :meth:`coolplot.Chart.cycle_states` returns
            without ``units``. The values are SI: states converted to the
            units of a chart (``cycle_states(name, units=...)``) are not.
        dT_margin_K : float
            Kelvin below the lowest and above the highest temperature.
        p_factor : float
            The lowest pressure is divided by it, the highest multiplied.

        Returns
        -------
        TpLimits
            Absolute bounds; the equation of state still limits them when
            the lines are computed.

        Examples
        --------
        >>> from coolplot import StatePoint, TpLimits
        >>> TpLimits.around([StatePoint(T=270.0, p=4e5), StatePoint(T=330.0, p=20e5)])
        TpLimits(T_min=230.0, T_max=370.0, p_min=200000.0, p_max=4000000.0)

        On a chart, around the cycles drawn on it:

        >>> diagram.tp_limits = TpLimits.around(diagram.cycle_states("hp"))  # doctest: +SKIP
        """
        if not dT_margin_K >= 0:
            raise ValueError("dT_margin_K has to be zero or positive, not {0}.".format(dT_margin_K))
        if not p_factor >= 1:
            raise ValueError("p_factor has to be 1 or more, not {0}.".format(p_factor))
        states = list(_states(sources))
        if not states:
            raise ValueError("Give at least one state or a cycle with states.")
        T_K = [_checked_value(state, "T") for state in states]
        p_Pa = [_checked_value(state, "p") for state in states]
        T_lo_K, T_hi_K = min(T_K) - dT_margin_K, max(T_K) + dT_margin_K
        p_lo_Pa, p_hi_Pa = min(p_Pa) / p_factor, max(p_Pa) * p_factor
        if not (T_lo_K < T_hi_K and p_lo_Pa < p_hi_Pa):
            raise ValueError("Empty region T=[{0}, {1}] K, p=[{2}, {3}] Pa around the states; give a margin.".format(
                T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa))
        return cls(T_min=T_lo_K, T_max=T_hi_K, p_min=p_lo_Pa, p_max=p_hi_Pa)


# A state as around takes it: a StatePoint, or a dict of quantities in SI units
_State = Union[StatePoint, Mapping[str, object]]


def _is_source(value: object) -> bool:
    """Whether a value of a mapping is a cycle, a state or a collection, not the number of a quantity."""
    return isinstance(value, (Cycle, StatePoint, Mapping)) or (
        isinstance(value, Iterable) and not isinstance(value, str))


def _states(sources: Iterable[object]) -> Iterator[_State]:
    """The states of cycles, states and collections of them, one by one."""
    for source in sources:
        if isinstance(source, Cycle):
            yield from (state for _, state in source.states)
        elif isinstance(source, StatePoint):
            yield source
        elif isinstance(source, Mapping):
            # A mapping is one state given by its quantities, or a collection
            # by number or name; what it holds decides, not its keys
            if not source or any(_is_source(value) for value in source.values()):
                yield from _states(source.values())
            else:
                yield source
        elif isinstance(source, Iterable) and not isinstance(source, str):
            yield from _states(source)
        else:
            raise TypeError("Expected cycles, states or collections of them, not {0!r}; the margins are given "
                            "by keyword (dT_margin_K, p_factor).".format(source))


def _checked_value(state: _State, key: str) -> float:
    """The temperature or pressure of a state as it is given, in SI units: a positive finite number."""
    values: dict = {}
    for name in state.keys():
        try:
            values[quantity_key(name)] = state[name]   # aliases such as "P" are accepted on input
        except (KeyError, AttributeError):
            pass   # not a quantity, e.g. the "via" of a cycle state
    if key not in values:
        raise ValueError("Every state needs a temperature and a pressure, one has no {0!r}.".format(key))
    try:
        value = float(values[key])
    except (TypeError, ValueError):
        raise ValueError("The {0!r} of a state is not a number: {1!r}.".format(key, values[key])) from None
    if not (math.isfinite(value) and value > 0.0):
        raise ValueError("The {0!r} of a state is {1}; temperatures are in K and pressures in Pa, positive and "
                         "finite. States in the units of a chart are not SI.".format(key, value))
    return value


TP_LIMITS = {
    "NONE": TpLimits(),
    "DEF": TpLimits(Relative(1.01), Relative(2.25), Relative(1.01), Relative(2.25)),
    "ACHP": TpLimits(173.15, 493.15, 0.25e5, Relative(2.25)),
    "ORC": TpLimits(273.15, 673.15, 0.25e5, Relative(2.25)),
}


# Limits as the public functions take them, for the annotations: a preset
# name ("DEF", "ACHP", ...), a TpLimits, or four bounds [T_min, T_max, p_min, p_max] in SI.
TpLimitsLike = Union[str, TpLimits, Sequence[Bound]]


def get_tp_limits(limits: TpLimitsLike) -> TpLimits:
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
        # Sorted by key: equal regions compare and hash equal (Engine.domain
        # uses them in its cache key) and survive JSON written with sort_keys
        object.__setattr__(self, "bounds", tuple(sorted(bounds)))

    def range_SI(self, key: str) -> Tuple[float, float]:
        """The (min, max) bounds of quantity ``key`` in SI units."""
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
        """The record of docs/reference/contracts.md for this region."""
        return {"bounds": {k: list(v) for k, v in self.bounds}}

    @classmethod
    def from_dict(cls, data: dict) -> "Region":
        """A region from its record, see :meth:`to_dict`."""
        return cls(tuple((k, tuple(v)) for k, v in data["bounds"].items()))
