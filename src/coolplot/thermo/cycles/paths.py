# -*- coding: utf-8 -*-
"""States of a cycle and the paths between them, in SI units.

:func:`resolve_states` turns the way states were given (two properties,
one property and the process leading to it, or a complete state) into
StatePoints. :func:`path_states` fills in the states along the process
between two states, so that a heat exchanger follows its isobar through
the saturation dome instead of cutting straight across.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np

from ...core.cycle import StateInput
from ...core.errors import PropertyError
from ...core.state import CP_DRY_AIR_J_KG_K, R0_J_KG, StatePoint, with_mollier_temperature
from ..process import state_point

# ``fluid`` in the functions below is a property provider: a
# coolplot.thermo.Fluid or a coolplot.thermo.humid_air.HumidAir.

#: Two states count as having the same property within this relative
#: tolerance, when the path kind is chosen automatically.
SAME_RTOL = 1e-6

# The property a "via" keeps from the state before
_KEPT = {"isenthalpic": "h", "isentropic": "s", "isobaric": "p", "isothermal": "T", "isochoric": "rho",
         "sensible": "W"}


def predecessors(loops: Sequence[Sequence[int]]) -> Dict[int, int]:
    """For each state, the state before it in the first chain that leads to it."""
    before: Dict[int, int] = {}
    for chain in loops:
        for a, b in zip(chain[:-1], chain[1:]):
            before.setdefault(b, a)
    return before


def resolve_state(fluid, given: StateInput, previous: StatePoint = None) -> StatePoint:
    """One state from how it was given; ``previous`` is needed for a via."""
    if given.state is not None:
        return with_mollier_temperature(given.state)   # a humid-air state made before 1.2 lacks Thx
    if given.via is None:
        (k1, v1), (k2, v2) = given.props
        return state_point(fluid, k1, v1, k2, v2)
    if previous is None:
        raise ValueError("A state with via '{0}' needs a state before it in the cycle.".format(given.via))
    key, value = given.props[0]
    if given.via == "sensible" and "W" not in fluid.quantities:
        raise ValueError("via 'sensible' keeps the humidity ratio W, which only humid air has; "
                         "a chart of {0} has no humidity ratio.".format(fluid.name))
    if given.via == "sensible" and key in ("h", "Thx"):
        # Given by the enthalpy or the Mollier scale: below the enthalpy at the dew point, water condenses
        h = value if key == "h" else CP_DRY_AIR_J_KG_K * (value - 273.15) + R0_J_KG * previous.W
        h_dew = state_point(fluid, "T", previous.Tdp, "W", previous.W).h
        if h < h_dew:
            raise ValueError("via 'sensible' cannot cool below the dew point {0:.2f} K of the state before "
                             "(h = {1:.1f} J/kg there, {2:.1f} J/kg asked): water would condense. Give the "
                             "state off the coil by two properties, e.g. T and RH.".format(
                                 previous.Tdp, h_dew, h))
    if given.via == "sensible" and key == "T" and value < previous.Tdp:
        raise ValueError("via 'sensible' cannot cool to {0:.2f} K, below the dew point {1:.2f} K of the state "
                         "before: water would condense. Give the state off the coil by two properties, e.g. "
                         "T and RH.".format(value, previous.Tdp))
    if given.via in _KEPT:
        return state_point(fluid, key, value, _KEPT[given.via], previous[_KEPT[given.via]])
    # Compression or expansion with an isentropic efficiency
    h_s = state_point(fluid, "p", value, "s", previous.s).h
    if given.via == "compression":
        h = previous.h + (h_s - previous.h) / given.eta_is
    else:
        h = previous.h - given.eta_is * (previous.h - h_s)
    return state_point(fluid, "p", value, "h", h)


def resolve_states(fluid, inputs: Dict[int, StateInput], loops) -> Dict[int, StatePoint]:
    """All states of a cycle.

    States given by two properties are computed first; a state given with
    "via" follows once the state before it is known. Raises ValueError if
    a state cannot be computed, naming the state.
    """
    before = predecessors(loops)
    states: Dict[int, StatePoint] = {}
    pending = dict(inputs)
    while pending:
        progress = False
        for number in sorted(pending):
            given = pending[number]
            previous = None
            if given.state is None and given.via is not None:
                if before.get(number) not in states:
                    if number not in before:
                        raise ValueError("State {0} is given with via '{1}' but no chain leads to it.".format(
                            number, given.via))
                    continue
                previous = states[before[number]]
            try:
                states[number] = resolve_state(fluid, given, previous)
            except PropertyError as e:
                raise e.with_where("State {0} of the cycle".format(number)) from None
            except ValueError as e:
                raise ValueError("State {0} of the cycle could not be computed: {1}".format(number, e)) from e
            del pending[number]
            progress = True
        if not progress:
            raise ValueError("States {0} depend on each other through 'via' and cannot be computed.".format(
                sorted(pending)))
    return states


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= SAME_RTOL * max(abs(a), abs(b), 1e-12)


def auto_kind(a: StatePoint, b: StatePoint) -> str:
    """The process between two states, judged from what they have in common."""
    for key, kind in (("p", "isobaric"), ("h", "isenthalpic"), ("s", "isentropic"), ("T", "isothermal")):
        if _same(a[key], b[key]):
            return kind
    return "polytropic"


def _log_or_linear(lo: float, hi: float, n: int) -> np.ndarray:
    if lo > 0.0 and hi > 0.0:
        return np.geomspace(lo, hi, n)
    return np.linspace(lo, hi, n)


def path_states(fluid, a: StatePoint, b: StatePoint, kind: str = "auto", steps: int = 20) -> List[StatePoint]:
    """States along the process from ``a`` to ``b``, both included.

    The provider may replace the kind (humid air draws every path
    straight). Points that CoolProp cannot compute are left out; the path
    then has a longer straight piece there, which is still a faithful line
    between the computed states.
    """
    kind = fluid.path_kind(a, b, kind)
    if kind == "auto":
        kind = auto_kind(a, b)
    if kind == "straight" or steps < 2:
        return [a, b]
    out = [a]
    for k1, v1, k2, v2 in _inner_inputs(fluid, a, b, kind, steps):
        try:
            state = state_point(fluid, k1, v1, k2, v2)
        except Exception:
            continue
        if all(math.isfinite(state[k]) for k in ("T", "p", "h", "s")):
            out.append(state)
    out.append(b)
    return out


def _inner_inputs(fluid, a: StatePoint, b: StatePoint, kind: str, steps: int) -> List[Tuple[str, float, str, float]]:
    """The (key, value, key, value) inputs of the states between a and b along a path kind."""
    t = np.linspace(0.0, 1.0, steps + 1)[1:-1]
    if kind == "isobaric":
        return [("p", a.p, "h", h) for h in _isobar_enthalpies(fluid, a, b, t)]
    if kind == "isothermal":
        return [("T", a.T, "s", s) for s in a.s + t * (b.s - a.s)]
    if kind not in ("isenthalpic", "isentropic", "polytropic"):
        raise ValueError("Unknown path kind '{0}'.".format(kind))
    p_values = _log_or_linear(a.p, b.p, steps + 1)[1:-1]
    if kind == "isenthalpic":
        return [("p", p, "h", a.h) for p in p_values]
    # Entropy kept (isentropic), or changed evenly with pressure (polytropic)
    s_values = [a.s] * len(t) if kind == "isentropic" else a.s + t * (b.s - a.s)
    return [("p", p, "s", s) for p, s in zip(p_values, s_values)]


def _isobar_enthalpies(fluid, a: StatePoint, b: StatePoint, t) -> List[float]:
    """Enthalpies along an isobar from a to b, with the saturation states
    added so that the path bends exactly on the dome."""
    h_values = list(a.h + t * (b.h - a.h))
    for q in (0.0, 1.0):
        try:
            h_sat = state_point(fluid, "p", a.p, "Q", q).h
        except Exception:
            continue
        if min(a.h, b.h) < h_sat < max(a.h, b.h):
            h_values.append(h_sat)
    h_values.sort(reverse=b.h < a.h)
    return h_values


def cycle_paths(fluid, states: Dict[int, StatePoint], loops, paths: Dict[Tuple[int, int], str],
                steps: int = 20) -> List[List[StatePoint]]:
    """For every chain, the states along all its connections, in order."""
    out = []
    for chain in loops:
        line: List[StatePoint] = [states[chain[0]]]
        for a, b in zip(chain[:-1], chain[1:]):
            kind = paths.get((a, b), "auto")
            line.extend(path_states(fluid, states[a], states[b], kind, steps)[1:])
        out.append(line)
    return out
