# -*- coding: utf-8 -*-
"""The interface every plotting backend implements.

A renderer turns a :class:`coolplot.scene.Scene` into something visible.
The base class does the bookkeeping that makes selective redrawing work:
it remembers which item it drew under which id, compares that with the
scene on every :meth:`Renderer.sync`, and calls the backend only for what
was added, changed, removed or reordered.

To support a new plotting library, subclass :class:`Renderer`, implement
the methods marked "backend hook" and "read back", and pass the
conformance kit in :mod:`coolplot.testing`. docs/contributing/writing_a_backend.md lists
every requirement. Nothing else in CoolPlot needs to change.
"""
from __future__ import annotations

import warnings

from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

from ..scene import AxesSpec, Item, Scene, items_equal

#: Optional abilities a backend can declare in ``Renderer.capabilities``.
CAPABILITIES = {
    "in_place_updates": "changed items keep their backend object (no remove and re-add)",
    "file_output": "can write a file with save(path)",
    "interactive": "draws into a live window or widget",
    "css_classes": "exposes item roles and groups as CSS classes",
    "events": "reports hover, click, drag, view changes and resizes with connect(callback)",
    "pdf_output": "save(path) writes print-ready PDF for a .pdf path: TrueType or Type 1 fonts, all embedded",
}


_branding_warned = set()   # renderer classes that already said they leave the branding out


def warn_without_branding(renderer, axes: AxesSpec):
    """Warn once per renderer (a renderer object, or a name) when the axes carry a badge or
    watermark it does not draw."""
    if axes is None or (axes.badge is None and axes.watermark is None):
        return
    name = renderer if isinstance(renderer, str) else type(renderer).__name__
    if name in _branding_warned:
        return
    _branding_warned.add(name)
    warnings.warn("{0} does not draw the badge or the watermark of the chart (BrandingSettings) and leaves them "
                  "out; the matplotlib and SVG backends draw them.".format(name), UserWarning, stacklevel=3)


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
        """Whether the sync changed anything at all."""
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
        self._callbacks: Dict[int, Callable] = {}
        self._next_token = 0
        # True while sync() runs: limit changes made by sync are not user events
        self._syncing = False

    # ------------------------------------------------------------------
    def sync(self, scene: Scene) -> SyncReport:
        """Make the output match ``scene``, touching only what changed."""
        self._syncing = True
        try:
            return self._sync(scene)
        finally:
            self._syncing = False

    def _sync(self, scene: Scene) -> SyncReport:
        report = SyncReport()
        if scene.axes != self._axes:
            self._set_axes(scene.axes)
            self._axes = scene.axes
            report.axes_changed = True

        self._sync_items(scene, report)
        self._sync_order(scene, report)
        self._sync_legend(scene, report)
        self._finish(report)
        self.last_report = report
        return report

    def _sync_items(self, scene: Scene, report: SyncReport):
        """Remove, add or update items so that the backend holds exactly the scene's."""
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

    def _sync_order(self, scene: Scene, report: SyncReport):
        order = scene.draw_order()
        if order == self._order:
            return
        # Always restack, because a new item may belong between existing
        # ones. Report it only if existing items changed their order.
        current_ids = set(scene.ids())
        kept = [i for i in self._order if i in current_ids]
        kept_ids = set(kept)
        report.reordered = [i for i in order if i in kept_ids] != kept
        self._reorder(order)
        self._order = order

    def _sync_legend(self, scene: Scene, report: SyncReport):
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

    # Events ------------------------------------------------------------
    def connect(self, callback: Callable) -> int:
        """Call ``callback(event)`` for every event (see :mod:`coolplot.core.events`).

        Returns a token for :meth:`disconnect`. Only backends with the
        "events" capability produce events.
        """
        self._next_token += 1
        self._callbacks[self._next_token] = callback
        self._start_events()
        return self._next_token

    def disconnect(self, token: int):
        """Stop calling the callback registered under ``token``."""
        self._callbacks.pop(token, None)

    def _start_events(self):
        """Hook: begin listening to the library's input events (called on connect)."""

    def _emit(self, event):
        for callback in list(self._callbacks.values()):
            callback(event)

    def plot_size_pt(self):
        """(width, height) of the plot area in points, or None if unknown.

        The diagram places isoline labels in this area; a backend that
        reports it gets labels laid out for its own page geometry.
        """
        return None

    # Read back ---------------------------------------------------------
    # These report what the backend actually drew, read from its own
    # objects (artists, SVG elements, ...) and not copied from the scene,
    # in the normalised form of coolplot.testing. They are what the
    # conformance kit checks.
    def describe_item(self, item_id: str) -> dict:
        """Read back: the item as drawn, in the normalised form of :mod:`coolplot.testing`."""
        raise NotImplementedError

    def describe_axes(self) -> dict:
        """Read back: the axes as drawn, in the normalised form of :mod:`coolplot.testing`."""
        raise NotImplementedError
