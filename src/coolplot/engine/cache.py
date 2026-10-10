# -*- coding: utf-8 -*-
"""A bounded store for computed curves.

Part of the engine layer: it decides what is computed and keeps results,
the thermo layer only knows how to compute a single curve.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable, Hashable


class CurveCache:
    """A bounded store of computed curves, keyed by everything they depend on

    Property calculations are the expensive part of a plot. Keeping results
    keyed by their inputs means that rebuilding a plot after a change only
    computes the lines whose inputs actually changed. When the store is
    full, the least recently used curve is dropped.

    ``hits`` and ``misses`` count how often a curve was reused or computed.
    """

    def __init__(self, max_size: int = 2000):
        self._store: "OrderedDict[Hashable, Any]" = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def __len__(self):
        return len(self._store)

    def get_or_compute(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        if key in self._store:
            self._store.move_to_end(key)
            self.hits += 1
            return self._store[key]
        self.misses += 1
        curve = compute()
        self._store[key] = curve
        if len(self._store) > self.max_size:
            self._store.popitem(last=False)
        return curve

    def clear(self):
        self._store.clear()
