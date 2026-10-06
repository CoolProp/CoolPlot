# -*- coding: utf-8 -*-
"""Which quantities go on the axes of a property diagram.

A diagram is named after its axes with the vertical axis first, as is
customary: "ph" is pressure over specific enthalpy (the log(p)-h chart),
"Ts" is temperature over specific entropy.

This module has no CoolProp dependency; it only knows quantity keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..quantities import get_quantity, quantity_key

# Every isoline is computed by stepping through a series of values of one
# quantity (the "sweep" quantity) while the isoline quantity is held
# constant; both axis values are then read from the resulting states. The
# sweep quantity is always temperature or pressure, because CoolProp's
# flash routines are fast and reliable for the input pairs this produces
# (PT, HmassP, PSmass, DmassT). Stepping along a plot axis instead, as older
# versions did, needs pairs like HmassSmass or HmassT that are slow or
# unsupported for many fluids.
_SWEEP = {
    "T": "p",
    "p": "T",
    "h": "p",
    "s": "p",
    "rho": "T",
    "u": "p",
    "Q": "T",   # lines of constant quality are traced through saturation states
}

_NAMES = {
    "TS": ("T", "s"), "PH": ("p", "h"), "HS": ("h", "s"), "PS": ("p", "s"),
    "PD": ("p", "rho"), "PRHO": ("p", "rho"), "TD": ("T", "rho"),
    "TRHO": ("T", "rho"), "PT": ("p", "T"),
}


@dataclass(frozen=True)
class DiagramType:
    """The pair of quantities on the axes

    Attributes
    ----------
    y : str
        Quantity key on the vertical axis.
    x : str
        Quantity key on the horizontal axis.
    """
    y: str
    x: str

    @classmethod
    def parse(cls, name) -> "DiagramType":
        """Build from a name like "ph", "Ts", "PH" or an existing DiagramType."""
        if isinstance(name, DiagramType):
            return name
        try:
            y, x = _NAMES[str(name).upper()]
        except KeyError:
            raise ValueError("Unknown diagram type '{0}', expected one of {1}.".format(
                name, sorted(n.lower() for n in _NAMES)))
        return cls(y=y, x=x)

    @property
    def name(self) -> str:
        return self.y + self.x

    @property
    def x_log(self) -> bool:
        return get_quantity(self.x).log_scale

    @property
    def y_log(self) -> bool:
        return get_quantity(self.y).log_scale

    def sweep_quantity(self, iso_key: str) -> Optional[str]:
        """Quantity stepped through to compute an isoline, or None if unsupported.

        A line of constant x or constant y is a straight line parallel to an
        axis and is not offered as an isoline; use the grid for that.
        """
        iso_key = quantity_key(iso_key)
        if iso_key in (self.x, self.y):
            return None
        return _SWEEP.get(iso_key)

    def supports(self, iso_key: str) -> bool:
        return self.sweep_quantity(iso_key) is not None

    def supported_isolines(self):
        """Quantity keys that can be drawn as isolines in this diagram."""
        return [k for k in _SWEEP if self.supports(k)]
