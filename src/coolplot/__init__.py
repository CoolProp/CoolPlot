# -*- coding: utf-8 -*-
"""CoolPlot: thermodynamic property diagrams with CoolProp as data source.

The package is organised in layers; each may only use the layers listed
before it (see docs/contributing/architecture.md, section 4):

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
* ``chart``: :class:`Chart`, the facade users work with;
  :class:`PropertyDiagram` and :class:`PsychrometricChart` are its two
  constructors.

See docs/how_to/themes.md for themes and docs/contributing/writing_a_backend.md for writing a new
backend.
"""
from .__version__ import __version__  # noqa: F401

# The names below are loaded on first access (PEP 562). Importing a light
# module such as coolplot.scene therefore does not pull in CoolProp.
_LAZY = {
    "Chart": ".chart",
    "PropertyDiagram": ".diagram",
    "PsychrometricChart": ".psychrometric",
    "HumidAirSpec": ".spec",
    "save_pdf": ".export",
    "Cycle": ".core.cycle",
    "CycleSpec": ".spec",
    "StateInput": ".core.cycle",
    "DiagramSpec": ".spec",
    "FluidSpec": ".spec",
    "IsolineSet": ".spec",
    "ProcessSpec": ".spec",
    "Settings": ".spec",
    "CalcSettings": ".spec",
    "LabelSettings": ".spec",
    "PageSettings": ".spec",
    "BrandingSettings": ".spec",
    "Engine": ".engine",
    "Fluid": ".thermo",
    "DiagramType": ".core.diagram_type",
    "TpLimits": ".core.limits",
    "Relative": ".core.limits",
    "Region": ".core.limits",
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
    "ENGINEERING": ".core.units",
    "IP": ".core.units",
    "PropertyError": ".core.errors",
    "native_mode": ".core.implementation",
    "set_native_mode": ".core.implementation",
}

__all__ = ["__version__"] + sorted(_LAZY)


def __getattr__(name):
    if name == "EUR":   # the old name of ENGINEERING, warns until 2.0 (see core.units)
        from .core.units import _old_eur
        return _old_eur(2)
    if name in _LAZY:
        import importlib
        module = importlib.import_module(_LAZY[name], __name__)
        return getattr(module, name)
    raise AttributeError("module 'coolplot' has no attribute '{0}'".format(name))
