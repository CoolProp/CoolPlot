# -*- coding: utf-8 -*-
"""The region of states a property plot covers.

The region is described by bounds on temperature and pressure because those
are the quantities engineers think in. The axis ranges of any diagram are
derived from these bounds by evaluating the plotted quantities at the four
corners of the T-p rectangle.

These limits define the *calculation domain*: isolines are computed inside
it. Zooming or panning in an interactive plot changes only the visible
window in the scene and does not need new property calculations.
"""
from __future__ import annotations

import math
from typing import Tuple

import numpy as np

from ..core.diagram_type import DiagramType
from ..core.limits import Relative, TpLimits
from ..core.quantities import quantity_key
from .fluid import Fluid

# Charts of humid air have a region of their own (bounds on T and W);
# coolplot.thermo.provider.chart_domain dispatches to it.


def resolve_tp_box(fluid: Fluid, limits: TpLimits, margin: float = 1e-7) -> Tuple[float, float, float, float]:
    """Absolute (T_min_K, T_max_K, p_min_Pa, p_max_Pa) for one fluid.

    Relative bounds refer to the saturation range of the fluid, see
    :meth:`Fluid.saturation_range` for ``margin``.
    """
    saturation = {}   # the saturation range of T or p, looked up only when a bound needs it

    def absolute(bound, key, end, fallback):
        if bound is None:
            return fallback
        if isinstance(bound, Relative):
            if key not in saturation:
                saturation[key] = fluid.saturation_range(key, margin)   # ValueError for incompressibles
            value = bound.factor * saturation[key][end]
        else:
            value = float(bound)
        if math.isnan(value):
            # A NaN limit, or a NaN factor of a relative one, would end in a
            # confusing "empty plotting region" below
            raise ValueError("The {0} limit of the plotting region is not a number; give a value, or None for "
                             "the limit of the equation of state.".format(key))
        return value

    T_lo_K = absolute(limits.T_min, "T", 0, 0.0)
    T_hi_K = absolute(limits.T_max, "T", 1, np.inf)
    p_lo_Pa = absolute(limits.p_min, "p", 0, 0.0)
    p_hi_Pa = absolute(limits.p_max, "p", 1, np.inf)

    # Never leave the validity range of the equation of state
    if fluid.T_min_K is not None:
        T_lo_K = max(T_lo_K, fluid.T_min_K)
    if fluid.T_max_K is not None:
        T_hi_K = min(T_hi_K, fluid.T_max_K)
    if fluid.p_min_Pa is not None:
        p_lo_Pa = max(p_lo_Pa, fluid.p_min_Pa)
    if fluid.p_max_Pa is not None:
        p_hi_Pa = min(p_hi_Pa, fluid.p_max_Pa)
    if not (T_lo_K < T_hi_K and p_lo_Pa < p_hi_Pa):
        raise ValueError("Empty plotting region T=[{0}, {1}] K, p=[{2}, {3}] Pa.".format(
            T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa))
    return T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa


def property_range_SI(fluid: Fluid, key: str, tp_box: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """Smallest and largest value of a quantity on the corners of the T-p box."""
    key = quantity_key(key)
    T_lo_K, T_hi_K, p_lo_Pa, p_hi_Pa = tp_box
    if key == "T":
        return T_lo_K, T_hi_K
    if key == "p":
        return p_lo_Pa, p_hi_Pa
    if key == "Q":
        return 0.0, 1.0
    values = []
    for T_K in (T_lo_K, T_hi_K):
        for p_Pa in (p_lo_Pa, p_hi_Pa):
            try:
                fluid.update("p", p_Pa, "T", T_K)
                values.append(fluid.get(key))
            except Exception:
                pass  # a corner outside the EOS range just does not contribute
    values = [v for v in values if np.isfinite(v)]
    if len(values) < 2:
        raise ValueError("Could not determine the range of '{0}' for {1}.".format(key, fluid.name))
    return min(values), max(values)


def axis_ranges_SI(fluid: Fluid, diagram: DiagramType, tp_box) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """((x_min, x_max), (y_min, y_max)) of a diagram in SI units."""
    return (property_range_SI(fluid, diagram.x, tp_box),
            property_range_SI(fluid, diagram.y, tp_box))
