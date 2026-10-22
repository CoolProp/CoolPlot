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

import math
import warnings
from typing import Optional, Tuple, Union

from ..core.floats import same_result
from ..core.quantities import quantity_key
from .fluid import Fluid
from .humid_air import HumidAir
from . import native
from .isolines import Curve, compute_isoline, compute_quality_line
from .limits import property_range_SI, resolve_tp_box

# The two property providers (see the module docstring), for the annotations
PropertyProvider = Union[Fluid, HumidAir]


def make_provider(spec) -> PropertyProvider:
    """The provider for a :class:`coolplot.spec.FluidSpec` or :class:`coolplot.spec.HumidAirSpec`."""
    if getattr(spec, "kind", "fluid") == "humid_air":
        return HumidAir(spec.p_Pa)
    return Fluid(spec)


def same_fingerprint(a: Tuple, b: Tuple) -> bool:
    """Whether two provider fingerprints are the same.

    A fingerprint is a tuple of plain values: texts (the CoolProp version, a
    digest of its configuration) and numbers (the enthalpy and entropy of a
    probe state, the pressure of humid air). Numbers are compared as results
    of one repeated computation (:func:`coolplot.core.floats.same_result`),
    so a probe that gave NaN, such as for INCOMP::T66, matches itself; texts
    are compared with ``==``. Tuple ``==`` would compare the numbers with
    ``==`` too, and find NaN unequal to NaN.
    """
    a, b = tuple(a), tuple(b)
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool) \
                and not isinstance(y, bool):
            if not same_result(float(x), float(y)):
                return False
        elif x != y:
            return False
    return True


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
    return tp_box, tuple(ranges)


#: More lines than this from one saturation anchor is a step that is too small.
MAX_ANCHORED_LINES = 200


def saturation_anchor_values(provider, key: str, by: str, step_SI: float, Q: float, range_SI, tp_box,
                             margin: float, unit) -> Tuple[Tuple[float, float], ...]:
    """(saturation value, line value) of lines of constant ``key`` through saturation states at even steps.

    The saturation states are at round multiples of the step in ``unit``
    (the display unit of ``by``, e.g. 0, 10, 20 deg C for a step of 10 K),
    between the lowest saturation state and the critical point (less
    ``margin``), inside the chart's T-p box and inside ``range_SI``. Each
    line takes the value of ``key`` at the state of saturation quantity
    ``by`` ("T" or "p") and vapour quality ``Q``. States CoolProp cannot
    compute are left out. Values are in SI units, in the order of the
    saturation states.
    """
    key = quantity_key(key)
    if provider.kind != "fluid" or not provider.has_critical_point:
        raise ValueError("Lines are placed by saturation states only for fluids with a saturation curve; "
                         "{0} has none.".format(provider.name))
    lo, hi = provider.saturation_range(by, margin)
    box_lo, box_hi = (tp_box[0], tp_box[1]) if by == "T" else (tp_box[2], tp_box[3])
    lo, hi = max(lo, box_lo), min(hi, box_hi)
    if range_SI is not None:
        lo, hi = max(lo, range_SI[0]), min(hi, range_SI[1])
    if not hi >= lo:
        return ()
    # Round steps in the display unit: a difference converts with the scale
    # only; 10 digits drop the noise of the conversion (20 deg F is
    # 11.1111111111 K, which converts back to 19.99999999998)
    step_shown = float("{0:.10g}".format(abs(step_SI * unit.scale)))
    lo_shown, hi_shown = sorted(float(v) for v in unit.from_SI([lo, hi]))
    first = math.ceil(lo_shown / step_shown - 1e-9)
    last = math.floor(hi_shown / step_shown + 1e-9)
    if last - first + 1 > MAX_ANCHORED_LINES:
        raise ValueError("A step of {0:g} {1} would place {2} lines; choose a larger step.".format(
            step_shown, unit.difference.label, last - first + 1))
    values = []
    failed = 0
    for k in range(first, last + 1):
        shown = float("{0:.10g}".format(k * step_shown))   # 30.000000000000004 becomes 30
        saturation_SI = min(max(float(unit.to_SI(shown)), lo), hi)
        if key == by:
            values.append((saturation_SI, saturation_SI))
            continue
        try:
            value = provider.state_point(by, saturation_SI, "Q", Q)[key]
        except (ValueError, KeyError):
            value = float("nan")
        if math.isfinite(value):
            values.append((saturation_SI, float(value)))
        else:
            failed += 1   # CoolProp cannot compute this saturation state; the line is left out
    if failed:
        warnings.warn("{0} of {1} saturation states for the lines of constant {2} of {3} could not be computed; "
                      "they have no line.".format(failed, last - first + 1, key, provider.name), UserWarning,
                      stacklevel=2)
    return tuple(values)


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
        return provider.line(key, value_SI, tp_box, points, diagram, ranges)
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
