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

This module imports neither CoolProp nor any plotting library.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Dict, Iterable, Iterator, Optional, Tuple

import numpy as np


from .style import AxesStyle, LineStyle, MarkerStyle, TextStyle  # noqa: F401 (re-exported)


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
        classes in SVG or HTML) expose it; see docs/backends.md.
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


@dataclass(frozen=True, eq=False, kw_only=True)
class Line(Item):
    """A polyline in display coordinates. NaN values split it into pieces."""
    x: np.ndarray
    y: np.ndarray
    style: LineStyle = field(default_factory=LineStyle)

    def __post_init__(self):
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
    """
    x: float
    y: float
    text: str
    direction: Optional[Tuple[float, float]] = None
    style: TextStyle = field(default_factory=TextStyle)


def items_equal(a: Item, b: Item) -> bool:
    """Compare two items field by field, treating arrays by value.

    The comparison is what decides whether a renderer has to redraw an item.
    Comparing a few hundred floats is far cheaper than redrawing a line.
    """
    if a is b:
        return True
    if type(a) is not type(b):
        return False
    for f in fields(a):
        va = getattr(a, f.name)
        vb = getattr(b, f.name)
        if isinstance(va, np.ndarray) or isinstance(vb, np.ndarray):
            if not np.array_equal(va, vb, equal_nan=True):
                return False
        elif va != vb:
            return False
    return True


# ---------------------------------------------------------------------------
# Axes and scene
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AxesSpec:
    """Everything about the axes that is not an item

    Limits are in display units. ``None`` lets the renderer autoscale.
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
