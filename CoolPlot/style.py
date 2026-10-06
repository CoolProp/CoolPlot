# -*- coding: utf-8 -*-
"""Default looks for the elements of a property plot.

A theme maps the kind of element (an isotherm, the saturation dome, a
process line) to a backend-neutral style from :mod:`CoolPlot.scene`.
Changing the theme only changes styles in the scene, so a renderer updates
colours and widths without any property calculation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

from .quantities import quantity_key
from .scene import LineStyle, MarkerStyle, TextStyle


def _default_isolines():
    return {
        "T": LineStyle(color="darkred", width=0.5),
        "p": LineStyle(color="darkcyan", width=0.5),
        "h": LineStyle(color="darkgreen", width=0.5),
        "rho": LineStyle(color="darkblue", width=0.5),
        "s": LineStyle(color="darkorange", width=0.5),
        "u": LineStyle(color="purple", width=0.5),
        "Q": LineStyle(color="black", width=0.5),
    }


@dataclass(frozen=True)
class Theme:
    """Styles for all element kinds of a property plot

    Themes are immutable; use :meth:`with_isoline_style` to derive one.
    """
    isolines: Mapping[str, LineStyle] = field(default_factory=_default_isolines, hash=False)
    saturation: LineStyle = LineStyle(color="black", width=1.0)
    isoline_label: TextStyle = TextStyle(size=7.0, background="white")
    process: LineStyle = LineStyle(color="red", width=1.5)
    process_points: MarkerStyle = MarkerStyle(shape="o", size=5.0, face_color="red", edge_color="red")

    def isoline(self, key: str) -> LineStyle:
        return self.isolines.get(quantity_key(key), LineStyle())

    def with_isoline_style(self, key: str, **changes) -> "Theme":
        """Return a copy where the style of one isoline family is modified.

        Example: theme.with_isoline_style("T", color="blue", width=1.0)
        """
        key = quantity_key(key)
        styles = dict(self.isolines)
        styles[key] = replace(styles.get(key, LineStyle()), **changes)
        return replace(self, isolines=styles)
