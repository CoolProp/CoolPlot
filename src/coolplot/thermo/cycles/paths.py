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
from typing import Dict, List, Optional, Sequence, Tuple

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


def resolve_state(fluid, given: StateInput, previous: Optional[StatePoint] = None) -> StatePoint:
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
    for key, kind in (("p", "isobaric"), ("h", "isenthalpic"), ("s", "isentropic"), ("T", "isothermal"),
                      ("rho", "isochoric")):
        if _same(a[key], b[key]):
            return kind
    return "polytropic"


#: For the paths that keep a property CoolProp can flash together with the
#: quality Q, the property kept and the property that changes evenly along
#: the path. Their saturation states are found exactly; on the other paths
#: the dome is found by bisection, see :func:`_dome_crossings`.
_EXACT_SATURATION = {"isobaric": ("p", "h"), "isothermal": ("T", "s")}

#: A dome crossing is located to within this fraction of the path.
CROSSING_TOL = 1e-9


def path_states(fluid, a: StatePoint, b: StatePoint, kind: str = "auto", steps: int = 20) -> List[StatePoint]:
    """States along the process from ``a`` to ``b``, both included.

    Where the path enters or leaves the saturation dome, the state on the
    dome is added, so that the line bends exactly there instead of cutting
    the corner between two samples.

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
    if kind not in _PATH_INPUTS:
        raise ValueError("Unknown path kind '{0}'.".format(kind))
    # Each point is the fraction t along the path (0 at a, 1 at b) and its state
    inner = sorted(set(np.linspace(0.0, 1.0, steps + 1)[1:-1]) | set(_saturation_fractions(fluid, a, b, kind)))
    points = [(0.0, a)]
    for t in inner:
        state = _state_at(fluid, a, b, kind, t)
        if state is not None:
            points.append((t, state))
    points.append((1.0, b))
    if kind not in _EXACT_SATURATION:
        points = _dome_crossings(fluid, a, b, kind, points)
    return [state for _, state in points]


def _path_inputs(a: StatePoint, b: StatePoint, kind: str, t: float) -> Tuple[str, float, str, float]:
    """The (key, value, key, value) inputs of the state a fraction t along the path from a to b.

    The pressure changes on a log scale (evenly in log p), the other
    properties linearly.
    """
    return _PATH_INPUTS[kind](a, b, t)


def _linear(x_a: float, x_b: float, t: float) -> float:
    return x_a + t * (x_b - x_a)


def _log_or_linear(x_a: float, x_b: float, t: float) -> float:
    if x_a > 0.0 and x_b > 0.0:
        return x_a * (x_b / x_a) ** t
    return _linear(x_a, x_b, t)


# For each path kind, the inputs of the state a fraction t along the path
_PATH_INPUTS = {
    "isobaric": lambda a, b, t: ("p", a.p, "h", _linear(a.h, b.h, t)),
    "isothermal": lambda a, b, t: ("T", a.T, "s", _linear(a.s, b.s, t)),
    "isochoric": lambda a, b, t: ("rho", a.rho, "T", _linear(a.T, b.T, t)),
    "isenthalpic": lambda a, b, t: ("p", _log_or_linear(a.p, b.p, t), "h", a.h),
    "isentropic": lambda a, b, t: ("p", _log_or_linear(a.p, b.p, t), "s", a.s),
    # Entropy changed evenly with log p
    "polytropic": lambda a, b, t: ("p", _log_or_linear(a.p, b.p, t), "s", _linear(a.s, b.s, t)),
}


def _state_at(fluid, a: StatePoint, b: StatePoint, kind: str, t: float) -> Optional[StatePoint]:
    """The state a fraction t along the path, or None where CoolProp cannot compute it."""
    try:
        state = state_point(fluid, *_path_inputs(a, b, kind, t))
    except Exception:
        return None
    if all(math.isfinite(state[k]) for k in ("T", "p", "h", "s")):
        return state
    return None


def _saturation_fractions(fluid, a: StatePoint, b: StatePoint, kind: str) -> List[float]:
    """Where an isobar or an isotherm meets the bubble and dew lines, as fractions of the path."""
    if kind not in _EXACT_SATURATION:
        return []
    kept, varied = _EXACT_SATURATION[kind]
    if b[varied] == a[varied]:
        return []
    out = []
    for q in (0.0, 1.0):
        try:
            x_sat = state_point(fluid, kept, a[kept], "Q", q)[varied]
        except Exception:
            continue    # e.g. above the critical point
        t = (x_sat - a[varied]) / (b[varied] - a[varied])
        if 0.0 < t < 1.0:
            out.append(t)
    return out


def _in_dome(state: StatePoint) -> bool:
    """Whether a state is two-phase; CoolProp gives Q = -1 for a single phase."""
    return 0.0 <= state.Q <= 1.0


def _dome_crossings(fluid, a: StatePoint, b: StatePoint, kind: str, points):
    """``points`` with a state added on the dome between each pair of
    neighbours of which one is two-phase and the other is not.

    The crossing is found by bisection on the fraction along the path, since
    CoolProp cannot flash, say, an entropy together with the quality. A path
    that enters and leaves the dome between two neighbours is not seen; a
    finer ``steps`` finds it.
    """
    out = [points[0]]
    for (t_a, s_a), (t_b, s_b) in zip(points[:-1], points[1:]):
        if _in_dome(s_a) != _in_dome(s_b) and not (_on_dome(s_a) or _on_dome(s_b)):
            crossing = _bisect_dome(fluid, a, b, kind, t_a, t_b, _in_dome(s_a))
            if crossing is not None:
                out.append(crossing)
        out.append((t_b, s_b))
    return out


def _on_dome(state: StatePoint) -> bool:
    """Whether a state is saturated liquid or saturated vapour (a state given with Q = 0 or 1)."""
    return state.Q == 0.0 or state.Q == 1.0


def _bisect_dome(fluid, a: StatePoint, b: StatePoint, kind: str, t_lo: float, t_hi: float, inside_lo: bool):
    """(t, state) on the dome between the fractions t_lo and t_hi, or None if CoolProp fails on the way."""
    crossing = None
    while t_hi - t_lo > CROSSING_TOL:
        t_mid = 0.5 * (t_lo + t_hi)
        state = _state_at(fluid, a, b, kind, t_mid)
        if state is None:
            return None
        crossing = (t_mid, state)
        if _in_dome(state) == inside_lo:
            t_lo = t_mid
        else:
            t_hi = t_mid
    return crossing


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
