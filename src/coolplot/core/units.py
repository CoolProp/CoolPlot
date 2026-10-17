# -*- coding: utf-8 -*-
"""Unit systems for displaying quantities.

CoolPlot stores and computes everything in SI units. Conversion to the
units a user wants to see happens in exactly two places: when a user hands
values to the API, and when the scene for the plot is built. That is why a
change of unit system never triggers a new property calculation.

One unit system covers every quantity of :mod:`coolplot.core.quantities`,
for fluids and for humid air alike. The presets are "SI", "KSI" (kJ and
kPa), "engineering" (deg C, bar, kJ, g/kg, %) and "IP" (deg F, psi,
Btu/lb, grains per lb). "EUR" is the old name of "engineering" and still
accepted with a warning.

This module is plain data and imports neither CoolProp nor a plotting
library.
"""
from __future__ import annotations

import warnings
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
    units: Mapping[str, Unit] = field(hash=False)

    def __post_init__(self):
        units = {quantity_key(k): u for k, u in dict(self.units).items()}
        for key, unit in units.items():
            if not isinstance(unit, Unit):
                raise TypeError("The unit of '{0}' has to be a Unit, not {1!r}.".format(key, unit))
        # A plain dict (not a read-only proxy), so that the value pickles
        # and deep-copies; the dataclass is frozen and nothing writes to it.
        object.__setattr__(self, "units", units)

    def __hash__(self):
        # Written out because a mapping is not hashable by itself; the
        # units take part, so two systems with the same name but other
        # units are different cache keys.
        return hash((self.name, tuple(sorted(self.units.items()))))

    def __getitem__(self, key: str) -> Unit:
        key = quantity_key(key)
        try:
            return self.units[key]
        except KeyError:
            raise KeyError("The unit system '{0}' has no unit for '{1}'.".format(self.name, key))

    def describe(self, key: str, value_SI, digits: int = 4) -> str:
        """A value in this system's unit, e.g. "25 deg C" or "3.5 bar"."""
        from .numbers import format_number
        unit = self[key]
        text = format_number(float(unit.from_SI(value_SI)), digits)
        return text if unit.label in ("-", "") else text + " " + unit.label

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
    "W": Unit("kg/kg"),
    "RH": Unit("-"),
    "Twb": Unit("K"),
    "Tdp": Unit("K"),
    "v": Unit("m3/kg"),
}

_KSI = dict(_SI, **{
    "p": Unit("kPa", 1e-3),
    "h": Unit("kJ/kg", 1e-3),
    "s": Unit("kJ/kg/K", 1e-3),
    "u": Unit("kJ/kg", 1e-3),
})

_ENGINEERING = dict(_KSI, **{
    "T": Unit("deg C", 1.0, -273.15),
    "p": Unit("bar", 1e-5),
    "W": Unit("g/kg", 1e3),
    "RH": Unit("%", 100.0),
    "Twb": Unit("deg C", 1.0, -273.15),
    "Tdp": Unit("deg C", 1.0, -273.15),
})

# Inch-pound units as used in US HVAC practice. 1 Btu (IT) = 1055.05585 J,
# 1 lb = 0.45359237 kg, 1 ft = 0.3048 m, 1 psi = 6894.757 Pa, 7000 grains
# per lb; degrees Rankine for entropy, so that s stays an absolute scale.
_BTU_PER_J = 1.0 / 1055.05585262
_LB_PER_KG = 1.0 / 0.45359237
_FT3_PER_M3 = 1.0 / 0.3048 ** 3
_IP = {
    "T": Unit("deg F", 1.8, -459.67),
    "p": Unit("psi", 1.0 / 6894.757293168),
    "h": Unit("Btu/lb", _BTU_PER_J / _LB_PER_KG),
    "s": Unit("Btu/lb/R", _BTU_PER_J / _LB_PER_KG / 1.8),
    "rho": Unit("lb/ft3", _LB_PER_KG / _FT3_PER_M3),
    "u": Unit("Btu/lb", _BTU_PER_J / _LB_PER_KG),
    "Q": Unit("-"),
    "W": Unit("gr/lb", 7000.0),
    "RH": Unit("%", 100.0),
    "Twb": Unit("deg F", 1.8, -459.67),
    "Tdp": Unit("deg F", 1.8, -459.67),
    "v": Unit("ft3/lb", _FT3_PER_M3 / _LB_PER_KG),
}

SI = UnitSystem("SI", _SI)
KSI = UnitSystem("KSI", _KSI)
ENGINEERING = UnitSystem("engineering", _ENGINEERING)
IP = UnitSystem("IP", _IP)
#: The old name of the engineering system, kept for existing code.
EUR = ENGINEERING

UNIT_SYSTEMS = {u.name.upper(): u for u in (SI, KSI, ENGINEERING, IP)}
_OLD_NAMES = {"EUR": "engineering"}


def get_unit_system(units, stacklevel: int = 2) -> UnitSystem:
    """Accept a UnitSystem or the name of a preset: "SI", "KSI", "engineering" or "IP".

    ``stacklevel`` is where the warning about an old name is attributed
    to; a public method that passes its argument on gives one more than
    its own depth, so that the warning names the user's line.
    """
    if isinstance(units, UnitSystem):
        return units
    name = str(units).upper()
    if name in _OLD_NAMES:
        warnings.warn("The unit system 'EUR' is called 'engineering' now (deg C, bar, kJ); the old name "
                      "will go in 1.0.", DeprecationWarning, stacklevel=stacklevel)
        name = _OLD_NAMES[name].upper()
    try:
        return UNIT_SYSTEMS[name]
    except KeyError:
        raise ValueError("Unknown unit system '{0}', expected one of {1} or a "
                         "UnitSystem instance.".format(units, [u.name for u in UNIT_SYSTEMS.values()]))
