# -*- coding: utf-8 -*-
"""A thermodynamic state as plain data.

Defined in the core layer so that specs (for example the states of a
cycle) can hold states without depending on CoolProp. The thermo layer
computes them.
"""
from __future__ import annotations

from typing import Dict, Tuple

from .quantities import quantity_key

#: Quantities stored in every state of a fluid, in this order.
STATE_KEYS = ("T", "p", "h", "s", "rho", "u", "Q")

#: Quantities stored in every state of humid air (per kg of dry air).
AIR_STATE_KEYS = ("T", "W", "RH", "Twb", "Tdp", "h", "v", "p")

# The order in which a StatePoint keeps its quantities, whatever order they
# were given in, so that equal states compare and hash equal and a state
# read back from JSON is the same value. Keys not listed follow alphabetically.
_ORDER = {key: i for i, key in enumerate(STATE_KEYS + tuple(k for k in AIR_STATE_KEYS if k not in STATE_KEYS))}


class StatePoint:
    """A fully defined state in SI units

    A read-only mapping from quantity keys to values that also allows
    attribute access: ``state.h`` and ``state["h"]`` are the same. A fluid
    state holds :data:`STATE_KEYS`, a humid-air state :data:`AIR_STATE_KEYS`.
    ``Q`` is the vapour quality; CoolProp reports values outside 0 to 1
    for single-phase states.

    Written as a plain class rather than a dataclass so that fluids and
    humid air share one type: the set of keys is decided by whoever
    computes the state. Instances compare and hash by their values, in
    whatever order the quantities were given.
    """
    __slots__ = ("_values",)

    def __init__(self, **values):
        items = [(quantity_key(k), float(v)) for k, v in values.items()]
        if not items:
            raise ValueError("A StatePoint needs at least one quantity.")
        if len({k for k, _ in items}) != len(items):
            raise ValueError("A quantity is given twice in {0}.".format(list(values)))
        items.sort(key=lambda kv: (_ORDER.get(kv[0], len(_ORDER)), kv[0]))
        object.__setattr__(self, "_values", tuple(items))

    # Read access ---------------------------------------------------------
    def __getattr__(self, name: str) -> float:
        # Only called when normal attribute lookup fails, so _values and
        # the methods are found the usual way.
        if name == "_values":   # a half-built instance (pickling, __new__)
            raise AttributeError(name)
        for key, value in self._values:
            if key == name:
                return value
        raise AttributeError("StatePoint has no quantity {0!r}.".format(name))

    def __getitem__(self, key: str) -> float:
        key = quantity_key(key)
        for k, value in self._values:
            if k == key:
                return value
        raise KeyError("StatePoint has no quantity {0!r}.".format(key))

    def __contains__(self, key: str) -> bool:
        try:
            return quantity_key(key) in self.keys()
        except KeyError:
            return False

    def keys(self) -> Tuple[str, ...]:
        return tuple(k for k, _ in self._values)

    def __iter__(self):
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self._values)

    def to_dict(self) -> Dict[str, float]:
        return dict(self._values)

    @classmethod
    def from_dict(cls, data: dict) -> "StatePoint":
        return cls(**{k: float(v) for k, v in data.items()})

    # Value semantics -----------------------------------------------------
    def __setattr__(self, name, value):
        raise AttributeError("StatePoint is read-only.")

    def __eq__(self, other) -> bool:
        return isinstance(other, StatePoint) and self._values == other._values

    def __hash__(self) -> int:
        return hash(self._values)

    def __repr__(self) -> str:
        return "StatePoint({0})".format(", ".join("{0}={1:.6g}".format(k, v) for k, v in self._values))

    def __reduce__(self):
        # Pickled as its values, so a state travels to worker processes
        return (_state_from_items, (self._values,))


def _state_from_items(items) -> StatePoint:
    return StatePoint(**dict(items))
