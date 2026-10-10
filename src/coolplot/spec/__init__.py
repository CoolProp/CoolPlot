# -*- coding: utf-8 -*-
"""What the user asks for, as immutable data: fluid, diagram and settings.

Nothing here computes properties or draws; the spec layer imports neither
CoolProp nor a plotting library.
"""
from .diagram import DiagramSpec, IsolineSet, ProcessSpec
from .fluid import FluidSpec
from .settings import PRESETS, CalcSettings, LabelSettings, PageSettings, Settings, get_settings

__all__ = ["DiagramSpec", "IsolineSet", "ProcessSpec", "FluidSpec", "PRESETS", "CalcSettings",
           "LabelSettings", "PageSettings", "Settings", "get_settings"]
