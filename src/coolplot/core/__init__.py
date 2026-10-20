# -*- coding: utf-8 -*-
"""Plain data used by every other layer: quantities and units.

No CoolProp and no plotting library may be imported here.
"""
from .quantities import QUANTITIES, Quantity, get_quantity, quantity_key
from .units import ENGINEERING, IP, KSI, SI, UNIT_SYSTEMS, Unit, UnitSystem, get_unit_system

__all__ = ["QUANTITIES", "Quantity", "get_quantity", "quantity_key", "ENGINEERING", "IP", "KSI", "SI",
           "UNIT_SYSTEMS", "Unit", "UnitSystem", "get_unit_system"]


def __getattr__(name):
    # EUR, the old name of ENGINEERING, warns until 2.0 (see core.units)
    if name == "EUR":
        from .units import _old_eur
        return _old_eur(2)
    raise AttributeError("module {0!r} has no attribute {1!r}".format(__name__, name))
