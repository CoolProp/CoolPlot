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
a tenth of a blend's). Without it, or with the native mode "off"
(:func:`coolplot.set_native_mode`, or the environment variable
``COOLPLOT_NATIVE=0``), the Python modules do the work. Both give the same
curves up to the noise of CoolProp's solvers; the Python copy stays the
reference the tests check.

What the port does not cover is left to Python here: fluids with binary
interaction parameters changed on the state (they cannot be named in a
fluid string; a mixture given as an AbstractState or a predefined blend
carries CoolProp's own values, which count as unchanged), fraction bases
other than mole (mass for incompressibles), and axes the port does not
know. The lines of constant quality of a tabular backend (BICUBIC, TTSE)
are drawn with the equation of state the tables came from, as in
:mod:`coolplot.thermo.isolines`.

The mode is read when a line is computed, and the engine's curve cache
keys curves by it, so the two implementations never share an entry.
Change the mode before building a chart, not while one is being computed.
CoolProp's released wheels up to 8.0.0 have no port, so the tests that
need it skip there and in CI.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Optional

import numpy as np

from ..core.implementation import native_mode
from .isolines import Curve, _base_backend_fluid

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
    """Whether the engine uses the port: it is available and the native mode is not "off".

    See :func:`coolplot.set_native_mode`.
    """
    return available() and native_mode() != "off"


_DEFAULT_INTERACTIONS = {}


def _interactions_are_default(backend: str, components, interactions) -> bool:
    """Whether the binary interaction parameters of a model are the ones CoolProp gives the mixture itself.

    A model made from an AbstractState or a predefined blend snapshots every
    parameter CoolProp reports; only a changed one keeps the model out of
    the port.
    """
    key = (backend, tuple(components))
    defaults = _DEFAULT_INTERACTIONS.get(key)
    if defaults is None:
        try:
            state = CoolProp.AbstractState(backend, "&".join(components))
            defaults = {}
            for i, j, name, _ in interactions:
                try:
                    defaults[(i, j, name)] = float(state.get_binary_interaction_double(i, j, name))
                except Exception:
                    pass
        except Exception:
            defaults = {}
        _DEFAULT_INTERACTIONS[key] = defaults
    return all((i, j, name) in defaults and defaults[(i, j, name)] == value for i, j, name, value in interactions)


def fluid_string(model) -> Optional[str]:
    """The CoolProp fluid string of a model key, or None when the string cannot carry the model."""
    backend, components, fractions, basis, interactions = model
    if interactions and not _interactions_are_default(backend, components, interactions):
        return None
    expected = "mass" if backend.upper().startswith("INCOMP") else "mole"
    if fractions and basis != expected:
        return None
    if fractions:
        names = "&".join("{0}[{1!r}]".format(c, float(x)) for c, x in zip(components, fractions))
    else:
        names = "&".join(components)
    return "{0}::{1}".format(backend, names) if backend else names


# The plots of the last few charts, by fluid string, the fluid's
# fingerprint (CoolProp's version, configuration and reference state: a
# plot made before set_reference_state keeps the old one), axes and T-p
# box. A PropertyPlot holds the fluid's phase envelope and critical point,
# which take as long to compute as a line of a mixture; the lines of one
# chart share them. The engine computes lines in worker processes when it
# runs in the background, so each process keeps its own.
_PLOTS = OrderedDict()
_PLOTS_KEPT = 8


def _plot(name: str, fingerprint, diagram, tp_box):
    key = (name, fingerprint, diagram.y, diagram.x, tuple(float(v) for v in tp_box))
    plot = _PLOTS.get(key)
    if plot is None:
        T_min_K, T_max_K, p_min_Pa, p_max_Pa = key[4]
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
    name = port_fluid_string(fluid, key)
    if name is None or key not in _KEYS or diagram.x not in _KEYS or diagram.y not in _KEYS:
        return None
    # The engine's axis ranges (the stepping's measure) are not passed: the
    # port computes them from the corners of the T-p box exactly as
    # coolplot.thermo.limits.property_range_SI does, and clamps the box to
    # the equation of state as resolve_tp_box does.
    try:
        plot = _plot(name, fluid.fingerprint, diagram, tp_box)
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
    except (AttributeError, TypeError):
        return None   # a port of another vintage, without this part of the API: Python does it


def port_fluid_string(fluid, key: str) -> Optional[str]:
    """The fluid string the port gets for a line of constant ``key`` of a Fluid, or None.

    The lines of constant quality of a tabular backend come from the
    equation of state behind the tables.
    """
    if key == "Q":
        fluid = _base_backend_fluid(fluid)
    return fluid_string(fluid.model_key)
