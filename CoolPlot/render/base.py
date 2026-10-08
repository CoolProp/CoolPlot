# -*- coding: utf-8 -*-
"""The interface every plotting backend implements.

A renderer turns a :class:`CoolPlot.scene.Scene` into something visible.
The base class does the bookkeeping that makes selective redrawing work:
it remembers which item it drew under which id, compares that with the
scene on every :meth:`Renderer.sync`, and calls the backend only for what
was added, changed, removed or reordered.

To support a new plotting library, subclass :class:`Renderer`, implement
the methods marked "backend hook" and "read back", and pass the
conformance kit in :mod:`CoolPlot.render.testing`. docs/backends.md lists
every requirement. Nothing else in CoolPlot needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple

from ..scene import AxesSpec, Item, Scene, items_equal

#: Optional abilities a backend can declare in ``Renderer.capabilities``.
CAPABILITIES = {
    "in_place_updates": "changed items keep their backend object (no remove and re-add)",
    "file_output": "can write a file with save(path)",
    "interactive": "draws into a live window or widget",
    "css_classes": "exposes item roles and groups as CSS classes",
}


@dataclass
class SyncReport:
    """What one call to :meth:`Renderer.sync` did, mainly for tests and profiling."""
    added: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    unchanged: int = 0
    axes_changed: bool = False
    reordered: bool = False
    legend_changed: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed or self.axes_changed
                    or self.reordered or self.legend_changed)


class Renderer:
    """Base class for all plotting backends"""

    #: Names from CAPABILITIES this backend supports.
    capabilities: FrozenSet[str] = frozenset()

    def __init__(self):
        self._drawn: Dict[str, Item] = {}
        self._order: List[str] = []
        self._axes: Optional[AxesSpec] = None
        self._legend: Tuple = ()
        self.last_report: Optional[SyncReport] = None

    # ------------------------------------------------------------------
    def sync(self, scene: Scene) -> SyncReport:
        """Make the output match ``scene``, touching only what changed."""
        report = SyncReport()
        if scene.axes != self._axes:
            self._set_axes(scene.axes)
            self._axes = scene.axes
            report.axes_changed = True

        current_ids = set(scene.ids())
        for item_id in [i for i in self._drawn if i not in current_ids]:
            self._remove(self._drawn.pop(item_id))
            report.removed.append(item_id)

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

        order = scene.draw_order()
        if order != self._order:
            # Always restack, because a new item may belong between existing
            # ones. Report it only if existing items changed their order.
            kept = [i for i in self._order if i in current_ids]
            report.reordered = [i for i in order if i in kept] != kept
            self._reorder(order)
            self._order = order

        # The legend shows a sample of each entry's style, so its signature
        # includes the styles.
        entries = scene.legend_entries()
        legend_style = scene.axes.style.legend
        signature = (tuple((text, tuple((i.id, getattr(i, "style", None)) for i in items))
                           for text, items in entries), legend_style)
        if signature != self._legend:
            self._set_legend(entries, legend_style)
            self._legend = signature
            report.legend_changed = True

        self._finish(report)
        self.last_report = report
        return report

    def clear(self):
        """Remove everything this renderer has drawn."""
        for item in list(self._drawn.values()):
            self._remove(item)
        self._drawn.clear()
        self._order = []
        self._axes = None
        if self._legend:
            self._set_legend([], None)
        self._legend = ()

    def draw_order(self) -> List[str]:
        """Ids in the order the backend was last told to draw them."""
        return list(self._order)

    # Backend hooks -----------------------------------------------------
    def _set_axes(self, axes: AxesSpec):
        """Apply labels, scales, limits and the complete AxesStyle."""
        raise NotImplementedError

    def _add(self, item: Item):
        """Create the backend object for a new item, fully styled."""
        raise NotImplementedError

    def _update(self, old: Item, new: Item):
        """Change an existing backend object. Override for in-place updates;
        the default removes the old object and adds a new one."""
        self._remove(old)
        self._add(new)

    def _remove(self, item: Item):
        """Delete the backend object of an item."""
        raise NotImplementedError

    def _reorder(self, order: List[str]):
        """Restack existing objects so they are drawn in ``order``."""
        raise NotImplementedError

    def _set_legend(self, entries, style):
        """Show a legend with (text, items) entries, or remove it if empty.

        Each entry gets one sample that overlays all its items, so a cycle
        shows its line with a marker on it.

        ``style`` is the LegendStyle; with ``style.visible`` False (or no
        entries) the legend has to disappear.
        """
        raise NotImplementedError

    def _finish(self, report: SyncReport):
        """Called once at the end of every sync, e.g. to request a repaint."""

    # Read back ---------------------------------------------------------
    # These report what the backend actually drew, read from its own
    # objects (artists, SVG elements, ...) and not copied from the scene,
    # in the normalised form of CoolPlot.render.testing. They are what the
    # conformance kit checks.
    def describe_item(self, item_id: str) -> dict:
        raise NotImplementedError

    def describe_axes(self) -> dict:
        raise NotImplementedError
