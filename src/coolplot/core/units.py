# -*- coding: utf-8 -*-
"""Unit systems for displaying quantities.

CoolPlot stores and computes everything in SI units. Conversion to the
units a user wants to see happens in exactly two places: when a user hands
values to the API, and when the scene for the plot is built. That is why a
change of unit system never triggers a new property calculation.

One unit system covers every quantity of :mod:`coolplot.core.quantities`,
for fluids and for humid air alike. The presets are "SI", "KSI" (kJ and
kPa), "engineering" (deg C, bar, kJ, g/kg, %) and "IP" (deg F, psi,
Btu/lb, grains per lb). "EUR", the name of "engineering" before 0.5, was
removed in 1.0.

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
    Unit("deg C", 1.0, -273.15, "K"). The last field names the unit of a
    *difference* of two values, which the offset does not apply to: a
    superheat of 5 K, not 5 deg C. It defaults to the label itself, which
    is right for every unit without an offset.
    """
    label: str
    scale: float = 1.0
    offset: float = 0.0
    difference_label: str = ""

    def from_SI(self, value_SI):
        """Convert a scalar or array from SI to this unit."""
        return np.asarray(value_SI, dtype=float) * self.scale + self.offset

    def to_SI(self, value):
        """Convert a scalar or array from this unit to SI."""
        return (np.asarray(value, dtype=float) - self.offset) / self.scale

    @property
    def difference(self) -> "Unit":
        """The unit of a difference of two values: the same scale, no offset."""
        return Unit(self.difference_label or self.label, self.scale, 0.0)


@dataclass(frozen=True)
class UnitSystem:
    """A named set of units, one per quantity key

    Unit systems are immutable. Use :meth:`with_unit` to derive a modified
    copy, for example to show pressure in MPa in an otherwise engineering system.
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
        return _describe(self[key], value_SI, digits)

    def difference(self, key: str) -> Unit:
        """The unit of a difference in a quantity, e.g. K where temperatures are shown in deg C."""
        return self[key].difference

    def describe_difference(self, key: str, value_SI, digits: int = 4) -> str:
        """A difference in this system's unit, e.g. "5 K" for a superheat."""
        return _describe(self.difference(key), value_SI, digits)

    def with_unit(self, key: str, unit: Unit, name: str = None) -> "UnitSystem":
        """Return a copy where one quantity uses a different unit."""
        units = dict(self.units)
        units[quantity_key(key)] = unit
        return replace(self, name=name or self.name + "*", units=units)


def _describe(unit: Unit, value_SI, digits: int) -> str:
    from .numbers import format_number
    text = format_number(float(unit.from_SI(value_SI)), digits)
    return text if unit.label in ("-", "") else text + " " + unit.label


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
    "T": Unit("deg C", 1.0, -273.15, "K"),
    "p": Unit("bar", 1e-5),
    "W": Unit("g/kg", 1e3),
    "RH": Unit("%", 100.0),
    "Twb": Unit("deg C", 1.0, -273.15, "K"),
    "Tdp": Unit("deg C", 1.0, -273.15, "K"),
})

# Inch-pound units as used in US HVAC practice. 1 Btu (IT) = 1055.05585 J,
# 1 lb = 0.45359237 kg, 1 ft = 0.3048 m, 1 psi = 6894.757 Pa, 7000 grains
# per lb; degrees Rankine for entropy, so that s stays an absolute scale.
_BTU_PER_J = 1.0 / 1055.05585262
_LB_PER_KG = 1.0 / 0.45359237
_FT3_PER_M3 = 1.0 / 0.3048 ** 3
_IP = {
    "T": Unit("deg F", 1.8, -459.67, "R"),
    "p": Unit("psi", 1.0 / 6894.757293168),
    "h": Unit("Btu/lb", _BTU_PER_J / _LB_PER_KG),
    "s": Unit("Btu/lb/R", _BTU_PER_J / _LB_PER_KG / 1.8),
    "rho": Unit("lb/ft3", _LB_PER_KG / _FT3_PER_M3),
    "u": Unit("Btu/lb", _BTU_PER_J / _LB_PER_KG),
    "Q": Unit("-"),
    "W": Unit("gr/lb", 7000.0),
    "RH": Unit("%", 100.0),
    "Twb": Unit("deg F", 1.8, -459.67, "R"),
    "Tdp": Unit("deg F", 1.8, -459.67, "R"),
    "v": Unit("ft3/lb", _FT3_PER_M3 / _LB_PER_KG),
}

#: Gauge pressures, relative to the standard atmosphere of 101325 Pa:
#: ``ENGINEERING.with_unit("p", BAR_GAUGE)``. A pressure axis in a gauge
#: unit is drawn linear, because the offset makes a logarithmic scale
#: impossible (vacuum is negative).
BAR_GAUGE = Unit("bar(g)", 1e-5, -1.01325, "bar")
PSI_GAUGE = Unit("psi(g)", 1.0 / 6894.757293168, -101325.0 / 6894.757293168, "psi")

SI = UnitSystem("SI", _SI)
KSI = UnitSystem("KSI", _KSI)
ENGINEERING = UnitSystem("engineering", _ENGINEERING)
IP = UnitSystem("IP", _IP)
UNIT_SYSTEMS = {u.name.upper(): u for u in (SI, KSI, ENGINEERING, IP)}


def _old_eur(stacklevel: int) -> UnitSystem:
    """ENGINEERING, with a warning: the constant EUR is its old name.

    It never warned before 1.0, so it stays through 1.x and goes in 2.0
    (the name "EUR" in calls warned from 0.5 and is gone in 1.0).
    """
    warnings.warn("EUR is the old name of ENGINEERING (deg C, bar, kJ); it will go in CoolPlot 2.0.",
                  DeprecationWarning, stacklevel=stacklevel + 1)
    return ENGINEERING


def __getattr__(name):
    # Only called for names the module does not define (PEP 562)
    if name == "EUR":
        return _old_eur(2)
    raise AttributeError("module {0!r} has no attribute {1!r}".format(__name__, name))


# Names removed in 1.0, with the name to use instead
_REMOVED_NAMES = {"EUR": "engineering"}


def get_unit_system(units, stacklevel: int = 2) -> UnitSystem:
    """Accept a UnitSystem or the name of a preset: "SI", "KSI", "engineering" or "IP".

    ``stacklevel`` is kept for callers of 0.x, where it placed the warning
    about an old name; it has no effect.
    """
    if isinstance(units, UnitSystem):
        return units
    name = str(units).upper()
    if name in _REMOVED_NAMES:
        raise ValueError("The unit system '{0}' was renamed '{1}' (deg C, bar, kJ) in CoolPlot 0.5 and the old "
                         "name removed in 1.0.".format(units, _REMOVED_NAMES[name]))
    try:
        return UNIT_SYSTEMS[name]
    except KeyError:
        raise ValueError("Unknown unit system '{0}', expected one of {1} or a "
                         "UnitSystem instance.".format(units, [u.name for u in UNIT_SYSTEMS.values()]))
