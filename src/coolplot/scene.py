# -*- coding: utf-8 -*-
"""A backend-neutral description of what a property plot shows.

The scene is the contract between the thermodynamic side of CoolPlot and
the plotting libraries. It is a flat collection of drawable items (lines,
markers, text) plus the description of one pair of axes. All coordinates are
already converted to display units, so a renderer never needs to know about
fluids or unit systems.

Every item has a stable string ``id``. A renderer remembers which items it
has drawn and, when it synchronises with the scene again, only touches the
items whose content changed. This is what makes selective redrawing work in
interactive applications: moving one state point of a cycle changes one or
two items, and only those are sent to the plotting library.

Items are immutable. To change one, build a new item with the same id and
put it into the scene. If the new item equals the old one, the scene keeps
the old object and nothing is redrawn.

A scene can be written as plain data (:meth:`Scene.to_dict`) and read
back (:meth:`Scene.from_dict`); docs/reference/contracts.md describes that form,
which is the contract for renderers written in other languages.

This module imports neither CoolProp nor any plotting library.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, replace
from typing import Dict, Iterable, Iterator, List, Optional, Tuple, Union

import numpy as np


from .core.floats import is_zero, is_zero_array, same_number
from .core.images import Picture, load_picture
from .core.textwidth import text_width_pt
from .style.values import (AxesStyle, LineStyle, MarkerStyle, TextStyle,  # noqa: F401 (re-exported)
                           style_from_dict, style_to_dict)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
def _frozen_array(values) -> np.ndarray:
    """Return a read-only float copy, so an item cannot change behind our back.

    The array is a view on an immutable bytes object, so even setting
    ``flags.writeable = True`` fails. Scene diffing relies on this: an item
    that could change in place would never be redrawn.
    """
    data = np.ascontiguousarray(values, dtype=float).ravel()
    return np.frombuffer(data.tobytes(), dtype=float)


@dataclass(frozen=True, eq=False, kw_only=True)
class Item:
    """Fields shared by all drawable items

    Attributes
    ----------
    id : str
        Stable identifier, unique within a scene, for example "iso/T/300".
    group : str
        Items in one group are usually styled and toggled together, for
        example "iso/T" for all isotherms.
    role : str
        What the item means, independent of how it looks: "isoline",
        "saturation", "quality", "isoline_label", "process", "state_points"
        or "annotation". Backends that support external styling (CSS
        classes in SVG or HTML) expose it; see docs/contributing/writing_a_backend.md.
    legend : str, optional
        Text of a legend entry for this item. Usually only one item per
        group carries it.
    visible : bool
        Hidden items stay in the scene; a renderer only toggles visibility.
    z_order : float
        Items with a higher value are drawn on top.
    """
    id: str
    group: str = ""
    role: str = ""
    legend: Optional[str] = None
    visible: bool = True
    z_order: float = 1.0

    def __post_init__(self):
        # Backends reserve the space below zero for the grid and background.
        z = float(self.z_order)
        if not (z >= 0.0 and math.isfinite(z)):
            raise ValueError("Item '{0}': z_order has to be finite and >= 0, not {1}.".format(self.id, z))
        object.__setattr__(self, "z_order", z)


@dataclass(frozen=True, eq=False, kw_only=True)
class Line(Item):
    """A polyline in display coordinates. NaN values split it into pieces."""
    x: np.ndarray
    y: np.ndarray
    style: LineStyle = field(default_factory=LineStyle)

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, "x", _frozen_array(self.x))
        object.__setattr__(self, "y", _frozen_array(self.y))
        if self.x.shape != self.y.shape:
            raise ValueError("Line '{0}': x and y need the same length.".format(self.id))


@dataclass(frozen=True, eq=False, kw_only=True)
class Markers(Item):
    """A set of points drawn with markers and no connecting line."""
    x: np.ndarray
    y: np.ndarray
    style: MarkerStyle = field(default_factory=MarkerStyle)

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, "x", _frozen_array(self.x))
        object.__setattr__(self, "y", _frozen_array(self.y))
        if self.x.shape != self.y.shape:
            raise ValueError("Markers '{0}': x and y need the same length.".format(self.id))


@dataclass(frozen=True, eq=False, kw_only=True)
class Text(Item):
    """A text label at one point in display coordinates

    ``direction`` optionally aligns the text with a direction given in data
    coordinates, (dx, dy). The renderer turns it into an angle on screen,
    because only the renderer knows the aspect ratio and the axis scales.
    This is how labels follow the slope of an isoline.

    ``offset_pt`` shifts the text on screen by (dx, dy) points from the
    point (x, y), with y pointing up, independent of the axis scales.
    ``clip`` says whether the text is cut off at the plot area; margin
    labels sit outside it and set ``clip=False``.
    """
    x: float
    y: float
    text: str
    direction: Optional[Tuple[float, float]] = None
    style: TextStyle = field(default_factory=TextStyle)
    offset_pt: Tuple[float, float] = (0.0, 0.0)
    clip: bool = True

    def __post_init__(self):
        super().__post_init__()
        offset = tuple(float(v) for v in self.offset_pt)
        if not _finite_pair(offset):
            raise ValueError("Text {0!r}: offset_pt has to be two finite numbers.".format(self.id))
        object.__setattr__(self, "offset_pt", offset)
        object.__setattr__(self, "clip", bool(self.clip))
        if self.direction is not None:
            direction = tuple(float(v) for v in self.direction)
            if not _finite_pair(direction) or (is_zero(direction[0]) and is_zero(direction[1])):
                raise ValueError("Text {0!r}: direction has to be two finite numbers, not both zero, or None; "
                                 "got {1}.".format(self.id, self.direction))
            object.__setattr__(self, "direction", direction)


# The kinds of item a scene holds, for the annotations. Code that reads x,
# y or style of an item takes this union rather than Item, which has only
# the fields the three share.
SceneItem = Union[Line, Markers, Text]


def _finite_pair(values) -> bool:
    return len(values) == 2 and all(math.isfinite(v) for v in values)


def items_equal(a: Item, b: Item) -> bool:
    """Compare two items field by field, treating arrays by value.

    The comparison is what decides whether a renderer has to redraw an item.
    Comparing a few hundred floats is far cheaper than redrawing a line.
    """
    if a is b:
        return True
    if type(a) is not type(b):
        return False
    return all(_values_equal(getattr(a, f.name), getattr(b, f.name)) for f in fields(a))


def _is_number(v) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_))


def _same_or_both_nan(a: float, b: float) -> bool:
    return (math.isnan(a) and math.isnan(b)) or same_number(a, b)


def _values_equal(va, vb) -> bool:
    """Field values compared by value; NaN equals NaN, so a text at NaN stays where it is.

    Numbers are compared with same_number (see coolplot.core.floats), arrays
    element by element in the same way; style objects and texts with ==.
    """
    if isinstance(va, np.ndarray) or isinstance(vb, np.ndarray):
        a = np.ascontiguousarray(va, dtype=np.float64)
        b = np.ascontiguousarray(vb, dtype=np.float64)
        if a.shape != b.shape:
            return False
        both_nan = np.isnan(a) & np.isnan(b)
        both_zero = is_zero_array(a) & is_zero_array(b)
        same = (a.view(np.uint64) == b.view(np.uint64)) & ~np.isnan(a)
        return bool(np.all(both_nan | both_zero | same))
    if _is_number(va) and _is_number(vb):
        return _same_or_both_nan(float(va), float(vb))
    if isinstance(va, tuple) and isinstance(vb, tuple) and all(_is_number(v) for v in va + vb):
        return len(va) == len(vb) and all(_same_or_both_nan(float(x), float(y)) for x, y in zip(va, vb))
    return va == vb


# ---------------------------------------------------------------------------
# Axes and scene
# ---------------------------------------------------------------------------
def drawable_limits(limits, log: bool) -> Tuple[float, float]:
    """The axis limits a backend actually draws for the requested ones.

    One rule for every backend and for the label layout, so that labels
    are placed in the same frame that is drawn:

    * a log axis cannot reach zero: an upper limit at or below zero
      becomes 10, a lower limit at or below zero upper / 1000;
    * equal limits are widened, by a decade on each side of a log axis
      and by 10 % (0.5 around zero) on a linear one.
    """
    lo, hi = float(min(limits)), float(max(limits))
    if log:
        if not hi > 0.0:
            hi = 10.0
        if not lo > 0.0:
            lo = hi * 1e-3
        if same_number(lo, hi):
            lo, hi = lo / 10.0, hi * 10.0
    elif same_number(lo, hi):
        pad = abs(lo) * 0.1
        if is_zero(pad):
            pad = 0.5
        lo, hi = lo - pad, hi + pad
    return lo, hi


#: Corners of the plot area a badge can sit in.
CORNERS = ("upper left", "upper right", "lower left", "lower right")
#: Distance between the baselines of the badge lines, relative to the font size.
BADGE_LINE_HEIGHT = 1.25
#: Baseline of a badge line below the top of its line, relative to the font size.
BADGE_BASELINE = 0.95


def _pictures(value) -> Tuple[Picture, ...]:
    """Variants of one picture as a tuple; a single Picture is allowed."""
    if isinstance(value, Picture):
        value = (value,)
    pictures = tuple(value)
    if not all(isinstance(p, Picture) for p in pictures):
        raise TypeError("Expected Picture values, got {0}.".format([type(p).__name__ for p in pictures]))
    return pictures


@dataclass(frozen=True)
class Badge:
    """A box in one corner of the plot area: a logo above lines of text

    The badge says where a chart comes from: the references of the
    equation of state, the program versions, the owner's logo and a line
    of their own (see :class:`coolplot.spec.settings.BrandingSettings`).
    Like the legend, its corner and content are decided centrally. Its size
    is :meth:`size_pt`, an estimate of the text widths made with
    :mod:`coolplot.core.textwidth`; every backend draws the box at exactly
    that size, so the label layout can keep clear of it.

    Attributes
    ----------
    location : str
        One of :data:`CORNERS`.
    logo : tuple of Picture
        Variants of the same logo, in order of preference (for example the
        SVG and a PNG rendering of it); each backend draws the first one it
        can, matplotlib only PNG. Empty for no logo.
    logo_width_pt : float
        Width of the logo; its height follows from the picture.
    lines : tuple of str
        Text lines below the logo, left aligned. A line containing "\\n" is
        split into several lines.
    text : TextStyle
        Font and colour of the lines.
    background, background_alpha : str or None, float
        Fill of the box; None for no fill.
    frame_color, frame_width_pt : str or None, float
        Outline of the box; None for no outline.
    padding_pt : float
        Space between the box outline and its content.
    gap_pt : float
        Space between the logo and the first line.
    inset_pt : float
        Distance of the box from the frame of the plot area.
    """
    location: str = "lower right"
    logo: Tuple[Picture, ...] = ()
    logo_width_pt: float = 72.0
    lines: Tuple[str, ...] = ()
    text: TextStyle = field(default_factory=TextStyle)
    background: Optional[str] = "#ffffff"
    background_alpha: float = 0.85
    frame_color: Optional[str] = None
    frame_width_pt: float = 0.5
    padding_pt: float = 4.0
    gap_pt: float = 3.0
    inset_pt: float = 6.0

    def __post_init__(self):
        if self.location not in CORNERS:
            raise ValueError("Badge: location has to be one of {0}, not {1!r}.".format(CORNERS, self.location))
        object.__setattr__(self, "logo", _pictures(self.logo))
        # one entry per drawn line: the box height counts entries
        lines = (part for line in self.lines for part in str(line).replace("\r\n", "\n").split("\n"))
        object.__setattr__(self, "lines", tuple(lines))
        for name in ("logo_width_pt", "frame_width_pt", "padding_pt", "gap_pt", "inset_pt"):
            value = float(getattr(self, name))
            if not (value >= 0.0 and math.isfinite(value)):
                raise ValueError("Badge: {0} has to be finite and >= 0, not {1}.".format(name, value))
            object.__setattr__(self, name, value)
        alpha = float(self.background_alpha)
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("Badge: background_alpha has to be between 0 and 1, not {0}.".format(alpha))
        object.__setattr__(self, "background_alpha", alpha)

    @property
    def empty(self) -> bool:
        """True when there is nothing to draw."""
        return not self.logo and not self.lines

    def logo_height_pt(self) -> float:
        """Height of the logo as drawn, 0 without a logo."""
        return self.logo_width_pt * self.logo[0].aspect if self.logo else 0.0

    @property
    def line_height_pt(self) -> float:
        """Distance between the baselines of two text lines."""
        return BADGE_LINE_HEIGHT * self.text.font.size_pt

    def size_pt(self) -> Tuple[float, float]:
        """Estimated (width, height) of the box in points.

        The text widths come from :func:`coolplot.core.textwidth.text_width_pt`,
        an estimate that errs on the wide side for common sans-serif fonts
        (an unusually wide font can overflow it). The label layout keeps
        clear of this box, and the SVG and matplotlib writers draw it at
        exactly this size.
        """
        size = self.text.font.size_pt
        text_w = max((text_width_pt(line, size) for line in self.lines), default=0.0)
        content_w = max(self.logo_width_pt if self.logo else 0.0, text_w)
        content_h = self.logo_height_pt() + len(self.lines) * self.line_height_pt
        if self.logo and self.lines:
            content_h += self.gap_pt
        return content_w + 2.0 * self.padding_pt, content_h + 2.0 * self.padding_pt


@dataclass(frozen=True)
class Watermark:
    """A faint picture centred in the plot area, behind the grid and the items

    Attributes
    ----------
    picture : tuple of Picture
        Variants of the same picture, in order of preference, as for
        :attr:`Badge.logo`.
    width_pt : float
        Width as drawn; the height follows from the picture.
    opacity : float
        0 (invisible) to 1 (opaque).
    """
    picture: Tuple[Picture, ...] = ()
    width_pt: float = 200.0
    opacity: float = 0.06

    def __post_init__(self):
        object.__setattr__(self, "picture", _pictures(self.picture))
        width = float(self.width_pt)
        if not (width > 0.0 and math.isfinite(width)):
            raise ValueError("Watermark: width_pt has to be positive, not {0}.".format(width))
        object.__setattr__(self, "width_pt", width)
        opacity = float(self.opacity)
        if not 0.0 <= opacity <= 1.0:
            raise ValueError("Watermark: opacity has to be between 0 and 1, not {0}.".format(opacity))
        object.__setattr__(self, "opacity", opacity)

    def height_pt(self) -> float:
        """Height as drawn, 0 without a picture."""
        return self.width_pt * self.picture[0].aspect if self.picture else 0.0


def first_picture(variants: Tuple[Picture, ...], mimes) -> Optional[Picture]:
    """The first variant whose type is in ``mimes``, or None."""
    return next((p for p in variants if p.mime in mimes), None)


@dataclass(frozen=True)
class AxesSpec:
    """Everything about the axes that is not an item

    Limits are in display units. ``None`` lets the renderer autoscale.
    Tick positions are left to the backend, but every tick label is
    written with :func:`coolplot.core.numbers.format_number` and
    ``tick_digits`` significant digits.
    The grid is drawn when ``style.grid_major`` (or ``grid_minor``) is set,
    the legend when ``style.legend.visible`` is True and at least one item
    has a legend text.

    ``badge`` and ``watermark`` (both optional) are the branding of the
    chart: a box with a logo and text lines in one corner, and a faint
    picture behind everything in the plot area. Backends that cannot draw
    them warn once and leave them out.
    """
    x_label: str = ""
    y_label: str = ""
    x_log: bool = False
    y_log: bool = False
    x_limits: Optional[Tuple[float, float]] = None
    y_limits: Optional[Tuple[float, float]] = None
    title: str = ""
    style: AxesStyle = field(default_factory=AxesStyle)
    tick_digits: int = 6
    badge: Optional[Badge] = None
    watermark: Optional[Watermark] = None

    def __post_init__(self):
        for name, cls in (("badge", Badge), ("watermark", Watermark)):
            value = getattr(self, name)
            if value is not None and not isinstance(value, cls):
                raise TypeError("AxesSpec: {0} has to be a {1} or None.".format(name, cls.__name__))
        # Tick labels are written with coolplot.core.numbers.format_number
        # and this many significant digits, by every backend.
        if not 1 <= int(self.tick_digits) <= 12:
            raise ValueError("AxesSpec: tick_digits has to be between 1 and 12, not {0}.".format(self.tick_digits))
        object.__setattr__(self, "tick_digits", int(self.tick_digits))
        # The composer gives an "auto" legend its corner; a scene made
        # without it gets the upper right one, so that writers see a corner
        legend = getattr(self.style, "legend", None)
        if legend is not None and legend.location == "auto":
            object.__setattr__(self, "style", replace(self.style, legend=replace(legend, location="upper right")))
        # Limits are stored ascending; inverted axes are not supported.
        for name in ("x_limits", "y_limits"):
            limits = getattr(self, name)
            if limits is not None:
                lo, hi = (float(v) for v in limits)
                if not (math.isfinite(lo) and math.isfinite(hi)):
                    raise ValueError("AxesSpec: {0} have to be finite, not {1}.".format(name, limits))
                object.__setattr__(self, name, (min(lo, hi), max(lo, hi)))


class Scene:
    """An ordered collection of items plus one :class:`AxesSpec`

    The insertion order is the default drawing order for items with the
    same ``z_order``. ``revision`` increases on every effective change, so
    an application can cheaply check whether anything happened at all.
    """

    def __init__(self, axes: Optional[AxesSpec] = None, items: Iterable[SceneItem] = ()):
        self._axes = axes or AxesSpec()
        self._items: Dict[str, SceneItem] = {}
        self.revision = 0
        for item in items:
            self.put(item)

    # Read access -----------------------------------------------------------
    @property
    def axes(self) -> AxesSpec:
        """The :class:`AxesSpec` of the scene."""
        return self._axes

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[SceneItem]:
        return iter(list(self._items.values()))

    def __contains__(self, item_id: str) -> bool:
        return item_id in self._items

    def __getitem__(self, item_id: str) -> SceneItem:
        return self._items[item_id]

    def ids(self):
        """The ids of all items, in the order they were added."""
        return list(self._items)

    def draw_order(self):
        """Item ids in drawing order: by z_order, then by position in the scene."""
        ranked = sorted(enumerate(self._items.values()), key=lambda p: (p[1].z_order, p[0]))
        return [item.id for _, item in ranked]

    def legend_entries(self):
        """(text, items) pairs for the legend, in scene order (not z order).

        Items that share a legend text form one entry whose sample shows all
        of them, e.g. the line and the markers of a cycle.
        """
        entries: Dict[str, List[SceneItem]] = {}
        for item in self._items.values():
            if item.legend and item.visible:
                entries.setdefault(item.legend, []).append(item)
        return [(text, tuple(items)) for text, items in entries.items()]

    def group(self, group: str):
        """All items of one group, in drawing order."""
        return [i for i in self._items.values() if i.group == group]

    # Write access ----------------------------------------------------------
    def set_axes(self, axes: AxesSpec) -> bool:
        """Replace the axes description; returns True if it changed."""
        if axes == self._axes:
            return False
        self._axes = axes
        self.revision += 1
        return True

    def put(self, item: SceneItem) -> bool:
        """Add or replace one item; returns True if the scene changed.

        An item equal to the stored one is ignored and the stored object is
        kept, so a renderer can skip it with a cheap identity check.
        """
        old = self._items.get(item.id)
        if old is not None and items_equal(old, item):
            return False
        self._items[item.id] = item
        self.revision += 1
        return True

    def remove(self, item_id: str) -> bool:
        """Remove the item with ``item_id``; returns whether there was one."""
        if item_id not in self._items:
            return False
        del self._items[item_id]
        self.revision += 1
        return True

    def replace_all(self, items: Iterable[SceneItem], axes: Optional[AxesSpec] = None) -> bool:
        """Make the scene contain exactly ``items`` and nothing else.

        This is the declarative way to update a scene: describe the complete
        desired content, and the scene works out what actually changed.
        Unchanged items keep their identity. The order of ``items`` becomes
        the new drawing order.
        """
        changed = False
        if axes is not None:
            changed = self.set_axes(axes)
        new_items: Dict[str, SceneItem] = {}
        for item in items:
            if item.id in new_items:
                raise ValueError("Duplicate item id '{0}' in scene.".format(item.id))
            old = self._items.get(item.id)
            if old is not None and items_equal(old, item):
                new_items[item.id] = old
            else:
                new_items[item.id] = item
                changed = True
        if set(new_items) != set(self._items):
            changed = True
        if list(new_items) != list(self._items):
            changed = True
        self._items = new_items
        if changed:
            self.revision += 1
        return changed

    # Storage ---------------------------------------------------------------
    def to_dict(self, in_draw_order: bool = True) -> dict:
        """Plain data (dicts, lists, numbers, strings, None) describing the
        scene; see docs/reference/contracts.md. NaN becomes None.

        The items are in drawing order, as the contract says. With
        ``in_draw_order=False`` they are in scene order instead, which a
        writer needs to give the legend in the order of :meth:`legend_entries`;
        it sorts by z order itself (coolplot-core and the JavaScript writer do).
        """
        order = self.draw_order() if in_draw_order else self.ids()
        return {"axes": axes_to_dict(self._axes), "items": [item_to_dict(self._items[i]) for i in order]}

    @classmethod
    def from_dict(cls, data: dict) -> "Scene":
        """A scene from :meth:`to_dict` data. The items keep their order."""
        items = [item_from_dict(d) for d in data.get("items", ())]
        seen = set()
        for item in items:
            # The scene keeps one item per id: a second one would silently replace the first
            if item.id in seen:
                raise ValueError("Duplicate item id '{0}' in scene.".format(item.id))
            seen.add(item.id)
        return cls(axes_from_dict(data.get("axes", {})), items)


# ---------------------------------------------------------------------------
# Plain data
# ---------------------------------------------------------------------------
_ITEM_TYPES = {"line": Line, "markers": Markers, "text": Text}
_STYLE_TYPES = {Line: LineStyle, Markers: MarkerStyle, Text: TextStyle}


def _number(value):
    """A float for JSON: finite as it is, NaN and infinities as None."""
    return float(value) if math.isfinite(value) else None


def _numbers(values) -> list:
    return [_number(v) for v in values]


def _float(value) -> float:
    return float("nan") if value is None else float(value)


def item_to_dict(item: SceneItem) -> dict:
    """An item as plain data; ``"type"`` says which kind it is."""
    out = {"type": next(name for name, cls in _ITEM_TYPES.items() if cls is type(item)),
           "id": item.id, "group": item.group, "role": item.role, "legend": item.legend,
           "visible": item.visible, "z_order": item.z_order, "style": style_to_dict(item.style)}
    if isinstance(item, Text):
        out.update(x=_number(item.x), y=_number(item.y), text=item.text, direction=None if item.direction is None else
                   list(item.direction), offset_pt=list(item.offset_pt), clip=item.clip)
    else:
        out.update(x=_numbers(item.x), y=_numbers(item.y))
    return out


def item_from_dict(data: dict) -> SceneItem:
    """The inverse of :func:`item_to_dict`."""
    try:
        cls = _ITEM_TYPES[data["type"]]
    except KeyError:
        raise ValueError("Unknown item type {0!r}, expected one of {1}.".format(data.get("type"), sorted(_ITEM_TYPES)))
    style = style_from_dict(_STYLE_TYPES[cls], data.get("style", {}))
    common = dict(id=data["id"], group=data.get("group", ""), role=data.get("role", ""), legend=data.get("legend"),
                  visible=data.get("visible", True), z_order=data.get("z_order", 1.0), style=style)
    if cls is Text:
        direction = data.get("direction")
        return Text(x=_float(data["x"]), y=_float(data["y"]), text=data["text"],
                    direction=None if direction is None else tuple(direction),
                    offset_pt=tuple(data.get("offset_pt", (0.0, 0.0))), clip=data.get("clip", True), **common)
    return cls(x=[_float(v) for v in data["x"]], y=[_float(v) for v in data["y"]], **common)


def axes_to_dict(axes: AxesSpec) -> dict:
    """The record of docs/reference/contracts.md for an :class:`AxesSpec`.

    ``badge`` and ``watermark`` are only written when the axes have them,
    so the record of an unbranded chart is the same as before 1.2.
    """
    out = {"x_label": axes.x_label, "y_label": axes.y_label, "x_log": axes.x_log, "y_log": axes.y_log,
           "x_limits": None if axes.x_limits is None else list(axes.x_limits),
           "y_limits": None if axes.y_limits is None else list(axes.y_limits),
           "title": axes.title, "style": style_to_dict(axes.style), "tick_digits": axes.tick_digits}
    if axes.badge is not None:
        badge = axes.badge
        out["badge"] = {"location": badge.location, "logo": [p.data_uri() for p in badge.logo],
                        "logo_width_pt": badge.logo_width_pt, "lines": list(badge.lines),
                        "text": style_to_dict(badge.text), "background": badge.background,
                        "background_alpha": badge.background_alpha, "frame_color": badge.frame_color,
                        "frame_width_pt": badge.frame_width_pt, "padding_pt": badge.padding_pt,
                        "gap_pt": badge.gap_pt, "inset_pt": badge.inset_pt}
    if axes.watermark is not None:
        mark = axes.watermark
        out["watermark"] = {"picture": [p.data_uri() for p in mark.picture], "width_pt": mark.width_pt,
                            "opacity": mark.opacity}
    return out


def _pictures_from_uris(uris) -> Tuple[Picture, ...]:
    """Pictures from the ``data:`` URIs of a record; anything else is refused."""
    pictures = []
    for uri in uris:
        if not (isinstance(uri, str) and uri.startswith("data:")):
            raise ValueError("A scene record holds pictures as data: URIs, not {0!r}.".format(str(uri)[:40]))
        pictures.append(load_picture(uri))
    return tuple(pictures)


def axes_from_dict(data: dict) -> AxesSpec:
    """An :class:`AxesSpec` from its record, see :func:`axes_to_dict`."""
    badge = watermark = None
    if data.get("badge") is not None:
        b = dict(data["badge"])
        b["logo"] = _pictures_from_uris(b.get("logo", ()))
        b["lines"] = tuple(b.get("lines", ()))
        if "text" in b:
            b["text"] = style_from_dict(TextStyle, b["text"])
        badge = Badge(**b)
    if data.get("watermark") is not None:
        w = dict(data["watermark"])
        w["picture"] = _pictures_from_uris(w.get("picture", ()))
        watermark = Watermark(**w)
    return AxesSpec(x_label=data.get("x_label", ""), y_label=data.get("y_label", ""),
                    x_log=data.get("x_log", False), y_log=data.get("y_log", False),
                    x_limits=None if data.get("x_limits") is None else tuple(data["x_limits"]),
                    y_limits=None if data.get("y_limits") is None else tuple(data["y_limits"]),
                    title=data.get("title", ""), style=style_from_dict(AxesStyle, data.get("style", {})),
                    tick_digits=data.get("tick_digits", 6), badge=badge, watermark=watermark)
