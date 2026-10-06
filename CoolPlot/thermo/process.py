# -*- coding: utf-8 -*-
"""State points and the paths between them, in SI units.

Cycle calculations belong here, not in the plotting code. A cycle model
produces a sequence of :class:`StatePoint` objects, and the diagram only
draws them. That way the same cycle can be shown on any diagram type, in
any unit system and with any renderer, and it can be tested without
plotting anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import numpy as np

from ..quantities import quantity_key
from .fluid import Fluid

_KEYS = ("T", "p", "h", "s", "rho", "u", "Q")


@dataclass(frozen=True)
class StatePoint:
    """A fully defined thermodynamic state in SI units

    ``Q`` is the vapour quality; CoolProp reports values outside 0 to 1
    for single-phase states.
    """
    T: float
    p: float
    h: float
    s: float
    rho: float
    u: float
    Q: float

    def __getitem__(self, key: str) -> float:
        return getattr(self, quantity_key(key))


def state_point(fluid: Fluid, key1: str, value1_SI: float, key2: str, value2_SI: float) -> StatePoint:
    """Evaluate a full state from two quantities, e.g. state_point(f, "p", 1e5, "T", 300)."""
    fluid.update(quantity_key(key1), value1_SI, quantity_key(key2), value2_SI)
    return StatePoint(**{k: fluid.get(k) for k in _KEYS})


def process_path(fluid: Fluid, start: StatePoint, end: StatePoint, along: Sequence[str] = ("p", "h"),
                 steps: int = 20) -> List[StatePoint]:
    """Intermediate states between two states.

    The two quantities in ``along`` are varied between their start and end
    values and every intermediate state is evaluated from them. Pressure
    and density vary logarithmically, everything else linearly. Typical
    choices: ("p", "s") for a compression or expansion, ("p", "h") for heat
    exchangers and throttling.
    """
    key1, key2 = (quantity_key(k) for k in along)
    steps = max(int(steps), 2)

    def ramp(key):
        a, b = start[key], end[key]
        if key in ("p", "rho") and a > 0.0 and b > 0.0:
            return np.geomspace(a, b, steps)
        return np.linspace(a, b, steps)

    path = []
    for v1, v2 in zip(ramp(key1), ramp(key2)):
        path.append(state_point(fluid, key1, v1, key2, v2))
    return path
