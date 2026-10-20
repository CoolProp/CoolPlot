# -*- coding: utf-8 -*-
"""Property providers: what the engine asks of a fluid or of humid air.

A provider computes states and lines for one chart kind. Two exist:
:class:`coolplot.thermo.Fluid` (kind "fluid", a CoolProp AbstractState)
and :class:`coolplot.thermo.humid_air.HumidAir` (kind "humid_air",
HAPropsSI). The engine never looks inside them; it uses this interface:

* ``kind``: "fluid" or "humid_air", matching the chart's diagram type;
* ``name``: for messages, ``model_key``: what identifies the model;
* ``quantities``: the keys a state of this provider holds, ``inputs`` the
  keys a state may be given by;
* ``fingerprint``: what decides the numbers (the CoolProp version and
  its settings), part of every cache key;
* ``configuration_changed()``: whether the provider has to be rebuilt;
* ``state_point(key1, value1, key2, value2)``: a full StatePoint;
* ``path_kind(a, b, kind)``: how the path between two states of a cycle
  is drawn ("auto" is resolved later for fluids, humid air draws straight
  lines);
* ``has_critical_point``.

The functions here dispatch what differs between the two providers: how
the calculation domain is found and how one line is computed.
"""
from __future__ import annotations

from typing import Optional, Tuple

from ..core.quantities import quantity_key
from .fluid import Fluid
from .humid_air import HumidAir
from . import native
from .isolines import Curve, compute_isoline, compute_quality_line
from .limits import property_range_SI, resolve_tp_box


def make_provider(spec):
    """The provider for a :class:`coolplot.spec.FluidSpec` or :class:`coolplot.spec.HumidAirSpec`."""
    if getattr(spec, "kind", "fluid") == "humid_air":
        return HumidAir(spec.p_Pa)
    return Fluid(spec)


def chart_domain(provider, limits, margin: float) -> Tuple[Tuple[float, float, float, float], Tuple]:
    """(tp_box, ranges) of a chart: the T-p box in SI units and the (min,
    max) of every quantity of the provider over it, as (key, (min, max))
    pairs. Quantities whose range cannot be found are left out."""
    if provider.kind == "humid_air":
        return provider.domain(limits, margin)
    tp_box = resolve_tp_box(provider, limits, margin)
    ranges = []
    for key in provider.quantities:
        try:
            ranges.append((key, property_range_SI(provider, key, tp_box)))
        except ValueError:
            continue   # not defined for this fluid, e.g. u for some backends
    return tuple(tp_box), tuple(ranges)


def compute_curve(provider, diagram, key: str, value_SI: float, tp_box, points: int, solver: str,
                  margin: float, spacing: str, ranges=None, use_native: Optional[bool] = None) -> Curve:
    """One line of constant ``key`` for any provider.

    Lines of constant quality are traced through saturation states with
    ``spacing``; all other fluid lines are stepped through ``tp_box`` with
    the ``solver``; humid-air lines are sampled in dry-bulb temperature.
    ``ranges`` are the (key, (min, max)) pairs of :func:`chart_domain`,
    which the stepping of fluid lines measures its steps by.

    Fluid lines are computed by CoolProp's C++ port of the numerics when
    the installed CoolProp has it, see :mod:`coolplot.thermo.native`.
    ``use_native`` decides that explicitly (the engine passes the flag of
    its cache key); None asks :func:`coolplot.thermo.native.enabled`. The
    port is used only when it is installed, whatever ``use_native`` says.
    """
    key = quantity_key(key)
    if provider.kind == "humid_air":
        return provider.line(key, value_SI, tp_box, points)
    if use_native is None:
        use_native = native.enabled()
    if use_native and native.available():
        curve = native.compute_curve(provider, diagram, key, value_SI, tp_box, points, solver, margin, spacing)
        if curve is not None:
            return curve
    if key == "Q":
        return compute_quality_line(provider, diagram, value_SI, points, margin, spacing)
    return compute_isoline(provider, diagram, key, value_SI, tp_box, points, solver, margin,
                           None if ranges is None else dict(ranges))
