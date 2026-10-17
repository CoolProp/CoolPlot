# -*- coding: utf-8 -*-
"""Property providers: what the engine asks of a fluid or of humid air.

A provider computes states and lines for one chart kind. Two exist:
:class:`coolplot.thermo.Fluid` (kind "fluid", a CoolProp AbstractState)
and :class:`coolplot.thermo.humid_air.HumidAir` (kind "humid_air",
HAPropsSI). The engine never looks inside them; it uses this interface:

* ``kind``: "fluid" or "humid_air", matching the chart's diagram type;
* ``name``: for messages, ``model_key``: what identifies the model;
* ``quantities``: the keys a state of this provider holds;
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

from typing import Tuple

from ..core.quantities import quantity_key
from .fluid import Fluid
from .humid_air import HumidAir
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
                  margin: float, spacing: str) -> Curve:
    """One line of constant ``key`` for any provider.

    Lines of constant quality are traced through saturation states with
    ``spacing``; all other fluid lines are swept through ``tp_box`` with
    the ``solver``; humid-air lines are sampled in dry-bulb temperature.
    """
    key = quantity_key(key)
    if provider.kind == "humid_air":
        return provider.line(key, value_SI, tp_box, points)
    if key == "Q":
        return compute_quality_line(provider, diagram, value_SI, points, margin, spacing)
    return compute_isoline(provider, diagram, key, value_SI, tp_box, points, solver, margin)
