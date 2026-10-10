# -*- coding: utf-8 -*-
"""CoolPlot: thermodynamic property diagrams with CoolProp as data source.

The package is organised in layers; each may only use the layers listed
before it (see docs/architecture.md, section 4):

* ``core``: quantities and units, plain data.
* ``style``: style values and themes.
* ``scene``: the backend-neutral description of a plot.
* ``spec``: what the user asks for (fluid, diagram, settings) as data.
* ``thermo``: all property calculations, in SI units; the only layer that
  imports CoolProp.
* ``engine``: which curves are needed, computing and caching them.
* ``compose``: computed curves plus spec and settings become a scene.
* ``render``: backends that draw a scene; ``render.mpl`` is the only module
  that imports matplotlib.
* ``diagram``: :class:`PropertyDiagram`, the facade users work with.

See docs/styling.md for themes and docs/backends.md for writing a new
backend.
"""
from .__version__ import __version__  # noqa: F401

# The names below are loaded on first access (PEP 562). Importing a light
# module such as coolplot.scene therefore does not pull in CoolProp.
_LAZY = {
    "PropertyDiagram": ".diagram",
    "DiagramSpec": ".spec",
    "FluidSpec": ".spec",
    "IsolineSet": ".spec",
    "ProcessSpec": ".spec",
    "Settings": ".spec",
    "CalcSettings": ".spec",
    "LabelSettings": ".spec",
    "PageSettings": ".spec",
    "Engine": ".engine",
    "Fluid": ".thermo",
    "DiagramType": ".core.diagram_type",
    "TpLimits": ".core.limits",
    "Relative": ".core.limits",
    "StatePoint": ".core.state",
    "state_point": ".thermo",
    "process_path": ".thermo",
    "Theme": ".style.theme",
    "get_theme": ".style.theme",
    "LineStyle": ".style.values",
    "MarkerStyle": ".style.values",
    "TextStyle": ".style.values",
    "Font": ".style.values",
    "AxesStyle": ".style.values",
    "LegendStyle": ".style.values",
    "Scene": ".scene",
    "UnitSystem": ".core.units",
    "Unit": ".core.units",
    "SI": ".core.units",
    "KSI": ".core.units",
    "EUR": ".core.units",
}

__all__ = ["__version__"] + sorted(_LAZY)


def __getattr__(name):
    if name in _LAZY:
        import importlib
        module = importlib.import_module(_LAZY[name], __name__)
        return getattr(module, name)
    raise AttributeError("module 'coolplot' has no attribute '{0}'".format(name))
