# -*- coding: utf-8 -*-
"""Events from a backend back to the application, as plain data.

Coordinates are in display units (the units of the diagram's axes), so an
application handles events the same way whatever backend produced them.
``item_id`` names the scene item under the pointer (the topmost one), or
is None; ``index`` is the point of that item (for example which state of
a cycle) or None.

This module is plain data: no CoolProp, no plotting library.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Union


@dataclass(frozen=True)
class Hover:
    """The pointer moved to (x, y) without a button pressed."""
    x: float
    y: float
    item_id: Optional[str] = None
    index: Optional[int] = None


@dataclass(frozen=True)
class Click:
    """A button was pressed and released without moving in between."""
    x: float
    y: float
    item_id: Optional[str] = None
    index: Optional[int] = None
    button: int = 1


@dataclass(frozen=True)
class DragStart:
    """A button was pressed on point ``index`` of a marker item."""
    item_id: str
    index: int
    x: float
    y: float


@dataclass(frozen=True)
class Drag:
    """The pointer moved with the button still pressed."""
    item_id: str
    index: int
    x: float
    y: float


@dataclass(frozen=True)
class DragEnd:
    """The button was released after a drag."""
    item_id: str
    index: int
    x: float
    y: float


@dataclass(frozen=True)
class ViewChanged:
    """The user zoomed or panned in the backend; the new visible limits."""
    x_limits: Tuple[float, float]
    y_limits: Tuple[float, float]


@dataclass(frozen=True)
class Resized:
    """The plot area changed its size, in points."""
    width_pt: float
    height_pt: float


Event = Union[Hover, Click, DragStart, Drag, DragEnd, ViewChanged, Resized]
