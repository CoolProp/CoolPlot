# -*- coding: utf-8 -*-
"""A thermodynamic state as plain data.

Defined in the core layer so that specs (for example the states of a
cycle) can hold states without depending on CoolProp. The thermo layer
computes them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .quantities import quantity_key

#: Quantities stored in every StatePoint, in this order.
STATE_KEYS = ("T", "p", "h", "s", "rho", "u", "Q")


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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StatePoint":
        return cls(**{k: float(data[k]) for k in STATE_KEYS})
