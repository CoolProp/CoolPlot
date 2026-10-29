# -*- coding: utf-8 -*-
"""Themes: the complete look of a property diagram in one value.

A theme maps every kind of element (an isoline family, the saturation
dome, a cycle, a label, the axes) to a style from :mod:`coolplot.style`.
The diagram resolves these styles when it builds the scene, so every
backend receives concrete, identical styles and the plot looks the same in
matplotlib, SVG or a browser.

How isoline colours are chosen
------------------------------
Isolines of different families cross each other everywhere, so any two
family colours have to stay distinguishable, also for readers with a colour
vision deficiency and in a black and white print. The default colours (red,
blue, teal) differ in hue and also step in lightness, so every pair stays
apart for each kind of colour vision deficiency and in greyscale, and each
colour has at least 3:1 contrast on the background (WCAG 2.2). Three
colours is about the most that pass these tests together. Fortunately
every diagram type offers exactly three coloured isoline families (plus
vapour quality, drawn in ink, and the rarely used internal energy).
Colours are therefore given out per diagram type: the families the diagram
offers, in the fixed order T, p, h, s, rho, u, take the palette slots one
after another. Temperature is always the first slot (red) wherever it
appears and density always the third (teal), and hiding a family never
repaints the others.

A theme can instead pin a colour to a quantity with ``isoline_colors``, as
the "classic" theme does to reproduce the old CoolProp look and the
"coolpack" theme does to reproduce the CoolPack charts of the late 1990s.

Changing the theme of a diagram only restyles items in the scene; it never
triggers a property calculation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Mapping, Optional, Sequence, Tuple, Union

from ..core.quantities import quantity_key
from .values import (AxesStyle, Dash, Font, LegendStyle, LineStyle, MarkerStyle, TextStyle,
                    opaque_color, style_from_dict, style_to_dict)

#: Where isoline labels take their colour from: "text" the colour of
#: Theme.isoline_label (ink, the default), "line" the colour of the line
#: each label belongs to.
ISOLINE_LABEL_COLORS = ("text", "line")


def _check_slot_dashes(isoline, dashes):
    """Building the styles once validates every slot dash."""
    for dash in dashes:
        isoline.with_(dash=dash)


def _pinned_colors(colors, owner: str):
    """The pinned isoline colours as a read-only mapping (None stays None),
    so that a preset cannot be changed by accident."""
    if colors is None:
        return None
    pinned = {quantity_key(k): opaque_color(v, owner, "isoline_colors") for k, v in dict(colors).items()}
    return MappingProxyType(pinned)


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
    isoline_label_color : str
        "text" (the default) draws every label in the colour of
        ``isoline_label``; "line" draws each label in the colour of its
        line, so a label is easy to match to its family. The label keeps
        its halo and its own transparency (only the colour is taken from
        the line). Light line colours (a yellow) read worse as text.
    processes : tuple of LineStyle
        Process number i (in the order they were added) uses entry i.
        After the last entry the list starts again, so give a theme at
        least as many entries as you expect processes.
    state_points : tuple of MarkerStyle
        Markers for the states of process i.
    state_number : TextStyle
        The numbers next to the states of a cycle.
    axes : AxesStyle
        Background, frame, ticks, grid, fonts and legend.
    """
    name: str = "custom"
    categorical: Tuple[str, ...] = ("#c72500", "#2d03cd", "#0ba589", "#2d004b")
    slot_dashes: Tuple[Dash, ...] = ("solid", "solid", "solid", "solid")
    isoline_colors: Optional[Mapping[str, str]] = field(default=None, hash=False)
    isoline: LineStyle = LineStyle(width_pt=0.75)
    saturation: LineStyle = LineStyle(width_pt=1.5)
    quality: LineStyle = LineStyle(width_pt=0.5)
    isoline_label: TextStyle = TextStyle(font=Font(size_pt=7.5))
    isoline_label_color: str = "text"
    processes: Tuple[LineStyle, ...] = (LineStyle(width_pt=2.0),)
    state_points: Tuple[MarkerStyle, ...] = (MarkerStyle(),)
    state_number: TextStyle = TextStyle(font=Font(size_pt=8.0, weight="bold"))
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
        object.__setattr__(self, "isoline_colors", _pinned_colors(self.isoline_colors, owner))
        if not self.processes or not self.state_points:
            raise ValueError("Theme {0!r}: give at least one process and one marker style.".format(self.name))
        object.__setattr__(self, "processes", tuple(self.processes))
        object.__setattr__(self, "state_points", tuple(self.state_points))
        _check_slot_dashes(self.isoline, self.slot_dashes)
        if self.isoline_label_color not in ISOLINE_LABEL_COLORS:
            raise ValueError("{0}: isoline_label_color is one of {1}, not {2!r}.".format(
                owner, ISOLINE_LABEL_COLORS, self.isoline_label_color))

    # Resolution -------------------------------------------------------------
    def isoline_style(self, key: str, families: Sequence[str]) -> LineStyle:
        """Style of the isolines of ``key`` in a diagram offering ``families``.

        ``families`` is the ordered list from
        :meth:`coolplot.thermo.DiagramType.supported_isolines` without "Q".
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
        """The line style of the ``index``-th process or cycle, cycling through the theme's colours."""
        return self.processes[index % len(self.processes)]

    def state_point_style(self, index: int) -> MarkerStyle:
        """The marker style of the ``index``-th process or cycle."""
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
        """A theme from its record (docs/how_to/themes.md)."""
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
    Text uses ink colours, not series colours (isoline_label_color="line"
    in a derived theme gives labels the colours of their lines).
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
        state_number=TextStyle(font=_sans(8.0, weight="bold"), color=ink, halo_color=surface, halo_width_pt=2.0),
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
            legend=LegendStyle(location="auto", background=surface,
                               text=TextStyle(font=_sans(8.0), color=ink_secondary)),
        ),
    )


#: Light screen theme. Red isotherms, blue isentropes, teal isochores (on
#: a log(p)-h chart): hues that also step in lightness (blue dark, red
#: middle, teal light), so that every pair stays apart for each kind of
#: colour vision deficiency and in greyscale (worst pair 14.6 in OKLab x100,
#: 32.3 for normal vision), each with at least 3:1 contrast on the surface.
#: The fourth slot (aubergine) is for internal energy.
#: docs/explanation/theme_catalog.md has all the numbers.
DEFAULT = _screen_theme(
    "default", surface="#fcfcfb", ink="#0b0b0b", ink_secondary="#52514e", ink_muted="#898781",
    gridline="#e1e0d9", baseline="#c3c2b7",
    categorical=("#c72500", "#2d03cd", "#0ba589", "#2d004b"))

#: The same families on a dark surface: coral, blue and aqua, stepped in
#: lightness the other way round (blue dark, coral middle, aqua light) and
#: checked there in the same way (worst pair 15.8).
DARK = _screen_theme(
    "dark", surface="#1a1a19", ink="#ffffff", ink_secondary="#c3c2b7", ink_muted="#898781",
    gridline="#2c2c2a", baseline="#383835",
    categorical=("#ee7a5a", "#3a66d0", "#7ee6d2", "#ffff78"))

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
                    "s": "darkorange", "u": "purple", "Twb": "darkred", "v": "darkblue"},
    isoline=LineStyle(width_pt=0.5),
    saturation=LineStyle(color="black", width_pt=1.0),
    quality=LineStyle(color="black", width_pt=0.5),
    isoline_label=TextStyle(font=Font(size_pt=7.0), halo_color="white", halo_width_pt=1.5),
    processes=(LineStyle(color="red", width_pt=1.5),),
    state_points=(MarkerStyle(shape="o", size_pt=5.0, face_color="red", edge_color="red"),),
    state_number=TextStyle(font=Font(size_pt=8.0), color="red", halo_color="white", halo_width_pt=1.5),
    axes=AxesStyle(grid_major=None, legend=LegendStyle(visible=False)),
)

def _serif(size_pt, **kwargs):
    return Font(family=("Times New Roman", "Times", "Liberation Serif", "Nimbus Roman", "DejaVu Serif", "serif"),
                size_pt=size_pt, **kwargs)


#: The look of the log(p),h-diagrams of CoolPack (DTU, "Refrigeration
#: Utilities", 1996-2001): Times on white, a dense light grey grid (major
#: and minor ticks alike), a black saturation curve, red isotherms, blue
#: isentropes, green isochores and navy lines of constant quality, every
#: label in the colour of its line and no legend. Taken from the R290
#: chart in the CoolPack tutorial; the colours are those of the 16 colour
#: Windows palette. The tutorial shows neither a cycle nor isobars and
#: isenthalps, so the cycle style (black, square markers), purple isobars
#: and magenta isenthalps are chosen, not copied.
COOLPACK = Theme(
    name="coolpack",
    categorical=("#000000",),
    isoline_colors={"T": "#ff0000", "s": "#0000ff", "rho": "#008000", "v": "#008000", "p": "#800080",
                    "h": "#ff00ff", "u": "#008080", "Twb": "#ff0000"},
    isoline=LineStyle(width_pt=0.5),
    saturation=LineStyle(color="#000000", width_pt=1.25),
    quality=LineStyle(color="#000080", width_pt=0.5),
    isoline_label=TextStyle(font=_serif(6.5), halo_color="#ffffff", halo_width_pt=1.0),
    isoline_label_color="line",
    processes=(LineStyle(color="#000000", width_pt=1.5), LineStyle(color="#800000", width_pt=1.5),
               LineStyle(color="#800080", width_pt=1.5)),
    state_points=(MarkerStyle(shape="s", size_pt=4.5, face_color="#000000", edge_color="#000000"),
                  MarkerStyle(shape="s", size_pt=4.5, face_color="#800000", edge_color="#800000"),
                  MarkerStyle(shape="s", size_pt=4.5, face_color="#800080", edge_color="#800080")),
    state_number=TextStyle(font=_serif(8.0, weight="bold"), color="#000000", halo_color="#ffffff",
                           halo_width_pt=1.5),
    axes=AxesStyle(
        frame_width_pt=0.75,
        tick_width_pt=0.75,
        tick_label=TextStyle(font=_serif(8.0)),
        axis_label=TextStyle(font=_serif(9.5)),
        title=TextStyle(font=_serif(12.0, weight="bold")),
        grid_major=LineStyle(color="#c0c0c0", width_pt=0.4),
        grid_minor=LineStyle(color="#c0c0c0", width_pt=0.4),
        legend=LegendStyle(visible=False),
    ),
)

THEMES = {t.name: t for t in (DEFAULT, DARK, PRINT, CLASSIC, COOLPACK)}


def get_theme(theme: Union[str, Theme, None]) -> Theme:
    """Accept a Theme or the name of a preset: 'default', 'dark', 'print', 'classic',
    'coolpack'."""
    if isinstance(theme, Theme):
        return theme
    if theme is None:
        return DEFAULT
    try:
        return THEMES[str(theme).lower()]
    except KeyError:
        raise ValueError("Unknown theme {0!r}, expected one of {1} or a Theme.".format(
            theme, sorted(THEMES)))
