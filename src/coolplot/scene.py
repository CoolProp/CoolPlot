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
from dataclasses import dataclass, field, fields
from typing import Dict, Iterable, Iterator, Optional, Tuple

import numpy as np


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
            if not _finite_pair(direction) or direction == (0.0, 0.0):
                raise ValueError("Text {0!r}: direction has to be two finite numbers, not both zero, or None; "
                                 "got {1}.".format(self.id, self.direction))
            object.__setattr__(self, "direction", direction)


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


def _values_equal(va, vb) -> bool:
    """Field values compared by value; NaN equals NaN, so a text at NaN stays where it is."""
    if isinstance(va, np.ndarray) or isinstance(vb, np.ndarray):
        return bool(np.array_equal(va, vb, equal_nan=True))
    if isinstance(va, float) and isinstance(vb, float) and math.isnan(va) and math.isnan(vb):
        return True
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
        if lo == hi:
            lo, hi = lo / 10.0, hi * 10.0
    elif lo == hi:
        pad = abs(lo) * 0.1 or 0.5
        lo, hi = lo - pad, hi + pad
    return lo, hi


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

    def __post_init__(self):
        # Tick labels are written with coolplot.core.numbers.format_number
        # and this many significant digits, by every backend.
        if not 1 <= int(self.tick_digits) <= 12:
            raise ValueError("AxesSpec: tick_digits has to be between 1 and 12, not {0}.".format(self.tick_digits))
        object.__setattr__(self, "tick_digits", int(self.tick_digits))
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

    def __init__(self, axes: AxesSpec = None, items: Iterable[Item] = ()):
        self._axes = axes or AxesSpec()
        self._items: Dict[str, Item] = {}
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

    def __iter__(self) -> Iterator[Item]:
        return iter(list(self._items.values()))

    def __contains__(self, item_id: str) -> bool:
        return item_id in self._items

    def __getitem__(self, item_id: str) -> Item:
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
        entries = {}
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

    def put(self, item: Item) -> bool:
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

    def replace_all(self, items: Iterable[Item], axes: AxesSpec = None) -> bool:
        """Make the scene contain exactly ``items`` and nothing else.

        This is the declarative way to update a scene: describe the complete
        desired content, and the scene works out what actually changed.
        Unchanged items keep their identity. The order of ``items`` becomes
        the new drawing order.
        """
        changed = False
        if axes is not None:
            changed = self.set_axes(axes)
        new_items: Dict[str, Item] = {}
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
        return cls(axes_from_dict(data.get("axes", {})), [item_from_dict(d) for d in data.get("items", ())])


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


def item_to_dict(item: Item) -> dict:
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


def item_from_dict(data: dict) -> Item:
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
    """The record of docs/reference/contracts.md for an :class:`AxesSpec`."""
    return {"x_label": axes.x_label, "y_label": axes.y_label, "x_log": axes.x_log, "y_log": axes.y_log,
            "x_limits": None if axes.x_limits is None else list(axes.x_limits),
            "y_limits": None if axes.y_limits is None else list(axes.y_limits),
            "title": axes.title, "style": style_to_dict(axes.style), "tick_digits": axes.tick_digits}


def axes_from_dict(data: dict) -> AxesSpec:
    """An :class:`AxesSpec` from its record, see :func:`axes_to_dict`."""
    return AxesSpec(x_label=data.get("x_label", ""), y_label=data.get("y_label", ""),
                    x_log=data.get("x_log", False), y_log=data.get("y_log", False),
                    x_limits=None if data.get("x_limits") is None else tuple(data["x_limits"]),
                    y_limits=None if data.get("y_limits") is None else tuple(data["y_limits"]),
                    title=data.get("title", ""), style=style_from_dict(AxesStyle, data.get("style", {})),
                    tick_digits=data.get("tick_digits", 6))
