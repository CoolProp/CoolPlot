# -*- coding: utf-8 -*-
"""The interface every plotting backend implements.

A renderer turns a :class:`CoolPlot.scene.Scene` into something visible.
The base class does the bookkeeping that makes selective redrawing work:
it remembers which item it drew under which id, compares that with the
scene on every :meth:`Renderer.sync`, and calls the backend only for items
that were added, changed or removed.

To support a new plotting library, subclass :class:`Renderer` and
implement the four methods marked "backend hook". Nothing else in CoolPlot
needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..scene import AxesSpec, Item, Scene, items_equal


@dataclass
class SyncReport:
    """What one call to :meth:`Renderer.sync` did, mainly for tests and profiling."""
    added: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    unchanged: int = 0
    axes_changed: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed or self.axes_changed)


class Renderer:
    """Base class for all plotting backends"""

    def __init__(self):
        self._drawn: Dict[str, Item] = {}
        self._axes: Optional[AxesSpec] = None
        self.last_report: Optional[SyncReport] = None

    def sync(self, scene: Scene) -> SyncReport:
        """Make the output match ``scene``, touching only what changed."""
        report = SyncReport()
        if scene.axes != self._axes:
            self._set_axes(scene.axes)
            self._axes = scene.axes
            report.axes_changed = True

        for item in scene:
            old = self._drawn.get(item.id)
            if old is None:
                self._add(item)
                report.added.append(item.id)
            elif items_equal(old, item):
                report.unchanged += 1
            else:
                self._update(old, item)
                report.updated.append(item.id)
            self._drawn[item.id] = item

        current_ids = set(scene.ids())
        for item_id in [i for i in self._drawn if i not in current_ids]:
            self._remove(self._drawn.pop(item_id))
            report.removed.append(item_id)

        self._finish(report)
        self.last_report = report
        return report

    def clear(self):
        """Remove everything this renderer has drawn."""
        for item in list(self._drawn.values()):
            self._remove(item)
        self._drawn.clear()
        self._axes = None

    # Backend hooks -----------------------------------------------------
    def _set_axes(self, axes: AxesSpec):
        """Apply labels, scales and limits."""
        raise NotImplementedError

    def _add(self, item: Item):
        """Create the backend object for a new item."""
        raise NotImplementedError

    def _update(self, old: Item, new: Item):
        """Change an existing backend object. Override for in-place updates;
        the default removes the old object and adds a new one."""
        self._remove(old)
        self._add(new)

    def _remove(self, item: Item):
        """Delete the backend object of an item."""
        raise NotImplementedError

    def _finish(self, report: SyncReport):
        """Called once at the end of every sync, e.g. to request a repaint."""
