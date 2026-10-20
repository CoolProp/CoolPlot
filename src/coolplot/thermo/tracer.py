# -*- coding: utf-8 -*-
"""Walking along an isoline, warm-starting each point from the previous one.

Ported from ``CoolProp.Plots.Common.IsoLineTracer`` (CoolProp 8), where it
was developed and tested against the predefined blends. The changes are
that the tracer builds its CoolProp states from a :class:`Fluid` model
description instead of cloning a caller's state, that the critical
temperature cache is keyed by that description, and a smaller margin on
the top of a closed phase envelope (see CLOSED_ENVELOPE_MARGIN).

For a pure fluid a plain flash is already fast; for mixtures the tracer is
orders of magnitude faster than a flash per point and leaves fewer gaps.
Every point the tracer cannot solve with confidence raises, and the caller
falls back to a plain flash for that point.
"""
from __future__ import annotations

import numpy as np

import CoolProp
from CoolProp.CoolProp import PropsSI

from .fluid import build_state

# The tracer needs CoolProp 8 (pyproject.toml): CoolProp 6 and 7 abort the
# whole Python process (a C++ abort, not an exception) in some of the
# saturation calls it makes for mixtures near the critical point.


#: A two-phase state whose two phases differ in density by less than this,
#: relatively, is the trivial solution: the VLE solver collapsed both phases
#: onto the same root rather than converging on a saturation state.
#:
#: Calibrated where it is load-bearing, which is the Q=0 and Q=1 calls the
#: bracket and the dome check make: across the predefined blends, genuine
#: saturation pairs there stay above 1.8e-3 and collapsed ones fall below
#: 1e-7, so this sits orders clear of both.  At intermediate quality the
#: separation is looser -- Air, R441A, R448A and R407C all return pairs a
#: little above this threshold at temperatures beyond their critical point --
#: and the quality lines will draw those.  Both error directions are safe for
#: the tracer: a rejected genuine pair costs a fallback flash, and an accepted
#: collapsed one still has to get past the density comparison that follows.
_TRIVIAL_SOLUTION_RTOL = 1e-4


def _phases_are_distinct(state):
    """Whether a two-phase state really has two phases

    Near the critical point the mixture QT and PQ solvers can return the
    trivial solution, reporting the requested quality and a state whose
    saturated liquid and vapour are the same root.  The result is a plausible
    looking point that is nowhere near the one asked for -- on an R513A Q=0.5
    line it puts the last point 93 J/kg/K along in entropy, which is the jag
    at the top of the dome.
    """
    try:
        rho_liq = state.saturated_liquid_keyed_output(CoolProp.iDmolar)
        rho_vap = state.saturated_vapor_keyed_output(CoolProp.iDmolar)
    except Exception:
        # HEOS, the cubics, GERG and REFPROP give these outputs after a
        # quality flash, so a failure there is a failed state.  A backend
        # without saturated outputs (IF97, PC-SAFT) throws every time.  Both
        # count as not distinct: that costs the caller a fallback flash or a
        # gap, never a collapsed state taken as a point.
        return False
    if not (np.isfinite(rho_liq) and np.isfinite(rho_vap)) or rho_liq <= 0.0 or rho_vap <= 0.0:
        return False
    return (rho_liq - rho_vap) > _TRIVIAL_SOLUTION_RTOL * max(rho_liq, rho_vap)


class IsoLineTracer(object):
    """Walk along an isoline, warm-starting every point from the previous one.

    :func:`coolplot.thermo.isolines.compute_isoline` evaluates an isoline at consecutive points, so
    the solution at one point is an excellent initial guess for the next one.
    That turns each point into a much cheaper problem than the cold
    two-dimensional flash it replaces:

    * A single-phase point is solved as a two-by-two Newton iteration in
      ``(T, rhomolar)``.  Every property is an explicit function of
      ``(T, rhomolar)`` for a Helmholtz-energy EOS, so the iteration needs no
      flash at all, only ``DmolarT_INPUTS`` updates on a state whose phase has
      been imposed.  Imposing the phase skips the saturation call that
      dominates a mixture update and, just as importantly, keeps the iterates
      on the single-phase root instead of snapping to a two-phase solution.
    * A two-phase point is bracketed by the two saturation states at the
      constant temperature or pressure of the input pair, and the vapour
      quality between them is found by a bracketed one-dimensional solve.

    The tracer needs temperature or pressure among the two inputs -- see
    :func:`supports` -- because that is what lets it bracket the saturation
    curve.  Every point it cannot bracket, on either side, raises so that the
    caller falls back to a plain :func:`AbstractState.update` call: a
    phase-imposed Newton iteration will happily return the metastable
    extension of the EOS inside the dome, and only the bracket rules that out.
    """

    #: The Newton iteration has settled once the relative step in both T and
    #: rhomolar is this small.  That alone is not convergence -- see
    #: RESIDUAL_RTOL -- but it is what stops the iteration.
    NEWTON_RTOL = 1e-10
    #: Residual accepted at that point, relative to how much the property
    #: varies over the iteration variables.
    RESIDUAL_RTOL = 1e-9
    NEWTON_ITMAX = 30
    #: A single Newton step may not move T or rhomolar by more than this
    #: fraction of their current value.
    NEWTON_TRUST = 0.25
    #: Bracketed solve for the vapour quality of a two-phase point.
    QUALITY_XTOL = 1e-12
    QUALITY_RTOL = 1e-8
    QUALITY_ITMAX = 60
    #: A saturation bracket narrower than this (relative) cannot resolve a
    #: quality: a pure fluid at fixed T brackets p by psat on both sides, and
    #: an azeotropic mixture is barely better.  Such a point is single-phase
    #: as far as the tracer is concerned.
    BRACKET_RTOL = 1e-8
    #: How far outside the saturation densities a converged single-phase root
    #: may sit before it is rejected as the wrong branch.
    BRANCH_RTOL = 1e-6

    #: The reported extent of the two-phase region is a traced curve, so its
    #: end is not exactly the cricondenbar (or cricondentherm).  A point is
    #: only called supercritical this far beyond it.
    DOME_MARGIN = 1.05
    #: Margin on the highest temperature of a phase envelope that ran to the
    #: critical point (CoolPlot change; CoolProp uses DOME_MARGIN here). On
    #: the predefined and common refrigerant blends that temperature agrees
    #: with the critical temperature from all_critical_points to within
    #: 0.04 K and does not change when the envelope is refined, so 0.5 % is
    #: still a margin of about forty. With 5 % every supercritical point up
    #: to some 17 K above the dome was handed back to a flash that costs up
    #: to 2 s per point for a blend; one isentrope of R32/R125 near the
    #: critical point took 25 s instead of 1 s.
    CLOSED_ENVELOPE_MARGIN = 1.005
    #: Above the top of a closed envelope by this much (0.07 K at 344 K,
    #: twice the 0.04 K above) there is no dome: a root there is accepted
    #: without the density check of TOP_DENSITY_MARGIN. Between the top and
    #: this, the density check applies. Only for an envelope whose two
    #: densities at the top agree to TOP_GAP_RTOL: with the coexistence
    #: curve going as (1 - T/Tc)^0.33, that puts the top within a few
    #: millikelvin of the critical point, where a gap of 35 % (the
    #: closedness test) could still leave it 0.3 K short.
    ABOVE_TOP_RTOL = 2e-4
    TOP_GAP_RTOL = 0.05
    #: A phase envelope that ends with its two densities still this far apart
    #: did not run to the critical point, so where its dome ends is unknown
    #: and has to be found the expensive way.
    ENVELOPE_CLOSED_RTOL = 0.35
    #: Near the critical point the saturation solver stops answering some
    #: kelvin before the top of a closed envelope and in the band above it
    #: (CLOSED_ENVELOPE_MARGIN). A root there is judged by its density
    #: against the dome the envelope describes at that temperature: a root
    #: this far outside those densities cannot be in the dome. The rest is
    #: handed back to a flash. Without this every point of an isotherm
    #: 0.5 K above the critical temperature of R410A was flashed (7 s for
    #: one line; 16 ms per flash), and an isentrope paid 0.3 s for each of
    #: its points just above the critical pressure.
    TOP_DENSITY_MARGIN = 1.5

    LIQUID = -1
    VAPOUR = 1

    #: Critical temperatures keyed by fluid *model*, for the blends whose phase
    #: envelope does not reach the critical point and where locating it costs
    #: seconds to minutes.  Unlike the envelope, this lookup has no side effect
    #: on the state that produced it, so caching it cannot make one tracer
    #: behave differently from the next.  The key has to carry the binary
    #: interaction parameters, not just the fluids and composition: they move
    #: the critical point, and a shared limit that came out too low would send
    #: :func:`_check_outside_the_dome` down its no-dome path over a range where
    #: there is one.
    _CRITICAL_T = {}

    @classmethod
    def supports(cls, index1, index2):
        """Whether an isoline with these two inputs can be traced

        The tracer needs temperature or pressure among the inputs, because
        that is what lets it put a saturation bracket around a point and so
        tell a two-phase state from a single-phase one.  Without it the Newton
        iteration would run on a phase-imposed state with nothing to stop it
        returning the metastable extension of the EOS inside the dome -- a
        plausible-looking answer that is simply wrong.  ``HmassSmass_INPUTS``
        and ``DmassSmass_INPUTS`` are the pairs this rules out.
        """
        return CoolProp.iT in (index1, index2) or CoolProp.iP in (index1, index2)

    def __init__(self, fluid, index1, index2, iso_index):
        """
        Parameters
        ----------
        fluid : Fluid
            The fluid the isoline belongs to. The tracer builds its own
            CoolProp states from the fluid model and never touches the
            working state of the fluid.
        index1, index2 : int
            Parameter indices of the two inputs, in the order the input pair
            expects them.
        iso_index : int
            Parameter index the isoline holds constant.
        """
        if index1 == index2:
            raise ValueError("The two inputs of an isoline cannot be the same property.")
        if not self.supports(index1, index2):
            raise ValueError("An isoline whose inputs include neither temperature "
                             "nor pressure cannot be traced.")
        self._i1 = index1
        self._i2 = index2
        # Both states are built from the same model description, so they are
        # the same fluid model by construction (no clone check needed).
        self._model_key = fluid.model_key
        self._sat = build_state(fluid.model_key)
        self._sp = build_state(fluid.model_key)
        # Not every backend honours an imposed phase; the tracer is still
        # correct without it, just slower and less robust, so fail soft.
        try:
            self._sp.specify_phase(CoolProp.iphase_gas)
        except Exception:
            pass  # backend without an imposed phase; correctness does not depend on it
        # Using the isoline's own constant as the saturation variable makes the
        # bracket constant along the whole line, so it is computed only once.
        if iso_index in (CoolProp.iT, CoolProp.iP) and iso_index in (index1, index2):
            self._sat_index = iso_index
        elif CoolProp.iT in (index1, index2):
            self._sat_index = CoolProp.iT
        else:
            self._sat_index = CoolProp.iP
        self._eos_bounds = self._find_eos_bounds()
        self._envelope_top = None   # (T, p, rhomolar_liq, rhomolar_vap) at the top of a closed envelope
        self._dome_densities = None   # (T, rhomolar) tables of the two branches of a closed envelope
        envelope_bounds, self._saturation_bounds = self._find_saturation_bounds()
        self._dome_limit = envelope_bounds.get(self._sat_index)
        self._dome_T_limit = self._find_dome_temperature_limit()
        self._sat_value = None
        self._bracket = None
        self._bracket_failure = None
        self._T = np.nan
        self._rhomolar = np.nan
        self._side = None
        self._out = None
        self._last_quality = None   # warm start for the next two-phase point
        self._last_two_phase = None   # (T, rhomolar) of the last two-phase point, a seed of last resort

    @property
    def state(self):
        """The state holding the most recently traced point

        Note that its ``phase()`` reports the phase the tracer imposed on it,
        not one it determined; ``Q()`` is meaningful, ``phase()`` is not.
        """
        if self._out is None:
            raise ValueError("No point has been traced yet.")
        return self._out

    def keyed_output(self, key):
        """Read a property of the most recently traced point"""
        return self.state.keyed_output(key)

    def set_guess(self, state):
        """Adopt a state the caller solved itself as the warm start

        A two-phase state says nothing about the single-phase root the Newton
        iteration follows, so it is ignored.  Both ``phase()`` and ``Q()`` are
        consulted: the caller's state is shared and may have had a phase
        imposed on it, in which case ``phase()`` reports that rather than what
        was found.
        """
        try:
            if state.phase() == CoolProp.iphase_twophase:
                return
            quality = state.Q()
            # phase() reports whatever the caller imposed on the shared state,
            # so do not rely on it alone.
            if np.isfinite(quality) and 0.0 <= quality <= 1.0:
                return
            T, rhomolar = state.T(), state.rhomolar()
        except Exception:
            return  # unusable state; keep whatever warm start we already had
        if np.isfinite(T) and np.isfinite(rhomolar) and T > 0.0 and rhomolar > 0.0:
            self._T = T
            self._rhomolar = rhomolar
            self._side = None

    def update(self, value1, value2):
        """Trace the state with ``index1 == value1`` and ``index2 == value2``

        Raises if the point could not be traced.  The warm start survives,
        because it holds the last point that *did* converge and that is still
        the best guess available for the next one -- dropping it on every
        failure lets a single awkward point strand the whole rest of the line
        in a region where there is no saturation state to restart from.
        """
        try:
            self._out = None
            targets = {self._i1: value1, self._i2: value2}
            bracket = self._get_bracket(targets)
            if bracket is not None and bracket['two_phase']:
                self._solve_quality(bracket)
            else:
                self._solve_single_phase(targets, bracket)
        except Exception:
            self._out = None
            raise

    # -------------------------------------------------------------------
    # Saturation bracket
    # -------------------------------------------------------------------
    def _find_eos_bounds(self):
        """The range the equation of state is actually valid over

        Cheap -- these are trivial parameters -- and used twice: to keep a
        diverged phase envelope from setting a meaningless bound, and to stop
        the Newton iteration reporting a root far outside the fitted range.
        With the phase imposed there is nothing else to stop it: an isochore
        on R504 will happily extrapolate to tens of thousands of kelvin and
        report finite numbers there.
        """
        bounds = {}
        for index, key in ((CoolProp.iT, CoolProp.iT_max), (CoolProp.iP, CoolProp.iP_max)):
            try:
                value = self._sp.trivial_keyed_output(key)
            except Exception:
                continue
            if np.isfinite(value) and value > 0.0:
                bounds[index] = value
        try:
            value = self._sp.trivial_keyed_output(CoolProp.iT_min)
            if np.isfinite(value) and value > 0.0:
                bounds['T_min'] = value
        except Exception:
            pass  # no lower limit published; the runaway guard uses the upper one
        return bounds

    def _find_saturation_bounds(self):
        """Two bounds on how far the two-phase region reaches, in T and in p

        They answer different questions and must not be conflated.

        The *inner* one is the phase envelope's own extent.  It decides what a
        failed saturation call means: beyond it there is probably no dome, so
        the point is traced without a bracket -- and then checked against the
        saturation densities at its own temperature by
        :func:`_check_outside_the_dome`, which is what actually makes that
        safe.  Being merely probable is therefore fine, and keeping it tight
        is what keeps the fallback rate down.

        The *outer* one also takes in the largest critical point among the
        components, and decides whether a saturation state the solver returned
        can be believed.  Beyond the cricondenbar the mixture PQ and QT
        solvers do not fail: they return a state that reports the requested
        pressure and quality exactly and sits hundreds of kelvin from the
        dome.  This one has to be generous, because the envelope trace stops
        short of the real cricondentherm for several predefined blends --
        R504 by about 20 K -- and those genuine dome states must not be thrown
        away as solver noise.

        Building the envelope is also what makes the saturation calls on
        ``self._sat`` converge in the first place -- the mixture PQ and QT
        flashes take their guesses from it -- so this is deliberately done on
        that object and deliberately not cached between tracers.  Caching it
        made the first isoline of a fluid behave differently from the rest.
        """
        envelope = {}
        closed = False
        try:
            self._sat.build_phase_envelope("none")
            data = self._sat.get_phase_envelope_data()
            envelope = {CoolProp.iT: max(data.T), CoolProp.iP: max(data.p)}
            closed = self._envelope_is_closed(data)
            if closed:
                hot = int(np.argmax(np.asarray(data.T, dtype=float)))
                self._envelope_top = (float(data.T[hot]), float(max(data.p)),
                                      float(data.rhomolar_liq[hot]), float(data.rhomolar_vap[hot]))
                self._dome_densities = self._dome_density_table(data)
        except Exception:
            pass  # no envelope: every point must be bracketed or handed back
        outer = dict(envelope)
        try:
            for index, name in ((CoolProp.iT, 'Tcrit'), (CoolProp.iP, 'pcrit')):
                critical = max(PropsSI(name, fluid) for fluid in self._sat.fluid_names())
                outer[index] = max(outer.get(index, 0.0), critical)
        except Exception:
            pass  # no component critical data; the envelope alone has to do

        def clean(candidate, margin):
            """Drop unusable bounds, clamp to the EOS range, apply the margin"""
            bounds = {}
            for index, value in candidate.items():
                if not (np.isfinite(value) and value > 0.0):
                    continue
                # A phase envelope can diverge rather than fail -- CO2/nitrogen
                # traces one out to 18000 K -- and an unclamped bound from it
                # makes every plausibility test below a tautology.
                limit = self._eos_bounds.get(index)
                bounds[index] = min(value, limit) if limit is not None else value
            return {k: v * margin for k, v in bounds.items()}
        # The inner bound may be tight when the envelope ran to the critical
        # point (CoolPlot change, see CLOSED_ENVELOPE_MARGIN): a point beyond
        # it is still checked by _check_outside_the_dome.
        inner_margin = self.CLOSED_ENVELOPE_MARGIN if closed else self.DOME_MARGIN
        return clean(envelope, inner_margin), clean(outer, self.DOME_MARGIN)

    def _envelope_is_closed(self, data):
        """Whether a phase envelope ran to the critical point

        Its liquid and vapour densities then converge at the hottest point.
        """
        temperatures = np.asarray(data.T, dtype=float)
        hot = int(np.argmax(temperatures))
        rho_liq = float(np.asarray(data.rhomolar_liq, dtype=float)[hot])
        rho_vap = float(np.asarray(data.rhomolar_vap, dtype=float)[hot])
        return abs(rho_liq - rho_vap) <= self.ENVELOPE_CLOSED_RTOL * max(rho_liq, rho_vap)

    def _find_dome_temperature_limit(self):
        """The temperature above which there is certainly no two-phase region

        Temperature only, deliberately.  A pressure bound looks like it should
        be just as usable -- above the cricondenbar no two-phase state exists
        at that pressure -- but it does not answer the question this is for.
        What has to be decided is whether the ``(T, rhomolar)`` the Newton
        iteration landed on is the stable root at *its own* temperature, and
        the EOS pressure along the metastable branch inside the dome runs well
        above the cricondenbar, so a root there satisfies a high-pressure
        isobar perfectly while sitting between the saturation densities.
        Short-circuiting on pressure shipped 69 such roots on a default
        R441A T-s plot, 8.7 % out in temperature.

        This one has to be right rather than generous: it is what decides
        whether a saturation call that could not answer counts as "there is no
        dome here" or as "this point cannot be checked, hand it back".  Too
        high and every supercritical point pays for a flash; too low and roots
        inside the dome are accepted unexamined.

        A phase envelope that ran to the critical point ends with its liquid
        and vapour densities converging, and then its own maximum temperature
        is the answer for free.  One that stopped early -- R504's ends with
        them still a factor of six apart, 37 K below the real critical point
        -- says nothing, and the critical point has to be located directly,
        which is slow enough to be worth avoiding for every other fluid.
        """
        try:
            data = self._sat.get_phase_envelope_data()
            temperatures = np.asarray(data.T, dtype=float)
            hot = int(np.argmax(temperatures))
            if self._envelope_is_closed(data):
                # The trace covered the whole dome, so its own extremes are the
                # cricondentherm and the cricondenbar.
                return temperatures[hot] * self.CLOSED_ENVELOPE_MARGIN
        except Exception:
            pass  # envelope unusable; fall through to locating the critical point
        # An envelope that stopped early does not bound the dome.  The critical
        # point can be located directly, which is slow enough to be worth
        # avoiding whenever the envelope already answered.
        key = self._model_key
        if key not in self._CRITICAL_T:
            if len(self._CRITICAL_T) > 64:  # a plotting session, not a cache
                self._CRITICAL_T.clear()
            critical = None
            try:
                stable = [point.T for point in self._sat.all_critical_points() if point.stable]
                if stable:
                    critical = max(stable)
            except Exception:
                pass  # critical point not locatable; fall back on the outer bound
            self._CRITICAL_T[key] = critical
        critical = self._CRITICAL_T[key]
        if critical is not None:
            return critical * self.DOME_MARGIN
        return self._saturation_bounds.get(CoolProp.iT)

    def _is_plausible_saturation(self, T, p):
        """Whether a state the saturation solver returned can be on the dome"""
        for index, value in ((CoolProp.iT, T), (CoolProp.iP, p)):
            bound = self._saturation_bounds.get(index)
            if bound is not None and not value <= bound:
                return False
        return True

    def _saturation_endpoint(self, sat_value, quality):
        """Move ``self._sat`` onto the saturation curve

        These deliberately do not go through ``update_with_guesses``.  Seeding
        the saturation solver from the previous point is about twice as fast,
        but near the critical point it converges on a state that is not the
        bubble or dew point and reports no error while doing so, and every
        branch decision below is built on this bracket.  The saturation calls
        are a small part of the cost of a traced isoline anyway.
        """
        if self._sat_index == CoolProp.iT:
            self._sat.update(CoolProp.QT_INPUTS, quality, sat_value)
        else:
            self._sat.update(CoolProp.PQ_INPUTS, sat_value, quality)

    def _get_bracket(self, targets):
        """Bracket the target property between its saturated liquid and vapour values

        Returns a dict describing the bracket and whether the point falls
        inside it, or ``None`` if the point is beyond the dome entirely, where
        an unbracketed single-phase root is safe because there is no second
        root to confuse it with.  Raises if the dome should be there and could
        not be found, so that the caller flashes the point instead.
        """
        sat_value = targets[self._sat_index]
        target_index = self._i2 if self._sat_index == self._i1 else self._i1
        target = targets[target_index]

        if self._sat_value is None or sat_value != self._sat_value:
            # Record the outcome and the value it belongs to together.  Storing
            # the value first and letting the build raise past it would leave
            # the previous outcome -- None, meaning "no dome, nothing to
            # check" -- cached against the new value, and since an isoline in T
            # or p has the same saturation value at every point, one failed
            # build would disable the branch check for the whole line.
            bracket, failure = None, None
            try:
                bracket = self._build_bracket(sat_value, target_index)
            except Exception as e:
                failure = str(e)
            self._sat_value = sat_value
            self._bracket = bracket
            self._bracket_failure = failure
        if self._bracket_failure is not None:
            raise ValueError(self._bracket_failure)
        if self._bracket is None:
            # Above the dome; a single-phase root here needs no checking
            # because there is no other root to be confused with.
            return None

        bracket = dict(self._bracket)
        v_liq, v_vap = bracket['liq'][0], bracket['vap'][0]
        bracket['target'] = target
        bracket['two_phase'] = (not bracket['degenerate']
                                and min(v_liq, v_vap) < target < max(v_liq, v_vap))
        # Which single-phase branch the point sits on.  Following the bracket
        # rather than the previous point is what keeps the iteration on the
        # correct root where an isoline crosses the saturation curve.  The
        # midpoint and the slope are used rather than the two bracket values
        # because for an azeotropic mixture the bubble and dew values can
        # agree to within round-off, and then their order is noise: R513A's
        # bubble and dew pressures come within 1.4e-9 relative of each other
        # near 305 K, below BRACKET_RTOL.
        slope = bracket['slope']
        if bracket['two_phase']:
            bracket['side'] = None
        elif slope is not None:
            bracket['side'] = self.LIQUID if (target - 0.5 * (v_liq + v_vap)) * slope > 0 \
                else self.VAPOUR
        elif not bracket['degenerate']:
            # No slope, but a bracket this wide still separates the branches
            bracket['side'] = self.LIQUID if (target - v_liq) * (v_liq - v_vap) > 0 \
                else self.VAPOUR
        else:
            raise ValueError("Cannot tell which side of the saturation curve "
                             "this point is on.")
        return bracket

    def _build_bracket(self, sat_value, target_index):
        """Saturation states at ``sat_value``, or None if there is no dome there

        Raises rather than returning None when the dome should exist but could
        not be found: an unbracketed point is only safe where there is nothing
        to bracket, and everywhere else the caller has to flash it instead.
        """
        # The bracket is attempted even beyond the reported extent of the dome,
        # because that extent is only a lower bound and a saturation state
        # that really does exist is better evidence than the limit.  A call
        # that fails, or that returns a state the envelope says cannot be on
        # the dome, then falls back on the limit to decide whether it came up
        # empty for want of a dome or for want of a solver.
        ends = {}
        try:
            for name, quality in (('liq', 0.0), ('vap', 1.0)):
                self._saturation_endpoint(sat_value, quality)
                ends[name] = (self._sat.keyed_output(target_index),
                              self._sat.T(), self._sat.rhomolar())
                if not self._is_plausible_saturation(self._sat.T(), self._sat.p()):
                    raise ValueError(
                        "The saturation solver returned a state at T={0:g} K, "
                        "p={1:g} Pa, beyond any possible dome.".format(
                            self._sat.T(), self._sat.p()))
        except Exception:
            if self._dome_limit is not None and sat_value > self._dome_limit:
                return None
            if self._beyond_the_envelope_top(sat_value):
                # A closed envelope ends at the critical point to within a
                # fraction of a kelvin: beyond its top there is no dome that
                # a saturation call could find. The root is still checked
                # by _check_outside_the_dome.
                return None
            raise
        v_liq, v_vap = ends['liq'][0], ends['vap'][0]
        if not (np.isfinite(v_liq) and np.isfinite(v_vap)):
            raise ValueError("The saturation states are not finite.")
        # A saturation solver that converged on the wrong branch, or onto the
        # trivial solution with both phases at one density, would make every
        # branch decision below meaningless.
        if not ends['liq'][2] > ends['vap'][2] * (1.0 + _TRIVIAL_SOLUTION_RTOL):
            raise ValueError("The saturation states are not on their own branches.")
        degenerate = abs(v_vap - v_liq) <= self.BRACKET_RTOL * max(abs(v_liq), abs(v_vap), 1e-30)
        return {'target_index': target_index, 'liq': ends['liq'], 'vap': ends['vap'],
                'degenerate': degenerate,
                'slope': self._branch_slope(target_index, ends['liq'])}

    def _beyond_the_envelope_top(self, sat_value):
        """Whether a closed envelope puts ``sat_value`` (T or p) past its top"""
        if self._envelope_top is None:
            return False
        top = self._envelope_top[0] if self._sat_index == CoolProp.iT else self._envelope_top[1]
        return sat_value > top

    def _branch_slope(self, target_index, liquid_end):
        """Sign of the target property along density at the saturated liquid

        A point whose target property lies on the same side of the saturation
        curve as this slope points sits on the liquid branch.  Returns None if
        the derivative is unavailable, in which case the branch is left to the
        previous point.
        """
        try:
            self._sp.update(CoolProp.DmolarT_INPUTS, liquid_end[2], liquid_end[1])
            slope = self._sp.first_partial_deriv(target_index, CoolProp.iDmolar, self._sat_index)
        except Exception:
            return None
        if not np.isfinite(slope) or slope == 0.0:
            return None
        return slope

    # -------------------------------------------------------------------
    # Two-phase point: solve for the vapour quality
    # -------------------------------------------------------------------
    @staticmethod
    def _quality_scale(target_index, target):
        """The function of the target property that is close to linear in the quality

        Enthalpy, entropy and internal energy are (for a pure fluid exactly)
        linear in the vapour quality; density is not, but the specific
        volume is. Solving in that function lets the secant iteration below
        settle in two or three saturation calls instead of six. A density
        target that is not positive (nonsense, but possible) is solved as
        it is.
        """
        if target_index in (CoolProp.iDmolar, CoolProp.iDmass) and target > 0.0:
            return lambda value: 1.0 / value
        return lambda value: value

    def _quality_residual(self, quality, bracket):
        """How far the two-phase state at this quality is from the target, in the scale of _quality_scale"""
        if self._sat_index == CoolProp.iT:
            self._sat.update(CoolProp.QT_INPUTS, quality, self._sat_value)
        else:
            self._sat.update(CoolProp.PQ_INPUTS, self._sat_value, quality)
        scale = bracket['scale']
        return scale(self._sat.keyed_output(bracket['target_index'])) - scale(bracket['target'])

    def _solve_quality(self, bracket):
        """The vapour quality between the saturation states that hits the target

        Along a line the quality changes little from one point to the next,
        so a secant iteration from the previous quality usually needs two
        or three saturation calls. The first point of a line, and any point
        the secant cannot settle, uses a bracketed regula falsi over the
        whole dome (five or six calls). The saturation calls are what a
        two-phase point costs (an isentrope of R410A in a p-h chart spent
        60 % of its time in them).
        """
        scale = bracket['scale'] = self._quality_scale(bracket['target_index'], bracket['target'])
        target = scale(bracket['target'])
        fa, fb = scale(bracket['liq'][0]) - target, scale(bracket['vap'][0]) - target
        if fa * fb > 0.0:
            raise ValueError("The saturation bracket does not contain the target.")
        width = abs(fb - fa)
        quality = self._secant_quality(bracket, fa, fb, width)
        if quality is None:
            quality = self._bracketed_quality(bracket, fa, fb, width)
        self._out = self._sat
        self._last_quality = quality
        try:
            self._last_two_phase = (self._sat.T(), self._sat.rhomolar())
        except Exception:
            self._last_two_phase = None
        # A two-phase point says nothing about the single-phase root.
        self._T = np.nan
        self._rhomolar = np.nan
        self._side = None

    def _secant_quality(self, bracket, fa, fb, width):
        """Secant iteration from the previous point's quality; None if it does not settle"""
        if self._last_quality is None:
            return None
        tolerance = self.QUALITY_RTOL * width
        q0 = min(max(self._last_quality, 1e-6), 1.0 - 1e-6)
        f0 = self._quality_residual(q0, bracket)
        if abs(f0) <= tolerance:
            return q0
        slope = fb - fa   # the dome crossed in one step, the first guess of the slope
        q1 = q0 - f0 / slope
        for _ in range(8):
            if not np.isfinite(q1) or not 0.0 < q1 < 1.0:
                return None
            f1 = self._quality_residual(q1, bracket)
            if abs(f1) <= tolerance:
                return q1
            if f1 == f0:
                return None
            slope = (f1 - f0) / (q1 - q0)
            q0, f0 = q1, f1
            q1 = q0 - f0 / slope
        return None

    def _bracketed_quality(self, bracket, fa, fb, width):
        """Regula falsi (Illinois) on the vapour quality between the saturation states"""
        a, b = 0.0, 1.0
        for _ in range(self.QUALITY_ITMAX):
            quality = b - fb * (b - a) / (fb - fa)
            # The endpoints are already known and a regula falsi can creep onto
            # them, so keep every trial strictly inside the bracket.
            lo, hi = min(a, b), max(a, b)
            if not np.isfinite(quality) or not lo < quality < hi:
                quality = 0.5 * (lo + hi)
            fq = self._quality_residual(quality, bracket)
            # NaN would compare as "same side" below and pass the residual gate
            if not np.isfinite(fq):
                raise ValueError("The quality solver met a residual that is not a number.")
            if fq * fb < 0.0:
                a, fa = b, fb
            else:
                fa *= 0.5  # Illinois: stops the retained endpoint from stalling
            b, fb = quality, fq
            if fq == 0.0 or abs(b - a) < self.QUALITY_XTOL:
                break
        else:
            raise ValueError("The quality solver did not converge.")
        # A bracket built on a bad saturation state can be wide enough to
        # appear to contain a target the two-phase region never reaches, and
        # then the iteration runs out of interval with the residual intact.
        if not abs(fb) <= self.QUALITY_RTOL * width:
            raise ValueError("The quality solver ran out of bracket with the "
                             "residual unresolved.")
        return b

    # -------------------------------------------------------------------
    # Single-phase point: Newton iteration in (T, rhomolar)
    # -------------------------------------------------------------------
    def _seed(self, bracket):
        """Pick the initial (T, rhomolar), preferring the previous point"""
        side = None if bracket is None else bracket['side']
        if np.isfinite(self._T) and np.isfinite(self._rhomolar) \
                and (side is None or self._side is None or side == self._side):
            return self._T, self._rhomolar
        if bracket is not None:
            end = bracket['liq'] if side == self.LIQUID else bracket['vap']
            return end[1], end[2]
        if self._last_two_phase is not None:
            # Beyond the dome right after a two-phase point, which happens
            # where a line leaves the dome through its top: the bulk state
            # of that point is close to the root, and the root is checked
            # against the dome like any other unbracketed one.
            return self._last_two_phase
        raise ValueError("No initial guess is available for the Newton iteration.")

    def _solve_single_phase(self, targets, bracket):
        """Newton iteration in (T, rhomolar) onto both target properties

        Raises unless it settles on a root that is checked, in range, and on
        the side of the saturation curve the bracket says it should be.
        """
        T, rhomolar = self._seed(bracket)
        state = self._sp
        for _ in range(self.NEWTON_ITMAX):
            state.update(CoolProp.DmolarT_INPUTS, rhomolar, T)
            residual, jacobian = self._newton_system(targets)
            dT, dD = self._newton_step(residual, jacobian)
            if abs(dT) <= self.NEWTON_RTOL * T and abs(dD) <= self.NEWTON_RTOL * rhomolar:
                self._check_residual(residual, jacobian, T, rhomolar)
                self._check_in_range(T)
                side = None if bracket is None else bracket['side']
                self._check_branch(bracket, side, T, rhomolar)
                self._T, self._rhomolar = T, rhomolar
                self._side = side
                self._out = state
                return
            damp = 1.0
            if abs(dT) > self.NEWTON_TRUST * T:
                damp = min(damp, self.NEWTON_TRUST * T / abs(dT))
            if abs(dD) > self.NEWTON_TRUST * rhomolar:
                damp = min(damp, self.NEWTON_TRUST * rhomolar / abs(dD))
            T += damp * dT
            rhomolar += damp * dD
            if not (T > 0.0 and rhomolar > 0.0):
                raise ValueError("The Newton iteration left the physical domain.")
        raise ValueError("The Newton iteration did not converge.")

    def _newton_system(self, targets):
        """(residuals, Jacobian) of the two target properties at the state ``self._sp`` holds

        The Jacobian is ((J11, J12), (J21, J22)): the derivatives of the two
        properties with respect to T and rhomolar.
        """
        i1, i2, state = self._i1, self._i2, self._sp
        residual = (state.keyed_output(i1) - targets[i1], state.keyed_output(i2) - targets[i2])
        jacobian = ((state.first_partial_deriv(i1, CoolProp.iT, CoolProp.iDmolar),
                     state.first_partial_deriv(i1, CoolProp.iDmolar, CoolProp.iT)),
                    (state.first_partial_deriv(i2, CoolProp.iT, CoolProp.iDmolar),
                     state.first_partial_deriv(i2, CoolProp.iDmolar, CoolProp.iT)))
        return residual, jacobian

    @staticmethod
    def _newton_step(residual, jacobian):
        """The Newton step (dT, drhomolar) that solves the linearised system"""
        (f1, f2), ((J11, J12), (J21, J22)) = residual, jacobian
        det = J11 * J22 - J12 * J21
        if not np.isfinite(det) or det == 0.0:
            raise ValueError("The Newton iteration hit a singular Jacobian.")
        dT = (J12 * f2 - J22 * f1) / det
        dD = (J21 * f1 - J11 * f2) / det
        if not (np.isfinite(dT) and np.isfinite(dD)):
            raise ValueError("The Newton iteration produced a non-finite step.")
        return dT, dD

    def _check_residual(self, residual, jacobian, T, rhomolar):
        """Reject a settled iteration whose residual is still large

        A small step is not by itself a small residual: where the Jacobian
        is large -- cv near the critical point, say -- the iteration can
        stall with the residual intact.  Each residual is scaled by how
        much its property moves over the iteration variables, which is
        finite and non-zero even for an enthalpy that happens to sit near
        its reference value.
        """
        (f1, f2), ((J11, J12), (J21, J22)) = residual, jacobian
        scale1 = abs(J11) * T + abs(J12) * rhomolar
        scale2 = abs(J21) * T + abs(J22) * rhomolar
        if not (np.isfinite(scale1) and np.isfinite(scale2)):
            raise ValueError("The residual cannot be scaled at this point.")
        if abs(f1) > self.RESIDUAL_RTOL * scale1 or abs(f2) > self.RESIDUAL_RTOL * scale2:
            raise ValueError("The Newton iteration stalled with the residual unresolved.")

    #: How far past the equation of state's stated temperature range a root
    #: may sit.  Deliberately loose: this is not a validity check.  CoolProp
    #: answers a PT flash well outside the fitted range and so would the
    #: fallback this hands back to, so a tighter bound would only make traced
    #: and flashed points on the same isoline obey different rules.  What it
    #: catches is an iteration that has run away entirely -- an R504 isochore
    #: reaching four hundred times the maximum temperature.
    RANGE_FACTOR = 2.0

    def _check_in_range(self, T):
        """Reject a root the Newton iteration has run away with"""
        upper = self._eos_bounds.get(CoolProp.iT)
        lower = self._eos_bounds.get('T_min')
        if (upper is not None and T > upper * self.RANGE_FACTOR) \
                or (lower is not None and T < lower / self.RANGE_FACTOR):
            raise ValueError("The Newton iteration converged at T={0:g} K, far "
                             "outside the range of the equation of state.".format(T))

    def _check_branch(self, bracket, side, T, rhomolar):
        """Reject a root that ended up inside the two-phase dome

        With a bracket this is a comparison against the two saturation
        densities at the constant temperature (or pressure) it was built at: a
        liquid root is denser than the saturated liquid, a vapour root thinner
        than the saturated vapour, and a root that is neither is metastable or
        unstable and goes back to the caller to flash.

        Without one the point was taken to be beyond the dome, and that is
        checked here rather than assumed.  The reported extent of the phase
        envelope is not reliable enough to assume it: for several predefined
        blends the envelope trace stops well short of the real cricondentherm
        -- R504 by about 20 K -- and every point in between would otherwise be
        accepted unexamined, which is exactly where the dome is.
        """
        if bracket is None:
            self._check_outside_the_dome(T, rhomolar)
            return
        if side is None:
            return
        if side == self.LIQUID:
            limit = bracket['liq'][2]
            wrong = rhomolar < limit * (1.0 - self.BRANCH_RTOL)
        else:
            limit = bracket['vap'][2]
            wrong = rhomolar > limit * (1.0 + self.BRANCH_RTOL)
        if wrong:
            raise ValueError("The Newton iteration converged on the wrong side "
                             "of the saturation curve.")

    @staticmethod
    def _dome_density_table(data):
        """(T, bulk rhomolar) of the dew and the bubble branch of a phase envelope, each sorted by T

        CoolProp keeps the bulk phase in the "vap" fields on both branches.
        """
        T_K = np.asarray(data.T, dtype=float)
        rho = np.asarray(data.rhomolar_vap, dtype=float)
        Q = np.asarray(data.Q, dtype=float)
        tables = []
        for quality in (1.0, 0.0):
            rows = np.flatnonzero((Q == quality) & np.isfinite(T_K) & np.isfinite(rho))
            order = rows[np.argsort(T_K[rows])]
            tables.append((T_K[order], rho[order]))
        return tables

    def _far_from_the_dome(self, T, rhomolar):
        """Whether a root is clear of the dome a closed envelope describes at its temperature

        Used where the saturation solver does not answer, near the critical
        point: the densities of the dome there are read from the envelope
        instead, widened by TOP_DENSITY_MARGIN, and a root outside them
        cannot be in the dome. Above the top of the envelope its last
        densities are used. Only for closed envelopes, which run up to the
        critical point.
        """
        if self._dome_densities is None:
            return False
        rho_liq_top, rho_vap_top = self._envelope_top[2], self._envelope_top[3]
        top_is_critical = abs(rho_liq_top - rho_vap_top) <= self.TOP_GAP_RTOL * max(rho_liq_top, rho_vap_top)
        if top_is_critical and T > self._envelope_top[0] * (1.0 + self.ABOVE_TOP_RTOL):
            return True
        bounds = []
        for T_table, rho_table in self._dome_densities:
            if len(T_table) < 2:
                return False
            bounds.append(float(np.interp(T, T_table, rho_table)))   # clamps beyond the table's ends
        rho_lo, rho_hi = min(bounds), max(bounds)
        return rhomolar > rho_hi * self.TOP_DENSITY_MARGIN or rhomolar < rho_lo / self.TOP_DENSITY_MARGIN

    def _check_outside_the_dome(self, T, rhomolar):
        """Confirm there is no two-phase region around this root

        A saturation call that succeeds here gives the two densities to
        compare against directly.  One that fails is not the reassurance it
        looks like: when the isoline is indexed by temperature this is the
        same call, at the same temperature, that :func:`_build_bracket`
        already gave up on, so it can add nothing.  Treating that as "no dome"
        left a band of about ten kelvin on R504 -- between where the
        saturation solver stops converging and the real critical point at
        335.5 K, which its phase envelope stops 37 K short of -- in which
        roots inside the dome were accepted unexamined.  So a failure only
        counts as an answer above the temperature where a dome could exist at
        all; below it the point goes back to the caller to flash.
        """
        if self._dome_T_limit is not None and T > self._dome_T_limit:
            return          # above the critical point; there is no dome to be in
        undecided = None
        try:
            self._sat.update(CoolProp.QT_INPUTS, 0.0, T)
            rho_liq, p_liq = self._sat.rhomolar(), self._sat.p()
            self._sat.update(CoolProp.QT_INPUTS, 1.0, T)
            rho_vap, p_vap = self._sat.rhomolar(), self._sat.p()
        except Exception:
            undecided = "the saturation solver did not converge"
        # A NaN would slip through both checks below: max() drops a NaN p_vap,
        # and a NaN density makes the inside-the-dome test false
        if undecided is None and not all(np.isfinite([p_liq, p_vap, rho_liq, rho_vap])):
            undecided = "the saturation solver returned a value that is not a number"
        if undecided is None and not self._is_plausible_saturation(T, max(p_liq, p_vap)):
            undecided = "the saturation solver left the dome behind"
        if undecided is None and not _phases_are_distinct(self._sat):
            # Same trivial solution the bracket has to reject: a positive but
            # vanishing density gap is the solver collapsing both phases, not
            # a narrow dome, and it would let a root inside one through.
            undecided = "the saturation states are not on their own branches"
        if undecided is not None:
            bound = self._dome_T_limit
            if bound is None or T <= bound:
                if self._far_from_the_dome(T, rhomolar):
                    return  # near the critical point, but away from what is left of the dome
                raise ValueError("This root cannot be shown to be outside the "
                                 "two-phase dome: {0}.".format(undecided))
            return          # above any possible dome, so there is none to be in
        if rho_vap < rhomolar < rho_liq:
            raise ValueError("The Newton iteration converged inside the "
                             "two-phase dome.")
