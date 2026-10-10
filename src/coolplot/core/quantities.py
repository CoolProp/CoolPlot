# -*- coding: utf-8 -*-
"""The thermodynamic quantities CoolPlot knows how to put on an axis.

This module is plain data. It imports neither CoolProp nor any plotting
library, so every other layer can depend on it.

Each quantity has a short key that is used everywhere in the public API
("T", "p", "h", "s", "rho", "u", "Q"). The thermo layer translates the key
into a CoolProp parameter through ``coolprop_name``.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Quantity:
    """Static description of one thermodynamic quantity

    Attributes
    ----------
    key : str
        Short name used in the CoolPlot API, for example "p".
    coolprop_name : str
        Name understood by ``CoolProp.CoolProp.get_parameter_index``.
    symbol : str
        Symbol used in axis labels, plain ASCII.
    label : str
        Human readable name used in axis labels.
    log_scale : bool
        Whether an axis showing this quantity defaults to a log scale.
    """
    key: str
    coolprop_name: str
    symbol: str
    label: str
    log_scale: bool = False


QUANTITIES = {
    q.key: q for q in (
        Quantity("T", "T", "T", "Temperature"),
        Quantity("p", "P", "p", "Pressure", log_scale=True),
        Quantity("h", "Hmass", "h", "Specific enthalpy"),
        Quantity("s", "Smass", "s", "Specific entropy"),
        Quantity("rho", "Dmass", "rho", "Density", log_scale=True),
        Quantity("u", "Umass", "u", "Specific internal energy"),
        Quantity("Q", "Q", "x", "Vapour quality"),
    )
}

# Alternative spellings accepted on input. Everything is normalised to the
# keys of QUANTITIES as early as possible.
_ALIASES = {
    "t": "T",
    "P": "p",
    "H": "h", "hmass": "h",
    "S": "s", "smass": "s",
    "D": "rho", "d": "rho", "dmass": "rho", "RHO": "rho",
    "U": "u", "umass": "u",
    "q": "Q", "x": "Q",
}


def quantity_key(name: str) -> str:
    """Normalise a quantity name to its CoolPlot key, e.g. "P" -> "p"."""
    if name in QUANTITIES:
        return name
    if name in _ALIASES:
        return _ALIASES[name]
    lower = name.lower()
    if lower in QUANTITIES:
        return lower
    if lower in _ALIASES:
        return _ALIASES[lower]
    raise KeyError("Unknown quantity '{0}', expected one of {1}.".format(name, sorted(QUANTITIES)))


def get_quantity(name: str) -> Quantity:
    """Return the :class:`Quantity` for a key or one of its aliases."""
    return QUANTITIES[quantity_key(name)]
