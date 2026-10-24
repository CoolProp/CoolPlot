# -*- coding: utf-8 -*-
"""The quantities CoolPlot knows how to put on an axis or hold constant.

This module is plain data. It imports neither CoolProp nor any plotting
library, so every other layer can depend on it.

Each quantity has a short key that is used everywhere in the public API:
"T", "p", "h", "s", "rho", "u" and "Q" for fluids, and in addition "W",
"RH", "Twb", "Tdp" and "v" for humid air. The thermo layer translates a
key into a CoolProp parameter through ``coolprop_name`` (AbstractState)
or ``humid_air_name`` (HAPropsSI).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Quantity:
    """Static description of one quantity

    Attributes
    ----------
    key : str
        Short name used in the CoolPlot API, for example "p".
    coolprop_name : str or None
        Name understood by ``CoolProp.CoolProp.get_parameter_index``, or
        None for a quantity that fluid states do not have.
    humid_air_name : str or None
        Name understood by ``CoolProp.HumidAirProp.HAPropsSI``, or None
        for a quantity that humid air does not have.
    symbol : str
        Symbol used in axis labels, plain ASCII. Charts write some of
        them with their own characters ("rho" as the Greek letter), see
        :mod:`coolplot.core.symbols`.
    label : str
        Human readable name used in axis labels.
    log_scale : bool
        Whether an axis showing this quantity defaults to a log scale.
    """
    key: str
    coolprop_name: Optional[str]
    humid_air_name: Optional[str]
    symbol: str
    label: str
    log_scale: bool = False


QUANTITIES = {
    q.key: q for q in (
        Quantity("T", "T", "T", "T", "Temperature"),
        Quantity("p", "P", "P", "p", "Pressure", log_scale=True),
        Quantity("h", "Hmass", "H", "h", "Specific enthalpy"),
        Quantity("s", "Smass", "S", "s", "Specific entropy"),
        Quantity("rho", "Dmass", None, "rho", "Density", log_scale=True),
        Quantity("u", "Umass", None, "u", "Specific internal energy"),
        Quantity("Q", "Q", None, "x", "Vapour quality"),
        # Humid air (per kg of dry air)
        Quantity("W", None, "W", "W", "Humidity ratio"),
        Quantity("RH", None, "R", "RH", "Relative humidity"),
        Quantity("Twb", None, "B", "Twb", "Wet-bulb temperature"),
        Quantity("Tdp", None, "D", "Tdp", "Dew-point temperature"),
        Quantity("v", None, "V", "v", "Specific volume"),
        # The temperature scale of the Mollier h,x chart: its vertical
        # coordinate, (h - r0 * W) / cp_a, read as a temperature (it equals
        # the dry-bulb temperature at W = 0). See coolplot.thermo.humid_air.
        Quantity("Thx", None, None, "T", "Temperature"),
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
    "w": "W", "rh": "RH", "twb": "Twb", "tdp": "Tdp", "V": "v",
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
