# -*- coding: utf-8 -*-
"""Lines of constant property, computed in SI units.

Everything here is a plain function of its inputs: a fluid, a diagram type,
the constant value and the ranges to cover. The result is a :class:`Curve`
with x and y arrays in SI units. Nothing in this module knows about units,
styles or plotting libraries, which is what allows results to be cached and
reused across unit systems and renderers.

Points that CoolProp cannot compute are kept as NaN. Renderers draw a gap
there instead of inventing data, which makes calculation problems visible.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Hashable, Tuple

import numpy as np

import CoolProp
from CoolProp import CoolProp as CP

from ..quantities import get_quantity, quantity_key
from .diagram_type import DiagramType
from .fluid import Fluid, parameter_index


@dataclass(frozen=True, eq=False)
class Curve:
    """x and y values of one line in SI units

    ``n_failed`` counts the points CoolProp could not compute; they are
    NaN in x and y.
    """
    x: np.ndarray
    y: np.ndarray
    n_failed: int = 0

    def __post_init__(self):
        for name in ("x", "y"):
            arr = np.array(getattr(self, name), dtype=float)
            arr.flags.writeable = False
            object.__setattr__(self, name, arr)

    @property
    def n_valid(self) -> int:
        return int(np.sum(np.isfinite(self.x) & np.isfinite(self.y)))


def value_grid(key: str, lo: float, hi: float, num: int) -> np.ndarray:
    """Evenly spaced values, logarithmically for quantities shown on log axes."""
    if get_quantity(key).log_scale and lo > 0.0 and hi > 0.0:
        return np.geomspace(lo, hi, num)
    return np.linspace(lo, hi, num)


def compute_isoline(fluid: Fluid, diagram: DiagramType, iso_key: str, value_SI: float,
                    tp_box: Tuple[float, float, float, float], points: int = 250) -> Curve:
    """Compute one line of constant ``iso_key`` in the axes of ``diagram``.

    The isoline quantity is held at ``value_SI`` while temperature or
    pressure (see :meth:`DiagramType.sweep_quantity`) steps through its
    range in ``tp_box`` = (T_min_K, T_max_K, p_min_Pa, p_max_Pa). Both axis
    values are read from each resulting state. Lines of constant quality
    are delegated to :func:`compute_quality_line`.
    """
    iso_key = quantity_key(iso_key)
    if iso_key == "Q":
        return compute_quality_line(fluid, diagram, value_SI, points)
    sweep_key = diagram.sweep_quantity(iso_key)
    if sweep_key is None:
        raise ValueError("Lines of constant '{0}' cannot be drawn in a {1} diagram.".format(
            iso_key, diagram.name))
    T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa = tp_box
    if sweep_key == "T":
        sweep = value_grid("T", T_lo_K, T_hi_K, points)
    else:
        sweep = value_grid("p", p_lo_Pa, p_hi_Pa, points)

    # CoolProp expects the two inputs in a fixed order for each input pair.
    # Ask once which order applies; generate_update_pair returns the values
    # in the order the pair needs them, so a zero in first place means the
    # constant goes first.
    pair, first, _ = CP.generate_update_pair(parameter_index(iso_key), 0.0,
                                             parameter_index(sweep_key), 1.0)
    constant_first = (first == 0.0)
    x_index = parameter_index(diagram.x)
    y_index = parameter_index(diagram.y)
    state = fluid.state

    x = np.full_like(sweep, np.nan)
    y = np.full_like(sweep, np.nan)
    n_failed = 0
    for i, sweep_value in enumerate(sweep):
        try:
            if constant_first:
                state.update(pair, value_SI, sweep_value)
            else:
                state.update(pair, sweep_value, value_SI)
            x[i] = state.keyed_output(x_index)
            y[i] = state.keyed_output(y_index)
        except Exception:
            n_failed += 1  # stays NaN, see the module docstring
    return Curve(x, y, n_failed)


def compute_quality_line(fluid: Fluid, diagram: DiagramType, quality: float, points: int = 250) -> Curve:
    """Line of constant vapour quality from the lowest temperature to the critical point.

    Quality 0 is the bubble line and quality 1 the dew line. The temperature
    steps get denser towards the critical point, where the line bends most.
    For pure fluids every quality line ends at the critical point, which is
    appended so that the saturation dome closes.
    """
    if not 0.0 <= quality <= 1.0:
        raise ValueError("The vapour quality has to be between 0 and 1, not {0}.".format(quality))
    T_lo_K, T_hi_K = fluid.saturation_range("T")
    u = np.linspace(0.0, 1.0, points)
    T_K = T_lo_K + (T_hi_K - T_lo_K) * (1.0 - (1.0 - u) ** 2)

    x_index = parameter_index(diagram.x)
    y_index = parameter_index(diagram.y)
    state = fluid.state
    x = np.full_like(T_K, np.nan)
    y = np.full_like(T_K, np.nan)
    n_failed = 0
    for i, T in enumerate(T_K):
        try:
            state.update(CoolProp.QT_INPUTS, quality, T)
            x[i] = state.keyed_output(x_index)
            y[i] = state.keyed_output(y_index)
        except Exception:
            n_failed += 1

    if fluid.is_pure:
        crit = fluid.critical
        x_crit, y_crit = crit.get(diagram.x, np.nan), crit.get(diagram.y, np.nan)
        if np.isfinite(x_crit) and np.isfinite(y_crit):
            x = np.append(x, x_crit)
            y = np.append(y, y_crit)
    return Curve(x, y, n_failed)


class CurveCache:
    """A bounded store of computed curves, keyed by everything they depend on

    Property calculations are the expensive part of a plot. Keeping results
    keyed by their inputs means that rebuilding a plot after a change only
    computes the lines whose inputs actually changed. When the store is
    full, the least recently used curve is dropped.

    ``hits`` and ``misses`` count how often a curve was reused or computed.
    """

    def __init__(self, max_size: int = 2000):
        self._store: "OrderedDict[Hashable, Curve]" = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def __len__(self):
        return len(self._store)

    def get_or_compute(self, key: Hashable, compute: Callable[[], Curve]) -> Curve:
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
