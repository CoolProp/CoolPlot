# -*- coding: utf-8 -*-
"""Tick positions for backends that place ticks themselves (SVG, plotly).

Where ticks go is up to each backend; these are simple, round positions.
The text of every tick label is central, see
:func:`coolplot.core.numbers.format_number`.
"""
from __future__ import annotations

import math
from typing import List


def ticks(lo: float, hi: float, log: bool, minor: bool = False) -> List[float]:
    """Round tick positions between lo and hi (major, or minor between them)."""
    lo, hi = min(lo, hi), max(lo, hi)
    if log and lo > 0.0:
        first, last = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
        if minor:
            mantissas = tuple(float(m) for m in range(2, 10))
        else:
            mantissas = (1.0,) if last - first > 2 else (1.0, 2.0, 5.0)
        ticks = [m * 10.0 ** e for e in range(first, last + 1) for m in mantissas]
        ticks = [t for t in ticks if lo <= t <= hi]
        if len(ticks) >= 2 or minor:
            return ticks
        # A range inside one decade, e.g. 1.5 to 1.9 bar: round linear steps
    span = hi - lo
    if not span > 0.0:
        return [lo]
    raw_step = span / 6.0
    magnitude = 10.0 ** math.floor(math.log10(raw_step))
    step = min(m * magnitude for m in (1.0, 2.0, 5.0, 10.0) if m * magnitude >= raw_step)
    if minor:
        step /= 5.0
    start = math.ceil(lo / step) * step
    return [start + i * step for i in range(int((hi - start) / step + 1e-9) + 1)]
