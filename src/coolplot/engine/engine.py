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
from ..spec.diagram import DiagramSpec
from ..spec.fluid import FluidSpec
from ..thermo.fluid import Fluid
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
        self._domains = {}
        self._warned = set()

    def fluid(self, spec: FluidSpec) -> Fluid:
        """The Fluid for a fluid model, created once and reused."""
        if spec in self._fluids:
            self._fluids.move_to_end(spec)
            return self._fluids[spec]
        fluid = Fluid(spec)
        self._fluids[spec] = fluid
        if len(self._fluids) > self.max_fluids:
            self._fluids.popitem(last=False)
        return fluid

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
        return self._domains[key]

    def cache_key(self, spec: DiagramSpec, domain: Domain, request: CurveRequest) -> Tuple:
        """Everything that determines one curve.

        Lines of constant quality do not depend on the T-p box but on the
        saturation settings; all other isolines are swept through the box.
        """
        calc = spec.settings.calc
        base = (spec.fluid, spec.diagram, request.key, request.value_SI, request.points)
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
            curve = self.curve(spec, domain, request)
            total = len(curve.x)
            if curve.n_valid < 2:
                self._warn(spec, request, "Skipping the line {0}={1:.6g} in {2}: CoolProp failed for "
                           "{3} of {4} points.".format(request.key, request.value_SI, spec.fluid.name,
                                                       curve.n_failed, total))
                continue
            if total and curve.n_gaps > tolerance * total:
                self._warn(spec, request, "The line {0}={1:.6g} in {2} has gaps: CoolProp failed for "
                           "{3} of {4} points inside the line.".format(request.key, request.value_SI,
                                                                       spec.fluid.name, curve.n_gaps, total))
            result.append((request, curve))
        return result

    def _warn(self, spec, request, message):
        key = (spec.fluid, spec.diagram, request.key, request.value_SI, request.points)
        if key not in self._warned:
            self._warned.add(key)
            warnings.warn(message, UserWarning, stacklevel=3)
