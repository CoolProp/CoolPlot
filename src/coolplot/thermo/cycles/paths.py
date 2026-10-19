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
from ...core.state import StatePoint
from ..fluid import Fluid
from ..process import state_point

#: Two states count as having the same property within this relative
#: tolerance, when the path kind is chosen automatically.
SAME_RTOL = 1e-6

# The property a "via" keeps from the state before
_KEPT = {"isenthalpic": "h", "isentropic": "s", "isobaric": "p", "isothermal": "T", "isochoric": "rho"}


def predecessors(loops: Sequence[Sequence[int]]) -> Dict[int, int]:
    """For each state, the state before it in the first chain that leads to it."""
    before: Dict[int, int] = {}
    for chain in loops:
        for a, b in zip(chain[:-1], chain[1:]):
            before.setdefault(b, a)
    return before


def resolve_state(fluid: Fluid, given: StateInput, previous: StatePoint = None) -> StatePoint:
    """One state from how it was given; ``previous`` is needed for a via."""
    if given.state is not None:
        return given.state
    if given.via is None:
        (k1, v1), (k2, v2) = given.props
        return state_point(fluid, k1, v1, k2, v2)
    if previous is None:
        raise ValueError("A state with via '{0}' needs a state before it in the cycle.".format(given.via))
    key, value = given.props[0]
    if given.via in _KEPT:
        return state_point(fluid, key, value, _KEPT[given.via], previous[_KEPT[given.via]])
    # Compression or expansion with an isentropic efficiency
    h_s = state_point(fluid, "p", value, "s", previous.s).h
    if given.via == "compression":
        h = previous.h + (h_s - previous.h) / given.eta_is
    else:
        h = previous.h - given.eta_is * (previous.h - h_s)
    return state_point(fluid, "p", value, "h", h)


def resolve_states(fluid: Fluid, inputs: Dict[int, StateInput], loops) -> Dict[int, StatePoint]:
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
            except Exception as e:
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


def path_states(fluid: Fluid, a: StatePoint, b: StatePoint, kind: str = "auto", steps: int = 20) -> List[StatePoint]:
    """States along the process from ``a`` to ``b``, both included.

    Points that CoolProp cannot compute are left out; the path then has
    a longer straight piece there, which is still a faithful line between
    the computed states.
    """
    if kind == "auto":
        kind = auto_kind(a, b)
    if kind == "straight" or steps < 2:
        return [a, b]
    inner: List[Tuple[str, float, str, float]] = []
    t = np.linspace(0.0, 1.0, steps + 1)[1:-1]
    if kind == "isobaric":
        h_values = list(a.h + t * (b.h - a.h))
        # Saturation states, so the path bends exactly on the dome
        for q in (0.0, 1.0):
            try:
                h_sat = state_point(fluid, "p", a.p, "Q", q).h
            except Exception:
                continue
            if min(a.h, b.h) < h_sat < max(a.h, b.h):
                h_values.append(h_sat)
        h_values.sort(reverse=b.h < a.h)
        inner = [("p", a.p, "h", h) for h in h_values]
    elif kind == "isenthalpic":
        inner = [("p", p, "h", a.h) for p in _log_or_linear(a.p, b.p, steps + 1)[1:-1]]
    elif kind == "isentropic":
        inner = [("p", p, "s", a.s) for p in _log_or_linear(a.p, b.p, steps + 1)[1:-1]]
    elif kind == "isothermal":
        inner = [("T", a.T, "s", s) for s in a.s + t * (b.s - a.s)]
    elif kind == "polytropic":
        p_values = _log_or_linear(a.p, b.p, steps + 1)[1:-1]
        inner = [("p", p, "s", a.s + ti * (b.s - a.s)) for p, ti in zip(p_values, t)]
    else:
        raise ValueError("Unknown path kind '{0}'.".format(kind))
    out = [a]
    for k1, v1, k2, v2 in inner:
        try:
            state = state_point(fluid, k1, v1, k2, v2)
        except Exception:
            continue
        if all(math.isfinite(state[k]) for k in ("T", "p", "h", "s")):
            out.append(state)
    out.append(b)
    return out


def cycle_paths(fluid: Fluid, states: Dict[int, StatePoint], loops, paths: Dict[Tuple[int, int], str],
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
