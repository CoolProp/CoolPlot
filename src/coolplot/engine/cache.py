# -*- coding: utf-8 -*-
"""A bounded store for computed curves, in memory and optionally on disk.

Part of the engine layer: it decides what is computed and keeps results,
the thermo layer only knows how to compute a single curve.
"""
from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any, Callable, Hashable, Optional, Union

from .store import ENVIRONMENT_VARIABLE, CurveStore


class CurveCache:
    """A bounded store of computed curves, keyed by everything they depend on

    Property calculations are the expensive part of a plot. Keeping results
    keyed by their inputs means that rebuilding a plot after a change only
    computes the lines whose inputs actually changed. When the store is
    full, the least recently used curve is dropped.

    With a ``directory`` the curves are also kept on disk
    (:class:`coolplot.engine.store.CurveStore`, the way CoolProp keeps its
    tabular data), so the next run, another process or another chart of the
    same fluid finds them there instead of tracing them again.

    Parameters
    ----------
    max_size : int
        Curves kept in memory.
    directory : str, True, False or None
        Folder of the curves on disk: a path; True for the default folder
        (~/.CoolProp/CoolPlot/Curves, or the folder ``COOLPLOT_CACHE_DIR``
        names); False for none. None (the default) keeps curves on disk
        only when ``COOLPLOT_CACHE_DIR`` names a folder ("0", "off" or an
        empty value mean none), so a script that draws one chart writes
        nothing.

    ``hits`` counts curves served from memory or disk, ``disk_hits`` those
    read from disk, and ``misses`` the curves that had to be computed.

    Examples
    --------
    >>> from coolplot import PropertyDiagram                             # doctest: +SKIP
    >>> from coolplot.engine import CurveCache                           # doctest: +SKIP
    >>> diagram = PropertyDiagram("R290", "ph", cache=CurveCache(directory=True))   # doctest: +SKIP
    """

    def __init__(self, max_size: int = 2000, directory: Union[str, bool, None] = None):
        self._store: "OrderedDict[Hashable, Any]" = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.disk_hits = 0
        if directory is None:
            directory = os.environ.get(ENVIRONMENT_VARIABLE, "").strip()
            if directory.lower() in ("", "0", "off", "false", "no"):
                directory = False
        if directory is False or directory == "":
            self.disk: Optional[CurveStore] = None
        else:
            self.disk = CurveStore(None if directory is True else str(directory))

    def __len__(self):
        return len(self._store)

    def get_or_compute(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        """The value stored under ``key``, or the result of ``compute()``, which is stored first."""
        curve = self._find(key)
        if curve is not None:
            self.hits += 1
            return curve
        self.misses += 1
        curve = compute()
        self._remember(key, curve)
        if self.disk is not None:
            self.disk.save(key, curve)
        return curve

    def peek(self, key: Hashable):
        """The curve stored for ``key`` in memory or on disk, or None; counts neither a hit nor a miss.

        A curve found counts as recently used, so curves on screen are the
        last to be dropped."""
        return self._find(key)

    def put(self, key: Hashable, curve: Any, disk: bool = True):
        """Store a curve computed elsewhere (for example in a worker); ``disk=False`` keeps it in memory only."""
        self._remember(key, curve)
        if disk and self.disk is not None:
            self.disk.save(key, curve)

    def clear(self):
        """Forget every curve kept in memory; the files on disk stay."""
        self._store.clear()

    # Internals ------------------------------------------------------------
    def _find(self, key: Hashable):
        curve = self._store.get(key)
        if curve is not None:
            self._store.move_to_end(key)
            return curve
        if self.disk is not None:
            curve = self.disk.load(key)
            if curve is not None:
                self.disk_hits += 1
                self._remember(key, curve)
        return curve

    def _remember(self, key: Hashable, curve: Any):
        self._store[key] = curve
        self._store.move_to_end(key)
        if len(self._store) > self.max_size:
            self._store.popitem(last=False)
