# -*- coding: utf-8 -*-
"""Themes: the complete look of a property diagram in one value.

A theme maps every kind of element (an isoline family, the saturation
dome, a cycle, a label, the axes) to a style from :mod:`CoolPlot.style`.
The diagram resolves these styles when it builds the scene, so every
backend receives concrete, identical styles and the plot looks the same in
matplotlib, SVG or a browser.

How isoline colours are chosen
------------------------------
Isolines of different families cross each other everywhere, so any two
family colours have to stay distinguishable, also for readers with a colour
vision deficiency. Only three hues of the default palette pass that test
for every pair. Fortunately every diagram type offers exactly three
coloured isoline families (plus vapour quality, drawn in ink, and the
rarely used internal energy). Colours are therefore given out per diagram
type: the families the diagram offers, in the fixed order T, p, h, s, rho,
u, take the palette slots one after another. Temperature is always the
first slot wherever it appears and density always the third, and hiding a
family never repaints the others.

A theme can instead pin a colour to a quantity with ``isoline_colors``, as
the "classic" theme does to reproduce the old CoolProp look.

Changing the theme of a diagram only restyles items in the scene; it never
triggers a property calculation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Mapping, Optional, Sequence, Tuple

from .quantities import quantity_key
from .style import (AxesStyle, Dash, Font, LegendStyle, LineStyle, MarkerStyle, TextStyle,
                    opaque_color, style_from_dict, style_to_dict)


@dataclass(frozen=True)
class Theme:
    """All styles of a property diagram

    Attributes
    ----------
    name : str
        Shown in error messages and saved files.
    categorical : tuple of str
        Colours for isoline families, given out per diagram type (see the
        module docstring).
    slot_dashes : tuple of dash
        Dash pattern per slot, a second visual channel next to colour. The
        "print" theme relies on it entirely.
    isoline_colors : mapping, optional
        Pins a colour to a quantity key and overrides the slots.
    isoline : LineStyle
        Template for isolines; colour and dash are filled in per family.
    saturation : LineStyle
        The bubble and dew lines (quality 0 and 1).
    quality : LineStyle
        Lines of constant quality inside the dome.
    isoline_label : TextStyle
        Value labels on isolines.
    processes : tuple of LineStyle
        Process number i (in the order they were added) uses entry i.
        After the last entry the list starts again, so give a theme at
        least as many entries as you expect processes.
    state_points : tuple of MarkerStyle
        Markers for the states of process i.
    axes : AxesStyle
        Background, frame, ticks, grid, fonts and legend.
    """
    name: str = "custom"
    categorical: Tuple[str, ...] = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")
    slot_dashes: Tuple[Dash, ...] = ("solid", "solid", "solid", "solid")
    isoline_colors: Optional[Mapping[str, str]] = field(default=None, hash=False)
    isoline: LineStyle = LineStyle(width_pt=0.75)
    saturation: LineStyle = LineStyle(width_pt=1.5)
    quality: LineStyle = LineStyle(width_pt=0.5)
    isoline_label: TextStyle = TextStyle(font=Font(size_pt=7.5))
    processes: Tuple[LineStyle, ...] = (LineStyle(width_pt=2.0),)
    state_points: Tuple[MarkerStyle, ...] = (MarkerStyle(),)
    axes: AxesStyle = field(default_factory=AxesStyle)

    def __post_init__(self):
        owner = "Theme {0!r}".format(self.name)
        categorical = tuple(opaque_color(c, owner, "categorical") for c in self.categorical)
        if not categorical or None in categorical:
            raise ValueError("{0}: categorical needs at least one real colour.".format(owner))
        object.__setattr__(self, "categorical", categorical)
        # Dash tuples come back from JSON as lists; normalise so that themes
        # compare equal and stay hashable after a round trip.
        dashes = tuple(d if isinstance(d, str) else tuple(float(v) for v in d) for d in self.slot_dashes)
        object.__setattr__(self, "slot_dashes", dashes or ("solid",))
        if self.isoline_colors is not None:
            pinned = {quantity_key(k): opaque_color(v, owner, "isoline_colors")
                      for k, v in dict(self.isoline_colors).items()}
            # Read-only view, so a preset cannot be changed by accident.
            object.__setattr__(self, "isoline_colors", MappingProxyType(pinned))
        if not self.processes or not self.state_points:
            raise ValueError("Theme {0!r}: give at least one process and one marker style.".format(self.name))
        object.__setattr__(self, "processes", tuple(self.processes))
        object.__setattr__(self, "state_points", tuple(self.state_points))
        # Building the styles once validates every slot dash.
        for dash in self.slot_dashes:
            self.isoline.with_(dash=dash)

    # Resolution -------------------------------------------------------------
    def isoline_style(self, key: str, families: Sequence[str]) -> LineStyle:
        """Style of the isolines of ``key`` in a diagram offering ``families``.

        ``families`` is the ordered list from
        :meth:`CoolPlot.thermo.DiagramType.supported_isolines` without "Q".
        """
        key = quantity_key(key)
        families = [quantity_key(f) for f in families if quantity_key(f) != "Q"]
        slot = families.index(key) if key in families else len(families)
        dash = self.slot_dashes[slot % len(self.slot_dashes)]
        if self.isoline_colors and key in self.isoline_colors:
            color = self.isoline_colors[key]
        else:
            color = self.categorical[slot % len(self.categorical)]
        return self.isoline.with_(color=color, dash=dash)

    def process_style(self, index: int) -> LineStyle:
        return self.processes[index % len(self.processes)]

    def state_point_style(self, index: int) -> MarkerStyle:
        return self.state_points[index % len(self.state_points)]

    # Derivation and storage -----------------------------------------------
    def with_(self, **changes) -> "Theme":
        """Copy with some fields changed, e.g. theme.with_(name="mine")."""
        return replace(self, **changes)

    def with_isoline_color(self, key: str, color: str) -> "Theme":
        """Copy where one quantity has a pinned isoline colour."""
        pinned = dict(self.isoline_colors or {})
        pinned[quantity_key(key)] = color
        return replace(self, isoline_colors=pinned)

    def to_dict(self) -> dict:
        """Plain data, e.g. for json.dump. :meth:`from_dict` reverses it."""
        return style_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        return style_from_dict(cls, data)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------
def _sans(size_pt, **kwargs):
    return Font(family=("Inter", "Helvetica Neue", "Arial", "DejaVu Sans", "sans-serif"),
                size_pt=size_pt, **kwargs)


def _screen_theme(name, surface, ink, ink_secondary, ink_muted, gridline, baseline, categorical):
    """Light and dark screen themes share their structure; only colours differ.

    Isolines are thin reference lines in the categorical colours. The
    saturation dome and cycles are drawn in ink, made heavier and given a
    casing in the surface colour, so they read as the subject of the chart.
    Text always uses ink colours, never a series colour.
    """
    label = TextStyle(font=_sans(7.5), color=ink_secondary, halo_color=surface, halo_width_pt=2.0)
    return Theme(
        name=name,
        categorical=categorical,
        isoline=LineStyle(width_pt=0.75),
        saturation=LineStyle(color=ink, width_pt=1.5, casing_color=surface, casing_width_pt=1.0),
        quality=LineStyle(color=ink_muted, width_pt=0.5),
        isoline_label=label,
        processes=(
            LineStyle(color=ink, width_pt=2.0, casing_color=surface, casing_width_pt=1.5),
            LineStyle(color=ink, width_pt=2.0, dash="dashed", casing_color=surface, casing_width_pt=1.5),
            LineStyle(color=ink_secondary, width_pt=2.0, dash="dashdot", casing_color=surface,
                      casing_width_pt=1.5),
        ),
        state_points=(
            MarkerStyle(shape="o", size_pt=6.0, face_color=ink, edge_color=surface, edge_width_pt=1.0),
            MarkerStyle(shape="s", size_pt=6.0, face_color=ink, edge_color=surface, edge_width_pt=1.0),
            MarkerStyle(shape="D", size_pt=6.0, face_color=ink_secondary, edge_color=surface,
                        edge_width_pt=1.0),
        ),
        axes=AxesStyle(
            background=surface,
            figure_background=surface,
            frame_color=baseline,
            frame_width_pt=0.8,
            tick_color=baseline,
            tick_label=TextStyle(font=_sans(8.0), color=ink_secondary),
            axis_label=TextStyle(font=_sans(9.5), color=ink),
            title=TextStyle(font=_sans(11.0, weight="bold"), color=ink),
            grid_major=LineStyle(color=gridline, width_pt=0.5),
            grid_minor=None,
            legend=LegendStyle(location="outside right", background=surface,
                               text=TextStyle(font=_sans(8.0), color=ink_secondary)),
        ),
    )


#: Light screen theme. Colours come from a palette whose first three hues
#: were checked for colour vision deficiencies in every pairing, on this
#: surface (worst pair: CVD Delta E 9.2, normal vision 24.0, OKLab x100).
DEFAULT = _screen_theme(
    "default", surface="#fcfcfb", ink="#0b0b0b", ink_secondary="#52514e", ink_muted="#898781",
    gridline="#e1e0d9", baseline="#c3c2b7",
    categorical=("#2a78d6", "#eb6834", "#1baf7a", "#eda100"))

#: The same hues stepped for a dark surface and checked there.
DARK = _screen_theme(
    "dark", surface="#1a1a19", ink="#ffffff", ink_secondary="#c3c2b7", ink_muted="#898781",
    gridline="#2c2c2a", baseline="#383835",
    categorical=("#3987e5", "#d95926", "#199e70", "#c98500"))

#: Black and white for printing: families differ by dash pattern only.
PRINT = DEFAULT.with_(
    name="print",
    categorical=("#3a3a3a",),
    slot_dashes=("solid", "dashed", "dotted", "dashdot"),
    isoline=LineStyle(width_pt=0.6),
    quality=LineStyle(color="#7a7a7a", width_pt=0.4),
    axes=replace(DEFAULT.axes, background="white", figure_background="white", frame_color="black",
                 tick_color="black", grid_major=LineStyle(color="#d0d0d0", width_pt=0.4)),
)

#: The colours of the CoolProp plots before 2026, for continuity.
CLASSIC = Theme(
    name="classic",
    categorical=("black",),
    isoline_colors={"T": "darkred", "p": "darkcyan", "h": "darkgreen", "rho": "darkblue",
                    "s": "darkorange", "u": "purple"},
    isoline=LineStyle(width_pt=0.5),
    saturation=LineStyle(color="black", width_pt=1.0),
    quality=LineStyle(color="black", width_pt=0.5),
    isoline_label=TextStyle(font=Font(size_pt=7.0), halo_color="white", halo_width_pt=1.5),
    processes=(LineStyle(color="red", width_pt=1.5),),
    state_points=(MarkerStyle(shape="o", size_pt=5.0, face_color="red", edge_color="red"),),
    axes=AxesStyle(grid_major=None, legend=LegendStyle(visible=False)),
)

THEMES = {t.name: t for t in (DEFAULT, DARK, PRINT, CLASSIC)}


def get_theme(theme) -> Theme:
    """Accept a Theme or the name of a preset: 'default', 'dark', 'print', 'classic'."""
    if isinstance(theme, Theme):
        return theme
    if theme is None:
        return DEFAULT
    try:
        return THEMES[str(theme).lower()]
    except KeyError:
        raise ValueError("Unknown theme {0!r}, expected one of {1} or a Theme.".format(
            theme, sorted(THEMES)))
