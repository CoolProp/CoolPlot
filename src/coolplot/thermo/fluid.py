# -*- coding: utf-8 -*-
"""Access to CoolProp for the rest of CoolPlot.

:class:`Fluid` wraps a ``CoolProp.AbstractState`` instead of inheriting from
it. The previous design subclassed AbstractState, which broke when CoolProp
moved its Python bindings to a different technology (pybind11). Wrapping
keeps CoolPlot independent of how the bindings are implemented and gives
one place to cache fluid constants such as the critical point.

A Fluid is not thread safe because the wrapped state is mutated by every
calculation. Use :meth:`Fluid.clone` to give a worker thread its own copy.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from functools import lru_cache
from typing import Optional, Tuple

import numpy as np

import CoolProp
from CoolProp import AbstractState
from CoolProp import CoolProp as CP

from ..core.errors import PropertyError
from ..core.quantities import get_quantity, quantity_key
from ..core.state import STATE_KEYS, StatePoint
from ..core.floats import is_zero, same_bits


@lru_cache(maxsize=None)
def parameter_index(key: str) -> int:
    """CoolProp parameter index for a CoolPlot quantity key, e.g. "p" -> iP."""
    name = get_quantity(key).coolprop_name
    if name is None:
        raise ValueError("'{0}' is not a quantity of a fluid state.".format(key))
    return CP.get_parameter_index(name)


#: Binary interaction parameters copied when a state is snapshotted.
INTERACTION_KEYS = ("betaT", "gammaT", "betaV", "gammaV", "Fij", "kij")


def _as_density(key: str, value_SI: float) -> Tuple[str, float]:
    """A specific volume given as an input becomes the density CoolProp works with."""
    if key == "v":
        if not value_SI > 0.0:
            raise ValueError("A specific volume has to be positive, not {0}.".format(value_SI))
        return "rho", 1.0 / value_SI
    return key, value_SI


def model_from_state(state: AbstractState) -> Tuple:
    """Snapshot of the fluid model of an AbstractState, as plain data.

    Returns (backend, components, fractions, basis, interactions) with the
    same meaning as the fields of :class:`coolplot.spec.FluidSpec`. Later
    changes to the state do not affect the snapshot, which is the point:
    a diagram must not change behind the user's back.
    """
    backend = state.backend_name()
    try:
        components = tuple(state.fluid_names())
    except Exception:
        raise ValueError("CoolProp cannot report the fluid of this {0} state; pass a fluid string "
                         "such as 'INCOMP::MEG[0.3]' instead.".format(backend))
    fractions = ()
    interactions = []
    if len(components) > 1:
        fractions = tuple(float(x) for x in state.get_mole_fractions())
        for i in range(len(components)):
            for j in range(i + 1, len(components)):
                for key in INTERACTION_KEYS:
                    try:
                        interactions.append((i, j, key, float(state.get_binary_interaction_double(i, j, key))))
                    except Exception:
                        continue   # parameter not used by this backend
    return backend, components, fractions, "mole", tuple(interactions)


def model_from_string(text: str, basis: str = None) -> Tuple:
    """Fluid model from a CoolProp fluid string, using CoolProp's own parser.

    Fractions are mole fractions, except for the INCOMP backend, where
    CoolProp reads them as mass fractions; ``basis`` overrides this.
    """
    backend, names = CP.extract_backend(text)
    names, values = CP.extract_fractions(names)
    if backend in ("?", ""):
        backend = "HEOS"
    if basis is None:
        basis = "mass" if backend.upper() == "INCOMP" else "mole"
    components = tuple(names.split("&")) if isinstance(names, str) else tuple(names)
    fractions = tuple(float(v) for v in values) if len(values) == len(components) and (
        len(components) > 1 or "[" in text) else ()
    return backend, components, fractions, basis, ()


def build_state(model: Tuple) -> AbstractState:
    """A fresh AbstractState for a model tuple (see :func:`model_from_state`)."""
    backend, components, fractions, basis, interactions = model
    state = AbstractState(backend, "&".join(components))
    if fractions:
        if basis == "mole":
            state.set_mole_fractions(list(fractions))
        elif basis == "mass":
            state.set_mass_fractions(list(fractions))
        elif basis == "volu":
            state.set_volu_fractions(list(fractions))
        else:
            raise ValueError("Unknown fraction basis '{0}'.".format(basis))
    for i, j, key, value in interactions:
        state.set_binary_interaction_double(int(i), int(j), key, float(value))
    return state


class Fluid:
    """A fluid model with its own CoolProp state and cached constants

    Parameters
    ----------
    fluid : FluidSpec, str or CoolProp.AbstractState
        A :class:`coolplot.spec.FluidSpec` (or any object with the fields
        backend, components, fractions, basis and interactions), a CoolProp
        fluid string like "HEOS::R32[0.7]&R125[0.3]", or an AbstractState.
        An AbstractState is copied: the Fluid never modifies it, and later
        changes to it have no effect.
    fractions : str, optional
        Basis of the fractions in a fluid string: "mole", "mass" or "volu".
        Default: "mass" for the INCOMP backend, "mole" otherwise.
    """

    kind = "fluid"
    #: The quantities a state of a fluid holds, and those it may be given by.
    quantities = STATE_KEYS
    inputs = STATE_KEYS

    def __init__(self, fluid, fractions: str = None):
        if isinstance(fluid, AbstractState):
            model = model_from_state(fluid)
            name = "&".join(model[1])
        elif isinstance(fluid, str):
            model = model_from_string(fluid, fractions)
            name = fluid
        elif all(hasattr(fluid, f) for f in ("backend", "components", "fractions", "basis", "interactions")):
            model = (fluid.backend, tuple(fluid.components), tuple(fluid.fractions), fluid.basis,
                     tuple(tuple(x) for x in fluid.interactions))
            name = str(fluid)
        else:
            raise TypeError("Expected a FluidSpec, a fluid string or a CoolProp.AbstractState.")
        state = build_state(model)
        if len(model[1]) == 1:
            # A predefined blend such as "R407C.mix" is one name for several
            # components; describe it by those, so that it is treated as the
            # mixture it is (tracer, phase envelope) and gets the same model
            # key as the same blend given as an AbstractState.
            try:
                if len(state.fluid_names()) > 1:
                    model = model_from_state(state)
            except Exception:
                pass   # INCOMP and others cannot report their components
        self._model = model
        self._state = state
        self._reset_caches()
        self._name = name

    def _reset_caches(self):
        self._critical = None
        self._has_critical = None
        self._envelope = None
        self._guide = None         # scratch state for difficult saturation states, see update()
        self._components = None    # pure states of the components of a mixture, see _component_states()
        self._fingerprint = None
        self._current = self._state   # the state the last update() set; get() reads it

    def __repr__(self):
        return "Fluid({0!r})".format(self._name)

    # Identity --------------------------------------------------------------
    @property
    def name(self) -> str:
        """The fluid as given, e.g. "HEOS::R290"."""
        return self._name

    @property
    def state(self) -> AbstractState:
        """The working state. Every calculation overwrites its thermodynamic state."""
        return self._state

    @property
    def model_key(self) -> Tuple:
        """(backend, components, fractions, basis, interactions): everything
        that determines the properties, so it can serve as a cache key."""
        return self._model

    def with_backend(self, backend: str) -> "Fluid":
        """The same fluid model on another CoolProp backend."""
        twin = Fluid.__new__(Fluid)
        twin._model = (backend,) + tuple(self._model[1:])
        twin._state = build_state(twin._model)
        twin._reset_caches()
        twin._name = "{0}::{1}".format(backend, "&".join(self._model[1]))
        return twin

    def clone(self) -> "Fluid":
        """An independent Fluid with the same model, for example for a worker thread."""
        twin = Fluid.__new__(Fluid)
        twin._model = self._model
        twin._state = build_state(self._model)
        twin._reset_caches()
        twin._critical = self._critical
        # The phase envelope is not shared: it keeps a CoolProp state of its
        # own for its lookups, so each clone (a worker thread) builds its own
        twin._name = self._name
        return twin

    # Property evaluation ---------------------------------------------------
    def update(self, key1: str, value1_SI: float, key2: str, value2_SI: float) -> AbstractState:
        """Set the working state from two quantities given by CoolPlot keys.

        See :meth:`update_pair` for what happens with mixtures. Returns the
        state that holds the result; :meth:`get` reads it.
        """
        inputs = ((quantity_key(key1), float(value1_SI)), (quantity_key(key2), float(value2_SI)))
        try:
            (key1, value1_SI), (key2, value2_SI) = (_as_density(k, v) for k, v in inputs)
            pair, v1, v2 = CP.generate_update_pair(parameter_index(key1), value1_SI,
                                                   parameter_index(key2), value2_SI)
            return self.update_pair(pair, v1, v2)
        except PropertyError:
            raise
        except ValueError as e:
            reason, limits = self.diagnose(inputs, str(e))
            raise PropertyError(self.name, inputs, str(e), reason=reason, limits=limits) from None

    def diagnose(self, inputs, message: str = "") -> Tuple[str, Tuple]:
        """Why a state cannot be computed, in plain words, as far as the fluid can tell.

        Returns (reason, limits) for :class:`coolplot.core.errors.PropertyError`:
        an input outside the range of the equation of state, a vapour
        quality above the critical point, or an input pair CoolProp does
        not solve for mixtures. ``message`` is what CoolProp said. The
        reason is empty when nothing is obviously wrong.
        """
        given = {quantity_key(k): float(v) for k, v in inputs}
        for key, low, high, what in (("T", self.T_min_K, self.T_max_K, "temperature"),
                                     ("p", self.p_min_Pa, self.p_max_Pa, "pressure")):
            value = given.get(key)
            if value is None:
                continue
            if low is not None and value < low * (1.0 - 1e-9):
                return "{0} is below the lowest {1} of the equation of state, {{0}}".format(key, what), ((key, low),)
            if high is not None and value > high * (1.0 + 1e-9):
                return "{0} is above the highest {1} of the equation of state, {{0}}".format(key, what), ((key, high),)
        if "Q" in given:
            return self._diagnose_quality(given)
        if "not yet supported" in message or "not ready for mixtures" in message:
            keys = " and ".join(sorted(given))
            return ("CoolProp does not solve a mixture from {0}; it solves p with any other quantity, and T with "
                    "p, rho or Q".format(keys)), ()
        return "", ()

    def _diagnose_quality(self, given: dict) -> Tuple[str, Tuple]:
        Q = given["Q"]
        if not self.has_critical_point:
            return "{0} has no two-phase region, so no state can be given by Q".format(self.name), ()
        if not 0.0 <= Q <= 1.0:
            return "a vapour quality has to be between 0 and 1", ()
        crit = self.critical
        for key, name in (("T", "temperature"), ("p", "pressure")):
            value = given.get(key)
            if value is not None and value > crit[key] * (1.0 - 1e-9):
                return ("{0} is above the critical {1} {{0}}, where there is no two-phase region to give a quality "
                        "in".format(key, name)), ((key, crit[key]),)
        return "", ()

    def update_pair(self, pair, value1: float, value2: float) -> AbstractState:
        """Set the working state from a CoolProp input pair and its two values.

        For a mixture, a state that CoolProp cannot find is tried once more
        on a separate scratch state that has the phase envelope built:
        CoolProp's mixture solvers take their starting values from it. That
        rescues most condenser and evaporator states of blends, for example
        the dew point of R32/R125 (70/30) at 26.6 bar. The working state is
        never changed by this, so every other calculation gives the same
        result whatever was computed before.

        A mixture state that CoolProp returns without raising is also
        checked, see :meth:`inconsistency`: CoolProp 8 answers some inputs
        inside the two-phase region with a single-phase state whose pressure
        and enthalpy belong to another density. Such a state raises
        ValueError here instead of being drawn.

        Returns the state that holds the result; :meth:`get` reads it.
        """
        self._current = self._state
        try:
            self._state.update(pair, value1, value2)
        except Exception:
            guide = self._guide_state() if not self.is_pure else None
            if guide is None:
                raise
            guide.update(pair, value1, value2)
            self._current = guide
        problem = self.inconsistency(self._current)
        if problem is not None:
            raise ValueError("CoolProp returned an inconsistent state for {0}: {1}".format(self.name, problem))
        if self._current is not self._state:
            # The check used the guide state for its saturation lookups; put
            # the requested state back on it
            self._current.update(pair, value1, value2)
        return self._current

    def inconsistency(self, state: AbstractState) -> Optional[str]:
        """Why a state of a mixture cannot be right, or None if it passes.

        Below the critical temperature of the mixture a single-phase state
        cannot be denser than the saturated vapour and less dense than the
        saturated liquid at its temperature: those densities bound the
        two-phase region. CoolProp 8's T,rho flash of mixtures reports such
        states as "gas" with Q = -1 (R407C at 100 kg/m3 and 264 K, for
        example), with a pressure and enthalpy that belong to a different
        density. Pure fluids are not checked: their flashes are reliable.
        """
        if self.is_pure:
            return None
        try:
            Q = state.Q()
            if 0.0 <= Q <= 1.0:
                return None   # two-phase states come out of the saturation solver itself
            T_K, rho = state.T(), state.rhomolar()
        except Exception:
            return None
        if not self.has_critical_point or T_K >= self.critical["T"] * (1.0 - 1e-6):
            return None   # above the critical temperature there is no dome to be in (retrograde regions excluded)
        guide = self._guide_state()
        if guide is None:
            return None
        try:
            guide.update(CoolProp.QT_INPUTS, 1.0, T_K)
            rho_vap = guide.rhomolar()
            guide.update(CoolProp.QT_INPUTS, 0.0, T_K)
            rho_liq = guide.rhomolar()
        except Exception:
            return None   # no saturation state at this temperature: nothing to compare with
        if rho_vap * (1.0 + 1e-6) < rho < rho_liq * (1.0 - 1e-6):
            return ("reported as single phase at T = {0:.2f} K with rho = {1:.4g} mol/m3, between the saturated "
                    "vapour ({2:.4g}) and liquid ({3:.4g}) densities, i.e. inside the two-phase region"
                    .format(T_K, rho, rho_vap, rho_liq))
        return None

    def _guide_state(self) -> Optional[AbstractState]:
        """A scratch state with the phase envelope built, made once; None if that fails."""
        if self._guide is None:
            self._guide = False
            try:
                guide = build_state(self._model)
                guide.build_phase_envelope("veryfine")
                self._guide = guide
            except Exception:
                pass
        return self._guide or None

    def get(self, key: str) -> float:
        """Read one quantity of the state set by the last :meth:`update`, in SI units."""
        if quantity_key(key) == "v":
            return 1.0 / self._current.keyed_output(CoolProp.iDmass)
        return self._current.keyed_output(parameter_index(key))

    def state_point(self, key1: str, value1_SI: float, key2: str, value2_SI: float) -> StatePoint:
        """The full state from two quantities, e.g. state_point("p", 1e5, "T", 300)."""
        self.update(key1, value1_SI, key2, value2_SI)
        return StatePoint(**{k: self.get(k) for k in STATE_KEYS})

    def path_kind(self, a: StatePoint, b: StatePoint, kind: str) -> str:
        """How the path between two states of a cycle is drawn; "auto" is
        resolved from the states by :func:`coolplot.thermo.cycles.auto_kind`."""
        return kind

    def properties(self, keys=("T", "p", "h", "s", "rho", "Q")) -> dict:
        """Read several quantities of the working state in SI units."""
        return {k: self.get(k) for k in keys}

    # Fluid constants -------------------------------------------------------
    def _trivial(self, index) -> Optional[float]:
        try:
            value = self._state.trivial_keyed_output(index)
        except Exception:
            return None
        return value if np.isfinite(value) else None

    def _component_states(self):
        """One pure state per component of a mixture (None if that fails), made once."""
        if self._components is None:
            self._components = False
            if not self.is_pure:
                try:
                    self._components = [AbstractState(self._model[0], name) for name in self._model[1]]
                except Exception:
                    pass
        return self._components or None

    def _lowest_temperature(self, index) -> Optional[float]:
        """A lower temperature limit: for a mixture the highest one of its components.

        CoolProp reports the mole-weighted average of the components' values
        for a mixture (129 K for R32/R1234yf 50/50, although R32 is solid
        below 136.3 K), which is below where any component's equation of
        state is valid, and CoolProp's own flashes contradict each other
        there.
        """
        value = self._trivial(index)
        components = self._component_states()
        if components:
            found = []
            for component in components:
                try:
                    v = component.trivial_keyed_output(index)
                except Exception:
                    continue
                if np.isfinite(v):
                    found.append(v)
            if found:
                value = max(found) if value is None else max([value] + found)
        return value

    @property
    def T_triple_K(self) -> Optional[float]:
        """The triple-point temperature in K, or None (for a mixture the highest one of its components)."""
        return self._lowest_temperature(CoolProp.iT_triple)

    @property
    def T_min_K(self) -> Optional[float]:
        """The lowest temperature of the equation of state in K, or None."""
        return self._lowest_temperature(CoolProp.iT_min)

    @property
    def T_max_K(self) -> Optional[float]:
        """The highest temperature of the equation of state in K, or None."""
        return self._trivial(CoolProp.iT_max)

    @property
    def p_min_Pa(self) -> Optional[float]:
        """The lowest pressure of the equation of state in Pa, or None."""
        return self._trivial(CoolProp.iP_min)

    @property
    def p_max_Pa(self) -> Optional[float]:
        """The highest pressure of the equation of state in Pa, or None."""
        return self._trivial(CoolProp.iP_max)

    @property
    def is_pure(self) -> bool:
        """Whether the fluid has one component."""
        return len(self._model[1]) == 1

    @property
    def has_critical_point(self) -> bool:
        """Whether CoolProp provides a critical point, i.e. a saturation curve and a dome.

        Incompressible fluids (INCOMP backend) have none: no saturation range,
        no quality lines, no saturation states inserted into lines."""
        if self._has_critical is None:
            try:
                self.critical
                self._has_critical = True
            except ValueError:
                self._has_critical = False
        return self._has_critical

    @property
    def fingerprint(self) -> Tuple:
        """What identifies CoolProp's answers for this model beyond the model itself.

        CoolProp's version, its global configuration, and the enthalpy and
        entropy at one probe state (which move with the reference state set
        by ``set_reference_state``). Part of every cache key, so a curve
        computed under other settings is never served.
        """
        if self._fingerprint is None:
            version = getattr(CoolProp, "__version__", "")
            h, s = self._probe()
            self._fingerprint = (version, config_digest(), h, s)
        return self._fingerprint

    def _probe(self) -> Tuple[float, float]:
        """Enthalpy and entropy at one state of a new AbstractState, rounded; they move with the reference state."""
        h = s = float("nan")
        try:
            probe = build_state(self._model)
            T_max_K = self.T_max_K
            T_K = (300.0 if T_max_K is None or is_zero(T_max_K) else T_max_K) * (1.0 - 1e-6)
            p_Pa = max(0.0 if self.p_min_Pa is None else self.p_min_Pa, 1e5)
            probe.update(CoolProp.PT_INPUTS, p_Pa, T_K)
            h, s = probe.hmass(), probe.smass()
        except Exception:
            pass
        return round(h, 6), round(s, 6)

    def configuration_changed(self) -> bool:
        """Whether CoolProp's global configuration differs from the one this fluid was made under."""
        try:
            raw = CP.get_config_as_json_string()
        except Exception:
            raw = None
        if raw is not None and raw == getattr(self, "_config_seen", None):
            return False   # the same text as last time: nothing to digest
        changed = config_digest() != self.fingerprint[1]
        if not changed:
            self._config_seen = raw
        return changed

    def reference_state_changed(self) -> bool:
        """Whether ``set_reference_state`` moved this fluid's enthalpy or entropy since it was made.

        Costs one new AbstractState (0.1 ms for a pure fluid, a few ms for a
        blend), so the engine asks only before lines can go to disk.
        """
        h, s = self._probe()
        _, _, h0, s0 = self.fingerprint

        def same(a, b):
            # The same number, with NaN equal to NaN: the probe repeats one computation
            return same_bits(a, b) or (is_zero(a) and is_zero(b)) or (math.isnan(a) and math.isnan(b))
        return not (same(h, h0) and same(s, s0))

    @property
    def critical(self) -> dict:
        """Critical point properties in SI units, computed once and cached.

        Returns a dict with the keys of :data:`coolplot.quantities.QUANTITIES`
        except "Q". Raises ValueError if CoolProp cannot provide the point.
        """
        if self._critical is None:
            self._critical = _critical_point(self)
        return self._critical

    def phase_envelope(self) -> Optional[PhaseEnvelope]:
        """The phase envelope of a mixture, computed once; None for pure fluids or on failure."""
        if self._envelope is None:
            envelope = False   # remembers a failure, so it is not retried
            if not self.is_pure:
                try:
                    envelope = PhaseEnvelope(self)
                except Exception:
                    envelope = False
            self._envelope = envelope
        return self._envelope or None

    def saturation_range(self, key: str, margin: float = 1e-7) -> Tuple[float, float]:
        """Lowest and highest saturation temperature or pressure in SI units.

        The range starts slightly above the lowest valid temperature of the
        equation of state and ends slightly below the critical point, where
        the saturation solvers are reliable. ``margin`` is that distance,
        relative to the critical value (``Settings.calc.critical_margin``).
        """
        key = get_quantity(key).key
        if key not in ("T", "p"):
            raise ValueError("Saturation ranges are defined in T or p, not in '{0}'.".format(key))
        if not self.has_critical_point:
            raise ValueError("{0} has no saturation curve (CoolProp provides no critical point for it); give "
                             "absolute temperature and pressure limits, e.g. tp_limits=[T_min_K, T_max_K, "
                             "p_min_Pa, p_max_Pa].".format(self.name))
        crit = self.critical
        rel_small = float(margin)
        T_lo_K = max(v for v in (self.T_triple_K, self.T_min_K, 0.0) if v is not None)
        T_lo_K += crit["T"] * rel_small
        if key == "T":
            return T_lo_K, crit["T"] * (1.0 - rel_small)
        self.update("Q", 0.0, "T", T_lo_K)
        return self.get("p") * (1.0 + rel_small), crit["p"] * (1.0 - rel_small)


class PhaseEnvelope:
    """The two-phase boundary of a mixture, from CoolProp's phase envelope

    The envelope runs along the dew line (Q = 1) up through the critical
    region and back down the bubble line (Q = 0). For every point it holds
    temperature, pressure and the density of the bulk phase, which has the
    overall composition. Further properties are evaluated on demand with
    :meth:`values` and kept.

    CoolProp stores the bulk phase in the "vap" fields and the incipient
    phase in the "liq" fields on both branches, so the bulk density is
    always ``rhomolar_vap``.

    ``closed`` says whether the envelope ran up to the critical point: its
    two densities then meet at its hottest point, which :meth:`top` gives.
    An envelope that stopped early (R504's ends 37 K below the critical
    point) says nothing about where the dome ends.
    """

    #: An envelope whose two densities at the hottest point still differ by
    #: more than this, relatively, did not reach the critical point.
    CLOSED_RTOL = 0.35

    def __init__(self, fluid: "Fluid"):
        work = build_state(fluid.model_key)
        data = None
        for level in ("veryfine", "none"):   # about 300 points; 60 if refining fails
            try:
                work.build_phase_envelope(level)
                data = work.get_phase_envelope_data()
                break
            except Exception:
                continue
        if data is None:
            raise ValueError("CoolProp could not build the phase envelope of {0}.".format(fluid.name))
        self._work = work
        self.Q = _read_only(data.Q)
        rhomolar = _read_only(data.rhomolar_vap)
        self._values = {"T": _read_only(data.T), "p": _read_only(data.p), "Q": self.Q,
                        "rho": _read_only(rhomolar * work.molar_mass())}
        self._rhomolar = rhomolar
        if not (np.any(self.Q < 0.5) and np.any(self.Q > 0.5)):   # flags: Q = 0 bubble, Q = 1 dew
            raise ValueError("The phase envelope of {0} has no bubble or no dew line.".format(fluid.name))
        self._hot = int(np.argmax(self._values["T"]))
        rho_liq, rho_vap = float(data.rhomolar_liq[self._hot]), float(rhomolar[self._hot])
        self.closed = bool(abs(rho_liq - rho_vap) <= self.CLOSED_RTOL * max(rho_liq, rho_vap))

    def top(self, key: str) -> float:
        """A property at the hottest point of the envelope, the critical point when ``closed``."""
        return float(self.values(key)[self._hot])

    def __len__(self):
        return len(self.Q)

    def values(self, key: str) -> np.ndarray:
        """A property along the envelope in SI units, NaN where it fails.

        Temperature, pressure and density come from the envelope itself.
        Everything else is evaluated at the envelope's (T, rho) with the
        phase imposed, an explicit evaluation of the equation of state
        without a flash. Recomputing the pressure from (T, rho) instead
        would turn the envelope's convergence tolerance into pressure errors
        of a few tenths of a percent on the liquid side.
        """
        key = get_quantity(key).key
        if key not in self._values:
            out = np.full(len(self), np.nan)
            index = parameter_index(key)
            T_K = self._values["T"]
            for i in range(len(self)):
                phase = CoolProp.iphase_liquid if self.Q[i] < 0.5 else CoolProp.iphase_gas   # flag Q = 0: bubble side
                try:
                    self._work.specify_phase(phase)
                    self._work.update(CoolProp.DmolarT_INPUTS, self._rhomolar[i], T_K[i])
                    out[i] = self._work.keyed_output(index)
                except Exception:
                    pass
            self._values[key] = _read_only(out)
        return self._values[key]


def _read_only(values) -> np.ndarray:
    arr = np.array(values, dtype=float)
    arr.flags.writeable = False
    return arr


def _critical_values(state: AbstractState):
    """(T, p, rhomolar) of the critical point: CoolProp's values, or the
    stable point of highest temperature from all_critical_points for a
    mixture; NaN where nothing is known."""
    T_crit_K = p_crit_Pa = rho_crit_mol = np.nan
    try:
        T_crit_K = state.T_critical()
        p_crit_Pa = state.p_critical()
        rho_crit_mol = state.rhomolar_critical()
    except Exception:
        try:
            for point in state.all_critical_points():
                if point.stable and not (point.T <= T_crit_K):
                    T_crit_K, p_crit_Pa, rho_crit_mol = point.T, point.p, point.rhomolar
        except Exception:
            pass
    return T_crit_K, p_crit_Pa, rho_crit_mol


def _critical_point(fluid: Fluid) -> dict:
    """Find the critical point, falling back to all_critical_points for mixtures."""
    T_crit_K, p_crit_Pa, rho_crit_mol = _critical_values(fluid.state)
    if not np.isfinite(T_crit_K):
        raise ValueError("CoolProp could not provide the critical point of {0}.".format(fluid.name))

    # Evaluate the remaining properties at the critical point on a separate
    # state, so the working state of the fluid is left alone.
    crit_state = build_state(fluid.model_key)
    errors = []
    attempts = []
    if np.isfinite(rho_crit_mol):
        attempts.append((CoolProp.DmolarT_INPUTS, rho_crit_mol, T_crit_K))
    if np.isfinite(p_crit_Pa):
        attempts.append((CoolProp.PT_INPUTS, p_crit_Pa, T_crit_K))
    for pair, v1, v2 in attempts:
        for impose_phase in (True, False):
            try:
                if impose_phase:
                    crit_state.specify_phase(CoolProp.iphase_critical_point)
                else:
                    crit_state.unspecify_phase()
                crit_state.update(pair, v1, v2)
                return {k: crit_state.keyed_output(parameter_index(k))
                        for k in ("T", "p", "h", "s", "rho", "u")}
            except Exception as e:
                errors.append(str(e))
    # The temperature and pressure are known even if no full state could be
    # built. Keep what is certain and mark the rest as unknown.
    if np.isfinite(p_crit_Pa):
        return {"T": T_crit_K, "p": p_crit_Pa, "h": np.nan, "s": np.nan,
                "rho": np.nan, "u": np.nan}
    raise ValueError("Could not evaluate the critical point of {0}: {1}".format(fluid.name, " | ".join(errors)))


# CoolProp's own cache of tabular data ----------------------------------------
# CoolPlot keeps traced lines on disk the way CoolProp keeps its TTSE and
# BICUBIC tables (src/Backends/Tabular/TabularBackends.cpp): next to them in
# the user's ~/.CoolProp folder, and under the same size limit.

# Settings that say where CoolProp keeps files or how much room they get,
# not how it computes; they stay out of the digest, so following the advice
# to raise the size limit does not invalidate every stored line
_CONFIG_NOT_DIGESTED = ("ALTERNATIVE_TABLES_DIRECTORY", "ALTERNATIVE_SVDTABLES_DIRECTORY",
                        "MAXIMUM_TABLE_DIRECTORY_SIZE_IN_GB", "SAVE_RAW_TABLES")


def config_digest() -> str:
    """A digest of CoolProp's global configuration, the same text in every process.

    Python's ``hash()`` of a string is salted per process; this digest keys
    lines kept on disk between runs. Settings that only place or limit
    CoolProp's table files are left out.
    """
    try:
        text = CP.get_config_as_json_string()
    except Exception:
        return ""
    try:
        config = json.loads(text)
        for key in _CONFIG_NOT_DIGESTED:
            config.pop(key, None)
        text = json.dumps(config, sort_keys=True)
    except (ValueError, AttributeError):
        pass
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def coolprop_revision() -> str:
    """CoolProp's version and git revision: development builds all report the same version."""
    return "{0}+{1}".format(getattr(CoolProp, "__version__", ""), getattr(CoolProp, "__gitrevision__", ""))


def _config(getter, name: str):
    """A CoolProp configuration value. CoolProp 8 takes the key as an enum
    member (CP.ALTERNATIVE_TABLES_DIRECTORY), older bindings as its name."""
    key = getattr(CP, name, None)
    if key is not None:
        return getter(key)
    return getter(name)


def coolprop_home_dir() -> str:
    """The folder CoolProp keeps its tables in, ~/.CoolProp, as CoolProp finds the home folder."""
    try:
        home = _config(CP.get_config_string, "ALTERNATIVE_TABLES_DIRECTORY")
    except (TypeError, ValueError, RuntimeError, AttributeError):   # a binding without the key
        home = ""
    if home:
        # The tables were moved; CoolPlot's folder moves with them
        return os.path.abspath(home)
    return os.path.join(os.path.expanduser("~"), ".CoolProp")


def coolprop_table_limit_GB() -> float:
    """CoolProp's MAXIMUM_TABLE_DIRECTORY_SIZE_IN_GB (1 GB unless changed)."""
    try:
        value = float(_config(CP.get_config_double, "MAXIMUM_TABLE_DIRECTORY_SIZE_IN_GB"))
    except (TypeError, ValueError, RuntimeError, AttributeError):   # a binding without the key
        return 1.0
    return value if value > 0.0 else 1.0
