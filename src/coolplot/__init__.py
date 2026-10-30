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
from typing import TYPE_CHECKING, Any

from .__version__ import __version__  # noqa: F401

if TYPE_CHECKING:
    # The same names as in _LAZY below, imported for type checkers only, so
    # that they see the real classes and functions behind the lazy loading
    # (tests/test_typing.py checks that the two lists agree). "X as X" marks
    # a name as part of the package's API for checkers in strict mode.
    from .chart import Chart as Chart
    from .core.cycle import Cycle as Cycle, StateInput as StateInput
    from .core.diagram_type import DiagramType as DiagramType
    from .core.errors import PropertyError as PropertyError
    from .core.implementation import native_mode as native_mode, set_native_mode as set_native_mode
    from .core.limits import Region as Region, Relative as Relative, TpLimits as TpLimits
    from .core.state import StatePoint as StatePoint
    from .core.units import (ENGINEERING as ENGINEERING, IP as IP, KSI as KSI, SI as SI, Unit as Unit,
                             UnitSystem as UnitSystem)
    from .diagram import PropertyDiagram as PropertyDiagram
    from .engine import Engine as Engine
    from .export import save_pdf as save_pdf
    from .psychrometric import PsychrometricChart as PsychrometricChart
    from .scene import Scene as Scene
    from .spec import (BrandingSettings as BrandingSettings, CalcSettings as CalcSettings, CycleSpec as CycleSpec,
                       DiagramSpec as DiagramSpec, FluidSpec as FluidSpec, HumidAirSpec as HumidAirSpec,
                       IsolineSet as IsolineSet, LabelSettings as LabelSettings, LineSpec as LineSpec,
                       PageSettings as PageSettings, ProcessSpec as ProcessSpec, Settings as Settings)
    from .style.theme import Theme as Theme, get_theme as get_theme
    from .style.values import (AxesStyle as AxesStyle, Font as Font, LegendStyle as LegendStyle,
                               LineStyle as LineStyle, MarkerStyle as MarkerStyle, TextStyle as TextStyle)
    from .thermo import Fluid as Fluid, process_path as process_path, state_point as state_point

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
    "LineSpec": ".spec",
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


if not TYPE_CHECKING:
    # Hidden from type checkers: for them a module with __getattr__ has every
    # name, and a misspelt one would pass unnoticed. They read the imports above.
    def __getattr__(name: str) -> Any:
        if name == "EUR":   # the old name of ENGINEERING, warns until 2.0 (see core.units)
            from .core.units import _old_eur
            return _old_eur(2)
        if name in _LAZY:
            import importlib
            module = importlib.import_module(_LAZY[name], __name__)
            return getattr(module, name)
        raise AttributeError("module 'coolplot' has no attribute '{0}'".format(name))
