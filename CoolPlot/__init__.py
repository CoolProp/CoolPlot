# -*- coding: utf-8 -*-
"""CoolPlot: thermodynamic property diagrams with CoolProp as data source.

The package is organised in layers, each depending only on the ones above:

* ``quantities``, ``units``, ``scene``, ``style``: plain data, no CoolProp,
  no plotting library.
* ``thermo``: all property calculations, in SI units. Only layer that
  imports CoolProp.
* ``diagram``: :class:`PropertyDiagram`, turns user settings and cached
  calculations into a scene.
* ``render``: backends that draw a scene. ``render.mpl`` is the only module
  that imports matplotlib.

See docs/architecture.md for the reasoning.
"""
from .__version__ import __version__  # noqa: F401

# The names below are loaded on first access (PEP 562). Importing a light
# module such as CoolPlot.scene therefore does not pull in CoolProp.
_LAZY = {
    "PropertyDiagram": ".diagram",
    "Fluid": ".thermo",
    "DiagramType": ".thermo",
    "TpLimits": ".thermo",
    "Relative": ".thermo",
    "StatePoint": ".thermo",
    "state_point": ".thermo",
    "process_path": ".thermo",
    "Theme": ".style",
    "Scene": ".scene",
    "UnitSystem": ".units",
    "Unit": ".units",
    "SI": ".units",
    "KSI": ".units",
    "EUR": ".units",
}

__all__ = ["__version__"] + sorted(_LAZY)


def __getattr__(name):
    if name in _LAZY:
        import importlib
        module = importlib.import_module(_LAZY[name], __name__)
        return getattr(module, name)
    raise AttributeError("module 'CoolPlot' has no attribute '{0}'".format(name))
