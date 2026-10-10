# -*- coding: utf-8 -*-
"""Unit systems for displaying quantities.

CoolPlot stores and computes everything in SI units. Conversion to the
units a user wants to see happens in exactly two places: when a user hands
values to the API, and when the scene for the plot is built. That is why a
change of unit system never triggers a new property calculation.

This module is plain data and imports neither CoolProp nor a plotting
library.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

import numpy as np

from .quantities import quantity_key


@dataclass(frozen=True)
class Unit:
    """A linear unit: value_display = value_SI * scale + offset

    Examples: bar is Unit("bar", 1e-5), degree Celsius is
    Unit("deg C", 1.0, -273.15).
    """
    label: str
    scale: float = 1.0
    offset: float = 0.0

    def from_SI(self, value_SI):
        """Convert a scalar or array from SI to this unit."""
        return np.asarray(value_SI, dtype=float) * self.scale + self.offset

    def to_SI(self, value):
        """Convert a scalar or array from this unit to SI."""
        return (np.asarray(value, dtype=float) - self.offset) / self.scale


@dataclass(frozen=True)
class UnitSystem:
    """A named set of units, one per quantity key

    Unit systems are immutable. Use :meth:`with_unit` to derive a modified
    copy, for example to show pressure in MPa in an otherwise EUR system.
    """
    name: str
    # The mapping does not take part in hashing because dictionaries are not
    # hashable. Two systems that share a name but differ in their units will
    # still compare unequal, which is all the rest of CoolPlot relies on.
    units: Mapping[str, Unit] = field(hash=False)

    def __getitem__(self, key: str) -> Unit:
        return self.units[quantity_key(key)]

    def with_unit(self, key: str, unit: Unit, name: str = None) -> "UnitSystem":
        """Return a copy where one quantity uses a different unit."""
        units = dict(self.units)
        units[quantity_key(key)] = unit
        return replace(self, name=name or self.name + "*", units=units)


_SI = {
    "T": Unit("K"),
    "p": Unit("Pa"),
    "h": Unit("J/kg"),
    "s": Unit("J/kg/K"),
    "rho": Unit("kg/m3"),
    "u": Unit("J/kg"),
    "Q": Unit("-"),
}

_KSI = dict(_SI, **{
    "p": Unit("kPa", 1e-3),
    "h": Unit("kJ/kg", 1e-3),
    "s": Unit("kJ/kg/K", 1e-3),
    "u": Unit("kJ/kg", 1e-3),
})

_EUR = dict(_KSI, **{
    "T": Unit("deg C", 1.0, -273.15),
    "p": Unit("bar", 1e-5),
})

SI = UnitSystem("SI", _SI)
KSI = UnitSystem("KSI", _KSI)
EUR = UnitSystem("EUR", _EUR)

UNIT_SYSTEMS = {u.name: u for u in (SI, KSI, EUR)}


def get_unit_system(units) -> UnitSystem:
    """Accept a UnitSystem or the name of a predefined one ('SI', 'KSI', 'EUR')."""
    if isinstance(units, UnitSystem):
        return units
    try:
        return UNIT_SYSTEMS[str(units).upper()]
    except KeyError:
        raise ValueError("Unknown unit system '{0}', expected one of {1} or a "
                         "UnitSystem instance.".format(units, sorted(UNIT_SYSTEMS)))
