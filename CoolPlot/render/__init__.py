# -*- coding: utf-8 -*-
"""Plotting backends.

Backends are imported explicitly so that using one never imports the
libraries of another::

    from CoolPlot.render.mpl import MatplotlibRenderer   # needs matplotlib
    from CoolPlot.render.svg import SvgRenderer          # no dependencies
"""
from .base import Renderer, SyncReport

__all__ = ["Renderer", "SyncReport"]
