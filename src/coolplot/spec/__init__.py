# -*- coding: utf-8 -*-
"""What the user asks for, as immutable data: fluid, diagram and settings.

Nothing here computes properties or draws; the spec layer imports neither
CoolProp nor a plotting library.
"""
from .diagram import CycleSpec, DiagramSpec, IsolineSet, ProcessSpec, SaturationAnchor
from .fluid import FluidSpec, HumidAirSpec
from .settings import PRESETS, CalcSettings, LabelSettings, PageSettings, Settings, get_settings

__all__ = ["CycleSpec", "DiagramSpec", "IsolineSet", "ProcessSpec", "SaturationAnchor", "FluidSpec", "HumidAirSpec", "PRESETS",
           "CalcSettings", "LabelSettings", "PageSettings", "Settings", "get_settings"]
