# -*- coding: utf-8 -*-
"""Style values (colours, lines, markers, text, axes) and themes.

The style values are loaded eagerly. The theme names are loaded on first
access (PEP 562), so that the scene, which only needs style values, does
not depend on the theme module.
"""
from .values import (AxesStyle, CSS_COLORS, DASH_NAMES, Font, GENERIC_FONTS, LEGEND_LOCATIONS,  # noqa: F401
                     LegendStyle, LineStyle, MARKER_SHAPES, MarkerStyle, TextStyle, dash_pattern_pt,
                     opaque_color, parse_color, style_from_dict, style_to_dict)

_THEME_NAMES = ("Theme", "THEMES", "DEFAULT", "DARK", "PRINT", "COOLPACK", "get_theme")


def __getattr__(name):
    if name in _THEME_NAMES:
        from . import theme
        return getattr(theme, name)
    raise AttributeError("module 'coolplot.style' has no attribute '{0}'".format(name))
