# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import

# This is the code forked from CoolProp 6.3. It is kept for reference until
# the new layered API (CoolPlot.PropertyDiagram, see docs/architecture.md)
# covers all of its features, and will then be removed.
import warnings as _warnings
_warnings.warn("CoolPlot.Plot is the legacy API and will be removed; use "
               "CoolPlot.PropertyDiagram instead, see docs/architecture.md.",
               DeprecationWarning, stacklevel=2)

# Bring some functions into the Plots namespace for code concision,
# but be careful not to clutter the namespace with too many
# classes and functions.

# Plotting objects and functions
from .Plots import PropertyPlot
from .Common import IsoLine

# Cycle calculation and drawing
from .SimpleCycles import StateContainer
from .SimpleCyclesExpansion import SimpleRankineCycle
from .SimpleCyclesCompression import SimpleCompressionCycle

# Old and deprecated objects
from .SimpleCycles import SimpleCycle, TwoStage, EconomizedCycle
