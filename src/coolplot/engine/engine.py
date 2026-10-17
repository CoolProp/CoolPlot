# -*- coding: utf-8 -*-
"""Computing what a plan asks for, and keeping the results.

The :class:`Engine` owns everything that is expensive to make: CoolProp
states (one :class:`coolplot.thermo.Fluid` per fluid model), the
calculation domains and the curves. All three are kept, keyed by the
inputs that determine them, so a new spec only costs the calculations
that really differ from earlier ones.

Several diagrams can share one engine, for example the ph and Ts chart of
the same refrigerant in an application.
"""
from __future__ import annotations

import warnings
from collections import OrderedDict
from typing import List, Tuple

from ..core.quantities import QUANTITIES
from ..spec.diagram import CycleSpec, DiagramSpec
from ..spec.fluid import FluidSpec
from ..thermo.fluid import Fluid
from ..thermo.cycles import cycle_paths, resolve_states
from ..thermo.isolines import Curve, compute_isoline, compute_quality_line
from ..thermo.limits import property_range_SI, resolve_tp_box
from .cache import CurveCache
from .plan import CurveRequest, Domain


class Engine:
    """Computes curves for diagram specs and caches every result

    Parameters
    ----------
    cache : CurveCache, optional
        Store for the curves; pass one to share it between engines.
    max_fluids : int
        Number of fluid models whose CoolProp states are kept.
    """

    def __init__(self, cache: CurveCache = None, max_fluids: int = 16):
        self.cache = cache if cache is not None else CurveCache()
        self.max_fluids = max_fluids
        self._fluids: "OrderedDict[FluidSpec, Fluid]" = OrderedDict()
        self._domains: "OrderedDict[Tuple, Domain]" = OrderedDict()
        self._cycles: "OrderedDict[Tuple, Tuple]" = OrderedDict()
        self._warned = set()

    def fluid(self, spec: FluidSpec) -> Fluid:
        """The Fluid for a fluid model, created once and reused.

        A fluid made under another CoolProp configuration (``set_config_*``)
        is made again. A changed reference state (``set_reference_state``)
        cannot be seen from outside: call :meth:`refresh` after it."""
        if spec in self._fluids and not self._fluids[spec].configuration_changed():
            self._fluids.move_to_end(spec)
            return self._fluids[spec]
        self._fluids.pop(spec, None)
        self._domains = OrderedDict((k, v) for k, v in self._domains.items() if k[0] != spec)
        fluid = Fluid(spec)
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
        self._cycles.clear()

    def domain(self, spec: DiagramSpec) -> Domain:
        """The calculation region of a diagram: the T-p box and the range of every quantity."""
        margin = spec.settings.calc.critical_margin
        key = (spec.fluid, spec.limits, margin)
        if key not in self._domains:
            fluid = self.fluid(spec.fluid)
            tp_box = resolve_tp_box(fluid, spec.limits, margin)
            ranges = []
            for quantity in QUANTITIES:
                try:
                    ranges.append((quantity, property_range_SI(fluid, quantity, tp_box)))
                except ValueError:
                    continue   # not defined for this fluid, e.g. u for some backends
            self._domains[key] = Domain(tuple(tp_box), tuple(ranges))
            if len(self._domains) > 64:
                self._domains.popitem(last=False)
        self._domains.move_to_end(key)
        return self._domains[key]

    def cache_key(self, spec: DiagramSpec, domain: Domain, request: CurveRequest) -> Tuple:
        """Everything that determines one curve.

        Lines of constant quality do not depend on the T-p box but on the
        saturation settings; all other isolines are swept through the box.
        """
        calc = spec.settings.calc
        base = (spec.fluid, self.fluid(spec.fluid).fingerprint, spec.diagram, request.key, request.value_SI,
                request.points)
        if request.key == "Q":
            return base + (calc.critical_margin, calc.saturation_spacing)
        # The margin decides where saturation states are inserted
        return base + (domain.tp_box, calc.solver, calc.critical_margin)

    def curve(self, spec: DiagramSpec, domain: Domain, request: CurveRequest) -> Curve:
        """One curve, from the cache or freshly computed."""
        calc = spec.settings.calc

        def compute():
            fluid = self.fluid(spec.fluid)
            if request.key == "Q":
                return compute_quality_line(fluid, spec.diagram, request.value_SI, request.points,
                                            calc.critical_margin, calc.saturation_spacing)
            return compute_isoline(fluid, spec.diagram, request.key, request.value_SI, domain.tp_box,
                                   request.points, calc.solver, calc.critical_margin)

        return self.cache.get_or_compute(self.cache_key(spec, domain, request), compute)

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
                why = curve.reason or "CoolProp failed for {0} of {1} points".format(curve.n_failed, total)
                self._warn(spec, domain, request, "Skipping the line {0}={1:.6g} in {2}: {3}.".format(
                    request.key, request.value_SI, spec.fluid.name, why))
                continue
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

    def _warn(self, spec, domain, request, message):
        # Keyed like the curve itself, so a gappy line in a new domain warns again
        key = self.cache_key(spec, domain, request)
        if key not in self._warned:
            if len(self._warned) > 10000:   # a long session, not a memory leak
                self._warned.clear()
            self._warned.add(key)
            warnings.warn(message, UserWarning, stacklevel=3)
