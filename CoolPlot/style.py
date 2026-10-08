# -*- coding: utf-8 -*-
"""Backend-neutral style values: colours, lines, markers, text and axes.

Every backend must render these values the same way; docs/backends.md lists
the exact rules and CoolPlot.render.testing checks them. To make that
possible, everything is normalised here, once, instead of in each backend:

* Colours are stored as lower-case "#rrggbb" plus a separate alpha. CSS
  colour names, "#rgb", "#rgba", "#rrggbb" and "#rrggbbaa" are accepted on input. "none" means
  no paint and is stored as None.
* All lengths (line widths, marker sizes, font sizes, dash lengths) are in
  typographic points, 1 pt = 1/72 inch. A backend that works in pixels uses
  96 px per inch, so 1 pt = 4/3 px.
* Dash patterns are resolved to explicit on/off lengths in points by
  :func:`dash_pattern_pt`, so "dashed" looks identical everywhere.

This module imports neither CoolProp nor a plotting library.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, fields, replace
from typing import Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
#: The 148 named colours of CSS Color Module Level 4.
CSS_COLORS = {
    "aliceblue": "#f0f8ff", "antiquewhite": "#faebd7", "aqua": "#00ffff", "aquamarine": "#7fffd4",
    "azure": "#f0ffff", "beige": "#f5f5dc", "bisque": "#ffe4c4", "black": "#000000",
    "blanchedalmond": "#ffebcd", "blue": "#0000ff", "blueviolet": "#8a2be2", "brown": "#a52a2a",
    "burlywood": "#deb887", "cadetblue": "#5f9ea0", "chartreuse": "#7fff00",
    "chocolate": "#d2691e", "coral": "#ff7f50", "cornflowerblue": "#6495ed", "cornsilk": "#fff8dc",
    "crimson": "#dc143c", "cyan": "#00ffff", "darkblue": "#00008b", "darkcyan": "#008b8b",
    "darkgoldenrod": "#b8860b", "darkgray": "#a9a9a9", "darkgreen": "#006400",
    "darkgrey": "#a9a9a9", "darkkhaki": "#bdb76b", "darkmagenta": "#8b008b",
    "darkolivegreen": "#556b2f", "darkorange": "#ff8c00", "darkorchid": "#9932cc",
    "darkred": "#8b0000", "darksalmon": "#e9967a", "darkseagreen": "#8fbc8f",
    "darkslateblue": "#483d8b", "darkslategray": "#2f4f4f", "darkslategrey": "#2f4f4f",
    "darkturquoise": "#00ced1", "darkviolet": "#9400d3", "deeppink": "#ff1493",
    "deepskyblue": "#00bfff", "dimgray": "#696969", "dimgrey": "#696969", "dodgerblue": "#1e90ff",
    "firebrick": "#b22222", "floralwhite": "#fffaf0", "forestgreen": "#228b22",
    "fuchsia": "#ff00ff", "gainsboro": "#dcdcdc", "ghostwhite": "#f8f8ff", "gold": "#ffd700",
    "goldenrod": "#daa520", "gray": "#808080", "green": "#008000", "greenyellow": "#adff2f",
    "grey": "#808080", "honeydew": "#f0fff0", "hotpink": "#ff69b4", "indianred": "#cd5c5c",
    "indigo": "#4b0082", "ivory": "#fffff0", "khaki": "#f0e68c", "lavender": "#e6e6fa",
    "lavenderblush": "#fff0f5", "lawngreen": "#7cfc00", "lemonchiffon": "#fffacd",
    "lightblue": "#add8e6", "lightcoral": "#f08080", "lightcyan": "#e0ffff",
    "lightgoldenrodyellow": "#fafad2", "lightgray": "#d3d3d3", "lightgreen": "#90ee90",
    "lightgrey": "#d3d3d3", "lightpink": "#ffb6c1", "lightsalmon": "#ffa07a",
    "lightseagreen": "#20b2aa", "lightskyblue": "#87cefa", "lightslategray": "#778899",
    "lightslategrey": "#778899", "lightsteelblue": "#b0c4de", "lightyellow": "#ffffe0",
    "lime": "#00ff00", "limegreen": "#32cd32", "linen": "#faf0e6", "magenta": "#ff00ff",
    "maroon": "#800000", "mediumaquamarine": "#66cdaa", "mediumblue": "#0000cd",
    "mediumorchid": "#ba55d3", "mediumpurple": "#9370db", "mediumseagreen": "#3cb371",
    "mediumslateblue": "#7b68ee", "mediumspringgreen": "#00fa9a", "mediumturquoise": "#48d1cc",
    "mediumvioletred": "#c71585", "midnightblue": "#191970", "mintcream": "#f5fffa",
    "mistyrose": "#ffe4e1", "moccasin": "#ffe4b5", "navajowhite": "#ffdead", "navy": "#000080",
    "oldlace": "#fdf5e6", "olive": "#808000", "olivedrab": "#6b8e23", "orange": "#ffa500",
    "orangered": "#ff4500", "orchid": "#da70d6", "palegoldenrod": "#eee8aa",
    "palegreen": "#98fb98", "paleturquoise": "#afeeee", "palevioletred": "#db7093",
    "papayawhip": "#ffefd5", "peachpuff": "#ffdab9", "peru": "#cd853f", "pink": "#ffc0cb",
    "plum": "#dda0dd", "powderblue": "#b0e0e6", "purple": "#800080", "rebeccapurple": "#663399",
    "red": "#ff0000", "rosybrown": "#bc8f8f", "royalblue": "#4169e1", "saddlebrown": "#8b4513",
    "salmon": "#fa8072", "sandybrown": "#f4a460", "seagreen": "#2e8b57", "seashell": "#fff5ee",
    "sienna": "#a0522d", "silver": "#c0c0c0", "skyblue": "#87ceeb", "slateblue": "#6a5acd",
    "slategray": "#708090", "slategrey": "#708090", "snow": "#fffafa", "springgreen": "#00ff7f",
    "steelblue": "#4682b4", "tan": "#d2b48c", "teal": "#008080", "thistle": "#d8bfd8",
    "tomato": "#ff6347", "turquoise": "#40e0d0", "violet": "#ee82ee", "wheat": "#f5deb3",
    "white": "#ffffff", "whitesmoke": "#f5f5f5", "yellow": "#ffff00", "yellowgreen": "#9acd32",
}

_HEX = re.compile(r"^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$")


def parse_color(value) -> Tuple[Optional[str], float]:
    """Normalise a colour to ("#rrggbb", alpha); "none" gives (None, 0.0).

    Raises ValueError for anything that is not a CSS colour name or a hex
    code, so a typo in a theme fails when the theme is built and not later
    in one backend only.
    """
    if value is None:
        return None, 0.0
    text = str(value).strip().lower()
    if text in ("none", "transparent"):
        return None, 0.0
    if text in CSS_COLORS:
        return CSS_COLORS[text], 1.0
    match = _HEX.match(text)
    if not match:
        raise ValueError("Unknown colour {0!r}; use a CSS colour name or #rrggbb.".format(value))
    digits = match.group(1)
    if len(digits) in (3, 4):
        digits = "".join(c * 2 for c in digits)
    alpha = 1.0
    if len(digits) == 8:
        alpha = int(digits[6:], 16) / 255.0
        digits = digits[:6]
    return "#" + digits, alpha


def _check_alpha(alpha: float, owner: str) -> float:
    alpha = float(alpha)
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("{0}: alpha has to be between 0 and 1, not {1}.".format(owner, alpha))
    return alpha


def _check_length(value: float, owner: str, name: str) -> float:
    value = float(value)
    if not value >= 0.0:
        raise ValueError("{0}: {1} has to be zero or positive, not {2}.".format(owner, name, value))
    return value


class _Normalising:
    """Mixin for frozen style dataclasses that normalise their colours.

    Fields whose name ends in "color" are parsed with :func:`parse_color`.
    An alpha given inside the colour ("#ff000080") is multiplied into the
    alpha field if there is one, so backends only ever see "#rrggbb".
    """

    def _normalise_colors(self, owner: str):
        for f in fields(self):
            if not f.name.endswith("color"):
                continue
            hex_color, alpha = parse_color(getattr(self, f.name))
            object.__setattr__(self, f.name, hex_color)
            if hex_color is not None and alpha < 1.0 and hasattr(self, "alpha") and f.name == "color":
                object.__setattr__(self, "alpha", self.alpha * alpha)

    def with_(self, **changes):
        """Copy with some fields changed, e.g. style.with_(color="red")."""
        return replace(self, **changes)


# ---------------------------------------------------------------------------
# Lines
# ---------------------------------------------------------------------------
#: Named dash patterns as multiples of the line width (matplotlib's values).
DASH_NAMES = {
    "solid": (),
    "dashed": (3.7, 1.6),
    "dotted": (1.0, 1.65),
    "dashdot": (6.4, 1.6, 1.0, 1.6),
}

Dash = Union[str, Tuple[float, ...]]


def dash_pattern_pt(dash: Dash, width_pt: float) -> Tuple[float, ...]:
    """Explicit on/off lengths in points; () means a solid line.

    A named pattern scales with the line width, but never below the width
    of a 1 pt line, so thin isolines still get visible dashes. A tuple is
    taken as explicit lengths in points and is not scaled.
    """
    if isinstance(dash, str):
        scale = max(float(width_pt), 1.0)
        return tuple(round(v * scale, 6) for v in DASH_NAMES[dash])
    return tuple(float(v) for v in dash)


@dataclass(frozen=True)
class LineStyle(_Normalising):
    """How a line looks

    casing_color and casing_width_pt draw a band of that colour on
    both sides of the line, underneath it. With the background colour this
    separates an important line (a cycle, the saturation dome) from the
    isolines it crosses.
    """
    color: Optional[str] = "black"
    width_pt: float = 1.0
    dash: Dash = "solid"
    alpha: float = 1.0
    cap: str = "butt"            # "butt", "round" or "square"
    join: str = "round"          # "miter", "round" or "bevel"
    casing_color: Optional[str] = None
    casing_width_pt: float = 0.0

    def __post_init__(self):
        self._normalise_colors("LineStyle")
        _check_length(self.width_pt, "LineStyle", "width_pt")
        _check_length(self.casing_width_pt, "LineStyle", "casing_width_pt")
        object.__setattr__(self, "alpha", _check_alpha(self.alpha, "LineStyle"))
        if isinstance(self.dash, str):
            if self.dash not in DASH_NAMES:
                raise ValueError("Unknown dash {0!r}, expected one of {1} or a tuple of lengths "
                                 "in points.".format(self.dash, sorted(DASH_NAMES)))
        else:
            dash = tuple(float(v) for v in self.dash)
            if len(dash) % 2 or any(v < 0.0 for v in dash) or (dash and sum(dash) <= 0.0):
                raise ValueError("A dash tuple needs an even number of non-negative lengths.")
            object.__setattr__(self, "dash", dash)
        if self.cap not in ("butt", "round", "square"):
            raise ValueError("Unknown line cap {0!r}.".format(self.cap))
        if self.join not in ("miter", "round", "bevel"):
            raise ValueError("Unknown line join {0!r}.".format(self.join))

    @property
    def dash_pt(self) -> Tuple[float, ...]:
        return dash_pattern_pt(self.dash, self.width_pt)


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------
#: Supported marker shapes. Every backend has to draw all of them.
MARKER_SHAPES = {
    "o": "circle",
    "s": "square",
    "^": "triangle pointing up",
    "v": "triangle pointing down",
    "D": "diamond",
    "x": "diagonal cross",
    "+": "plus",
}


@dataclass(frozen=True)
class MarkerStyle(_Normalising):
    """How individual points look

    size_pt is the width of the marker's bounding box. face_color
    None gives a hollow marker. The cross shapes "x" and "+" have no face;
    they are drawn with the edge colour.
    """
    shape: str = "o"
    size_pt: float = 6.0
    face_color: Optional[str] = "black"
    edge_color: Optional[str] = "black"
    edge_width_pt: float = 1.0
    alpha: float = 1.0

    def __post_init__(self):
        self._normalise_colors("MarkerStyle")
        if self.shape not in MARKER_SHAPES:
            raise ValueError("Unknown marker shape {0!r}, expected one of {1}.".format(
                self.shape, sorted(MARKER_SHAPES)))
        _check_length(self.size_pt, "MarkerStyle", "size_pt")
        _check_length(self.edge_width_pt, "MarkerStyle", "edge_width_pt")
        object.__setattr__(self, "alpha", _check_alpha(self.alpha, "MarkerStyle"))


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------
#: Families every backend has to resolve to an installed font.
GENERIC_FONTS = ("sans-serif", "serif", "monospace")


@dataclass(frozen=True)
class Font:
    """A font request: the first available family wins

    family lists font names in order of preference and should end with
    one of the generic families "sans-serif", "serif" or "monospace".
    """
    family: Tuple[str, ...] = ("DejaVu Sans", "Helvetica", "Arial", "sans-serif")
    size_pt: float = 9.0
    weight: str = "normal"       # "normal" or "bold"
    style: str = "normal"        # "normal" or "italic"

    def __post_init__(self):
        family = (self.family,) if isinstance(self.family, str) else tuple(self.family)
        if not family:
            raise ValueError("Font: give at least one family.")
        object.__setattr__(self, "family", family)
        _check_length(self.size_pt, "Font", "size_pt")
        if self.weight not in ("normal", "bold"):
            raise ValueError("Font weight has to be 'normal' or 'bold'.")
        if self.style not in ("normal", "italic"):
            raise ValueError("Font style has to be 'normal' or 'italic'.")

    def with_(self, **changes):
        return replace(self, **changes)


@dataclass(frozen=True)
class TextStyle(_Normalising):
    """How a text label looks

    A halo is an outline in halo_color drawn behind the glyphs. With
    the background colour it keeps a label readable where it sits on top
    of lines, without hiding them behind a box.
    """
    font: Font = field(default_factory=Font)
    color: Optional[str] = "black"
    alpha: float = 1.0
    h_align: str = "center"      # "left", "center" or "right"
    v_align: str = "center"      # "bottom", "center" or "top"
    halo_color: Optional[str] = None
    halo_width_pt: float = 0.0

    def __post_init__(self):
        self._normalise_colors("TextStyle")
        object.__setattr__(self, "alpha", _check_alpha(self.alpha, "TextStyle"))
        _check_length(self.halo_width_pt, "TextStyle", "halo_width_pt")
        if self.h_align not in ("left", "center", "right"):
            raise ValueError("Unknown horizontal alignment {0!r}.".format(self.h_align))
        if self.v_align not in ("bottom", "center", "top"):
            raise ValueError("Unknown vertical alignment {0!r}.".format(self.v_align))


# ---------------------------------------------------------------------------
# Axes and legend
# ---------------------------------------------------------------------------
LEGEND_LOCATIONS = ("upper left", "upper right", "lower left", "lower right", "outside right")


@dataclass(frozen=True)
class LegendStyle(_Normalising):
    """Whether there is a legend, where it goes and how its box looks."""
    visible: bool = True
    location: str = "outside right"
    background: Optional[str] = "white"
    frame_color: Optional[str] = None
    text: TextStyle = field(default_factory=TextStyle)

    def __post_init__(self):
        object.__setattr__(self, "background", parse_color(self.background)[0])
        self._normalise_colors("LegendStyle")
        if self.location not in LEGEND_LOCATIONS:
            raise ValueError("Unknown legend location {0!r}, expected one of {1}.".format(
                self.location, LEGEND_LOCATIONS))


@dataclass(frozen=True)
class AxesStyle(_Normalising):
    """Everything around the data: background, frame, ticks, grid, fonts

    grid_major and grid_minor are drawn only if the axes ask for a
    grid; None switches that grid level off.
    """
    background: Optional[str] = "white"
    figure_background: Optional[str] = "white"
    frame_color: Optional[str] = "black"
    frame_width_pt: float = 0.8
    tick_color: Optional[str] = "black"
    tick_length_pt: float = 3.5
    tick_width_pt: float = 0.8
    tick_direction: str = "out"  # "out" or "in"
    tick_label: TextStyle = field(default_factory=TextStyle)
    axis_label: TextStyle = field(default_factory=lambda: TextStyle(font=Font(size_pt=10.0)))
    title: TextStyle = field(default_factory=lambda: TextStyle(font=Font(size_pt=11.0, weight="bold")))
    grid_major: Optional[LineStyle] = field(default_factory=lambda: LineStyle(color="#dddddd", width_pt=0.5))
    grid_minor: Optional[LineStyle] = None
    legend: LegendStyle = field(default_factory=LegendStyle)

    def __post_init__(self):
        object.__setattr__(self, "background", parse_color(self.background)[0])
        object.__setattr__(self, "figure_background", parse_color(self.figure_background)[0])
        self._normalise_colors("AxesStyle")
        _check_length(self.frame_width_pt, "AxesStyle", "frame_width_pt")
        _check_length(self.tick_length_pt, "AxesStyle", "tick_length_pt")
        _check_length(self.tick_width_pt, "AxesStyle", "tick_width_pt")
        if self.tick_direction not in ("out", "in"):
            raise ValueError("Tick direction has to be 'out' or 'in'.")


# ---------------------------------------------------------------------------
# Conversion to and from plain dictionaries (JSON)
# ---------------------------------------------------------------------------
def style_to_dict(obj):
    """Turn a style value (or theme) into plain dicts, lists and numbers."""
    if hasattr(obj, "__dataclass_fields__"):
        return {f.name: style_to_dict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, (tuple, list)):
        return [style_to_dict(v) for v in obj]
    if isinstance(obj, dict) or hasattr(obj, "items"):
        return {k: style_to_dict(v) for k, v in obj.items()}
    return obj


def style_from_dict(cls, data):
    """Inverse of :func:`style_to_dict` for any style dataclass.

    Unknown keys raise TypeError, so a misspelt option in a saved theme
    is reported instead of silently ignored.
    """
    import typing
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for name, value in data.items():
        if name not in hints:
            raise TypeError("{0} has no field {1!r}.".format(cls.__name__, name))
        kwargs[name] = _convert(hints[name], value)
    return cls(**kwargs)


def _convert(hint, value):
    import typing
    if value is None:
        return None
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is Union:
        for arg in args:
            if arg is type(None):
                continue
            try:
                return _convert(arg, value)
            except (TypeError, ValueError, AttributeError):
                continue
        return value
    if hasattr(hint, "__dataclass_fields__"):
        if not isinstance(value, dict):
            raise TypeError("Expected a dict for {0}.".format(hint.__name__))
        return style_from_dict(hint, value)
    if origin in (tuple, Tuple):
        item = args[0] if args else None
        if item is not None and hasattr(item, "__dataclass_fields__"):
            return tuple(_convert(item, v) for v in value)
        if isinstance(value, (list, tuple)):
            return tuple(value)
        raise TypeError("Expected a list.")
    if origin is not None and getattr(origin, "__name__", "") in ("Mapping", "dict"):
        return dict(value)
    if hint is str and not isinstance(value, str):
        raise TypeError("Expected a string.")
    return value
