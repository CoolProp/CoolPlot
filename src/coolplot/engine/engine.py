# -*- coding: utf-8 -*-
"""Computing what a plan asks for, and keeping the results.

The :class:`Engine` owns everything that is expensive to make: the
property providers (one :class:`coolplot.thermo.Fluid` per fluid model,
one :class:`coolplot.thermo.humid_air.HumidAir` per total pressure), the
calculation domains and the curves. All three are kept, keyed by the
inputs that determine them, so a new spec only costs the calculations
that really differ from earlier ones.

Several diagrams can share one engine, for example the ph and Ts chart of
the same refrigerant in an application.
"""
from __future__ import annotations

import warnings
from collections import OrderedDict
from dataclasses import replace
from typing import List, Tuple

from ..spec.diagram import CycleSpec, DiagramSpec
from ..thermo.cycles import cycle_paths, resolve_states
from ..thermo.isolines import Curve
from ..thermo import native
from ..thermo.references import fluid_references, versions_line
from ..thermo.provider import chart_domain, compute_curve, make_provider, saturation_anchor_values
from .cache import CurveCache
from .planning import CurveRequest, Domain


class Engine:
    """Computes curves for diagram specs and caches every result

    Parameters
    ----------
    cache : CurveCache, optional
        Store for the curves; pass one to share it between engines.
    max_fluids : int
        Number of property providers (fluid models) that are kept.
    """

    def __init__(self, cache: CurveCache = None, max_fluids: int = 16):
        self.cache = cache if cache is not None else CurveCache()
        self.max_fluids = max_fluids
        self._fluids: "OrderedDict[object, object]" = OrderedDict()
        self._domains: "OrderedDict[Tuple, Domain]" = OrderedDict()
        self._anchors: "OrderedDict[Tuple, Tuple]" = OrderedDict()   # values of lines placed by saturation states
        self._cycles: "OrderedDict[Tuple, Tuple]" = OrderedDict()
        self._warned = set()

    def fluid(self, spec):
        """The property provider for a FluidSpec or HumidAirSpec, created once and reused.

        A fluid made under another CoolProp configuration (``set_config_*``)
        is made again. A changed reference state (``set_reference_state``)
        cannot be seen from outside: call :meth:`refresh` after it."""
        if spec in self._fluids and not self._fluids[spec].configuration_changed():
            self._fluids.move_to_end(spec)
            return self._fluids[spec]
        self._fluids.pop(spec, None)
        # Everything computed with the old fluid goes with it
        self._domains = OrderedDict((k, v) for k, v in self._domains.items() if k[0] != spec)
        self._anchors = OrderedDict((k, v) for k, v in self._anchors.items() if k[0] != spec)
        self._cycles = OrderedDict((k, v) for k, v in self._cycles.items() if k[0] != spec)
        fluid = make_provider(spec)
        self._fluids[spec] = fluid
        if len(self._fluids) > self.max_fluids:
            self._fluids.popitem(last=False)
        return fluid

    def refresh(self):
        """Forget every CoolProp state, domain and cycle, so the next request builds them anew.

        Needed after ``CoolProp.CoolProp.set_reference_state`` or any other
        change to CoolProp that its configuration string does not show;
        the curves made before stay in the cache under their old fingerprint
        and are not served again."""
        self._fluids.clear()
        self._domains.clear()
        self._anchors.clear()
        self._cycles.clear()

    def domain(self, spec: DiagramSpec) -> Domain:
        """The calculation region of a diagram: the T-p box, the range of every
        quantity and the values of the families placed by saturation states."""
        if self.cache.disk is not None:
            # Lines on disk outlive the process: a reference state changed
            # without refresh() would put new lines (and enthalpy and entropy
            # ranges) under the old fingerprint. One new state per update, so
            # only when lines can go to disk.
            changed = getattr(self.fluid(spec.fluid), "reference_state_changed", None)
            if changed is not None and changed():
                self.refresh()
        margin = spec.settings.calc.critical_margin
        key = (spec.fluid, spec.limits, margin)
        if key not in self._domains:
            tp_box, ranges = chart_domain(self.fluid(spec.fluid), spec.limits, margin)
            provider = self.fluid(spec.fluid)
            has_saturation = provider.kind == "humid_air" or bool(getattr(provider, "has_critical_point", False))
            self._domains[key] = Domain(tp_box, ranges, saturation=has_saturation)
            if len(self._domains) > 64:
                self._domains.popitem(last=False)
        self._domains.move_to_end(key)
        domain = self._domains[key]
        anchored = tuple(((s.key, s.anchor), self._anchor_values(spec, domain, s))
                         for s in spec.isolines if s.anchor is not None)
        return replace(domain, anchored=anchored) if anchored else domain

    def _anchor_values(self, spec: DiagramSpec, domain: Domain, iso_set) -> Tuple[float, ...]:
        """The values of one family placed by saturation states, computed once per fluid, region and unit."""
        anchor = iso_set.anchor
        unit = spec.units[anchor.by]   # the round steps are round in the units shown
        margin = spec.settings.calc.critical_margin
        key = (spec.fluid, spec.limits, margin, iso_set.key, anchor, unit)
        if key not in self._anchors:
            self._anchors[key] = saturation_anchor_values(
                self.fluid(spec.fluid), iso_set.key, anchor.by, anchor.step_SI, anchor.Q, anchor.range_SI,
                domain.tp_box, margin, unit)
            if len(self._anchors) > 256:
                self._anchors.popitem(last=False)
        self._anchors.move_to_end(key)
        return self._anchors[key]

    # Position of the "computed by CoolProp's port" flag in a cache key. The
    # flag is decided once, when the key is made, and handed to the code that
    # computes the curve, so a curve is always computed the way its key says,
    # also in worker processes and when the mode changes meanwhile.
    _NATIVE_INDEX = 6

    @classmethod
    def key_uses_native(cls, key: Tuple) -> bool:
        """Whether the curve of a cache key is computed by CoolProp's port (see thermo.native)."""
        return bool(key[cls._NATIVE_INDEX])

    def cache_key(self, spec: DiagramSpec, domain: Domain, request: CurveRequest) -> Tuple:
        """Everything that determines one curve.

        Lines of constant quality do not depend on the T-p box but on the
        saturation settings; all other isolines are swept through the box.
        """
        calc = spec.settings.calc
        base = (spec.fluid, self.fluid(spec.fluid).fingerprint, spec.diagram, request.key, request.value_SI,
                request.points, native.enabled())   # the implementation that computes the line, see thermo.native
        if request.key == "Q":
            return base + (calc.critical_margin, calc.saturation_spacing)
        # The margin decides where saturation states are inserted
        key = base + (domain.tp_box, calc.solver, calc.critical_margin)
        if request.key == "T" and spec.diagram.is_mollier:
            # An isotherm of the Mollier chart ends a little beyond the top of
            # the humidity ratio range, which the T-p box does not hold
            key += (dict(domain.ranges_SI).get("W"),)
        return key

    def curve(self, spec: DiagramSpec, domain: Domain, request: CurveRequest) -> Curve:
        """One curve, from the cache or freshly computed."""
        calc = spec.settings.calc
        key = self.cache_key(spec, domain, request)

        def compute():
            return compute_curve(self.fluid(spec.fluid), spec.diagram, request.key, request.value_SI,
                                 domain.tp_box, request.points, calc.solver, calc.critical_margin,
                                 calc.saturation_spacing, domain.ranges_SI, use_native=self.key_uses_native(key))

        return self.cache.get_or_compute(key, compute)

    def _obtain(self, spec: DiagramSpec, domain: Domain, request: CurveRequest):
        """(curve, final) for a request. This engine computes it right away;
        :class:`coolplot.engine.background.BackgroundEngine` returns what is
        ready (a coarse preview has final=False) or (None, False)."""
        return self.curve(spec, domain, request), True

    def curves(self, spec: DiagramSpec, domain: Domain, requests) -> List[Tuple[CurveRequest, Curve]]:
        """The curves of all requests that have at least two valid points.

        Curves that are left out, or that have more failed points inside
        the line (see :attr:`Curve.n_gaps`) than
        ``Settings.calc.warn_failed_fraction``, cause one warning each; the
        same curve does not warn again on later updates.
        """
        result = []
        tolerance = spec.settings.calc.warn_failed_fraction
        for request in requests:
            curve, final = self._obtain(spec, domain, request)
            if curve is None:
                continue   # not ready yet (background engine)
            total = len(curve.x)
            if not final:
                # A coarse preview: draw it if it has a line, judge only the final curve
                if curve.n_valid >= 2:
                    result.append((request, curve))
                continue
            if curve.n_valid < 2:
                if curve.n_failed == 0 and curve.n_outside > 0:
                    continue   # the line lies outside the calculation domain: nothing to draw, nothing wrong
                if request.key == "Q" and self._pseudo_pure_warning(spec):
                    continue   # one warning for the fluid explains every missing quality line
                why = curve.reason or "CoolProp failed for {0} of {1} points".format(curve.n_failed, total)
                self._warn(spec, domain, request, "Skipping the line {0}={1:.6g} in {2}: {3}.".format(
                    request.key, request.value_SI, spec.fluid.name, why))
                continue
            if curve.reason:
                self._warn(spec, domain, request, "The line {0}={1:.6g} in {2} is incomplete: {3}.".format(
                    request.key, request.value_SI, spec.fluid.name, curve.reason))
            if total and curve.n_gaps > tolerance * total:
                self._warn(spec, domain, request, "The line {0}={1:.6g} in {2} has gaps: CoolProp failed for "
                           "{3} of {4} points inside the line.".format(request.key, request.value_SI,
                                                                       spec.fluid.name, curve.n_gaps, total))
            result.append((request, curve))
        return result

    def cycle(self, spec: DiagramSpec, cycle: CycleSpec):
        """(states, chains) of a cycle: StatePoints by number, and per chain
        the states along all its paths. Computed once per fluid and cycle
        definition; restyling a cycle does not recompute it."""
        key = (spec.fluid, cycle.states, cycle.loops, cycle.paths, cycle.steps)
        if key in self._cycles:
            self._cycles.move_to_end(key)
            return self._cycles[key]
        fluid = self.fluid(spec.fluid)
        states = resolve_states(fluid, dict(cycle.states), cycle.loops)
        chains = cycle_paths(fluid, states, cycle.loops, dict(cycle.paths), cycle.steps)
        self._cycles[key] = (states, chains)
        if len(self._cycles) > 64:
            self._cycles.popitem(last=False)
        return states, chains

    def source_lines(self, spec: DiagramSpec) -> Tuple[str, ...]:
        """The badge lines that name where the properties come from, as
        ``Settings.branding`` asks for them: the references of the fluid
        (:func:`coolplot.thermo.references.fluid_references`) and the
        versions of CoolProp and CoolPlot. Empty when it asks for neither."""
        settings = spec.settings.branding
        lines = []
        if settings.references != "none":
            lines.extend(fluid_references(spec.fluid, settings.references))
        if settings.versions:
            lines.append(versions_line())
        return tuple(lines)

    def _pseudo_pure_warning(self, spec) -> bool:
        """Warn once per fluid that a pseudo-pure blend has no quality lines; False for other fluids."""
        blend = getattr(self.fluid(spec.fluid), "pseudo_pure_blend", None)
        if blend is None:
            return False
        key = ("pseudo-pure", spec.fluid)
        if key not in self._warned:
            self._warned.add(key)
            warnings.warn("{0} is CoolProp's pseudo-pure model of a blend: it has no two-phase states, so the "
                          "lines of constant vapour quality are left out and the dome has no glide. Use "
                          "'{1}' for the blend as a mixture.".format(spec.fluid.name, blend), UserWarning,
                          stacklevel=4)
        return True

    def _warn(self, spec, domain, request, message):
        # Keyed like the curve itself, so a gappy line in a new domain warns again
        key = self.cache_key(spec, domain, request)
        if key not in self._warned:
            if len(self._warned) > 10000:   # a long session, not a memory leak
                self._warned.clear()
            self._warned.add(key)
            warnings.warn(message, UserWarning, stacklevel=3)
