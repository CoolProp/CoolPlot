# -*- coding: utf-8 -*-
"""Lines computed by CoolProp's own copy of these numerics (``CoolProp.Plot``).

CoolProp carries a C++ port of :mod:`coolplot.thermo.isolines`,
:mod:`coolplot.thermo.tracer` and :mod:`coolplot.thermo.stepping` as
``CoolProp::Plot`` (src/CoolPropPlot.cpp), exposed to Python as
``CoolProp.CoolProp.Plot`` (the legacy ``CoolProp.Plots`` package is the
old plotting code, not this). When the installed CoolProp has it, the engine computes
its isolines there: the same algorithm, point for point, with the GIL
released while it runs (the time of a chart is mostly CoolProp's own
solvers, so the gain is the Python overhead: half of a pure-fluid chart,
a tenth of a blend's). Without it, or with the environment variable
``COOLPLOT_NATIVE=0``, the Python modules do the work. Both give the same
curves up to the noise of CoolProp's solvers; the Python copy stays the
reference the tests check.

What the port does not cover is left to Python here: fluids with binary
interaction parameters set on the state (they cannot be named in a fluid
string), fraction bases other than mole (mass for incompressibles), and
axes the port does not know.
"""
from __future__ import annotations

import os
from collections import OrderedDict
from typing import Optional

import numpy as np

from .isolines import Curve

try:
    import CoolProp
    from CoolProp.CoolProp import Plot as _Plot
except Exception:   # CoolProp without the port, or no CoolProp at all
    _Plot = None

# Quantity keys of coolplot mapped to CoolProp's parameters
_KEYS = {}
if _Plot is not None:
    _KEYS = {"T": CoolProp.iT, "p": CoolProp.iP, "h": CoolProp.iHmass, "s": CoolProp.iSmass,
             "rho": CoolProp.iDmass, "u": CoolProp.iUmass, "Q": CoolProp.iQ}


def available() -> bool:
    """Whether the installed CoolProp carries ``CoolProp.CoolProp.Plot``."""
    return _Plot is not None and hasattr(_Plot, "PropertyPlot")


def enabled() -> bool:
    """Whether the engine uses the port: it is available and ``COOLPLOT_NATIVE`` is not "0"."""
    return available() and os.environ.get("COOLPLOT_NATIVE", "1").strip().lower() not in ("0", "false", "no", "off")


def fluid_string(model) -> Optional[str]:
    """The CoolProp fluid string of a model key, or None when the string cannot carry the model."""
    backend, components, fractions, basis, interactions = model
    if interactions:
        return None
    expected = "mass" if backend.upper().startswith("INCOMP") else "mole"
    if fractions and basis != expected:
        return None
    if fractions:
        names = "&".join("{0}[{1!r}]".format(c, float(x)) for c, x in zip(components, fractions))
    else:
        names = "&".join(components)
    return "{0}::{1}".format(backend, names) if backend else names


# The plots of the last few charts, by fluid string, axes and T-p box. A
# PropertyPlot holds the fluid's phase envelope and critical point, which
# take as long to compute as a line of a mixture; the lines of one chart
# share them. The engine computes lines in worker processes when it runs
# in the background, so each process keeps its own.
_PLOTS = OrderedDict()
_PLOTS_KEPT = 8


def _plot(name: str, diagram, tp_box):
    key = (name, diagram.y, diagram.x, tuple(float(v) for v in tp_box))
    plot = _PLOTS.get(key)
    if plot is None:
        T_min_K, T_max_K, p_min_Pa, p_max_Pa = key[3]
        plot = _Plot.PropertyPlot(name, _KEYS[diagram.y], _KEYS[diagram.x], T_min_K, T_max_K, p_min_Pa, p_max_Pa)
        _PLOTS[key] = plot
        while len(_PLOTS) > _PLOTS_KEPT:
            _PLOTS.popitem(last=False)
    return plot


def compute_curve(fluid, diagram, key: str, value_SI: float, tp_box, points: int, solver: str, margin: float,
                  spacing: str) -> Optional[Curve]:
    """One line through ``CoolProp.Plot``, or None when the port cannot compute it.

    The arguments are those of :func:`coolplot.thermo.provider.compute_curve`.
    None means the Python numerics have to do it (an axis or a model the
    port does not take); an error of the port itself is raised as the
    ValueError CoolProp reports.
    """
    if not available():
        return None
    name = fluid_string(fluid.model_key)
    if name is None or key not in _KEYS or diagram.x not in _KEYS or diagram.y not in _KEYS:
        return None
    plot = _plot(name, diagram, tp_box)
    settings = _Plot.CalcSettings()
    settings.points = int(points)
    settings.saturation_points = int(points)
    settings.solver = solver
    settings.critical_margin = float(margin)
    settings.saturation_spacing = spacing
    line = plot.calc_isolines(_KEYS[key], [float(value_SI)], settings)[0]
    return Curve(np.array(line.x, dtype=float), np.array(line.y, dtype=float), n_failed=line.n_failed,
                 n_fallback=line.n_fallback, n_inserted=line.n_inserted, method=line.method, reason=line.reason,
                 n_evaluated=line.n_evaluated, n_outside=line.n_outside)
