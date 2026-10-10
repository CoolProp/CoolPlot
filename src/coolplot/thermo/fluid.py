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

from functools import lru_cache
from typing import Optional, Tuple

import numpy as np

import CoolProp
from CoolProp import AbstractState
from CoolProp import CoolProp as CP

from ..core.quantities import get_quantity


@lru_cache(maxsize=None)
def parameter_index(key: str) -> int:
    """CoolProp parameter index for a CoolPlot quantity key, e.g. "p" -> iP."""
    return CP.get_parameter_index(get_quantity(key).coolprop_name)


#: Binary interaction parameters copied when a state is snapshotted.
INTERACTION_KEYS = ("betaT", "gammaT", "betaV", "gammaV", "Fij", "kij")


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
        self._model = model
        self._state = build_state(model)
        self._critical = None
        self._envelope = None
        self._guided = False   # phase envelope built on the working state, see update()
        self._name = name

    def __repr__(self):
        return "Fluid({0!r})".format(self._name)

    # Identity --------------------------------------------------------------
    @property
    def name(self) -> str:
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
        twin._critical = None
        twin._envelope = None
        twin._guided = False
        twin._name = "{0}::{1}".format(backend, "&".join(self._model[1]))
        return twin

    def clone(self) -> "Fluid":
        """An independent Fluid with the same model, for example for a worker thread."""
        twin = Fluid.__new__(Fluid)
        twin._model = self._model
        twin._state = build_state(self._model)
        twin._critical = self._critical
        twin._envelope = self._envelope   # read-only arrays, safe to share
        twin._guided = False
        twin._name = self._name
        return twin

    # Property evaluation ---------------------------------------------------
    def update(self, key1: str, value1_SI: float, key2: str, value2_SI: float) -> AbstractState:
        """Set the working state from two quantities given by CoolPlot keys.

        For a mixture, a saturation state (vapour quality as one input)
        that CoolProp cannot find is tried once more after building the
        phase envelope on the working state: CoolProp's mixture saturation
        solvers take their starting values from it. That rescues most
        condenser and evaporator states of blends, for example the dew
        point of R32/R125 (70/30) at 26.6 bar.
        """
        pair, v1, v2 = CP.generate_update_pair(parameter_index(key1), value1_SI,
                                               parameter_index(key2), value2_SI)
        try:
            self._state.update(pair, v1, v2)
        except Exception:
            if self.is_pure or "Q" not in (get_quantity(key1).key, get_quantity(key2).key) or self._guided:
                raise
            self._guided = True
            try:
                self._state.build_phase_envelope("veryfine")
            except Exception:
                pass   # the retry below raises the solver's own error
            self._state.update(pair, v1, v2)
        return self._state

    def get(self, key: str) -> float:
        """Read one quantity of the working state in SI units."""
        return self._state.keyed_output(parameter_index(key))

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

    @property
    def T_triple_K(self) -> Optional[float]:
        return self._trivial(CoolProp.iT_triple)

    @property
    def T_min_K(self) -> Optional[float]:
        return self._trivial(CoolProp.iT_min)

    @property
    def T_max_K(self) -> Optional[float]:
        return self._trivial(CoolProp.iT_max)

    @property
    def p_min_Pa(self) -> Optional[float]:
        return self._trivial(CoolProp.iP_min)

    @property
    def p_max_Pa(self) -> Optional[float]:
        return self._trivial(CoolProp.iP_max)

    @property
    def is_pure(self) -> bool:
        return len(self._model[1]) == 1

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
    """

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
        if not (np.any(self.Q == 0.0) and np.any(self.Q == 1.0)):
            raise ValueError("The phase envelope of {0} has no bubble or no dew line.".format(fluid.name))

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
                phase = CoolProp.iphase_liquid if self.Q[i] == 0.0 else CoolProp.iphase_gas
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


def _critical_point(fluid: Fluid) -> dict:
    """Find the critical point, falling back to all_critical_points for mixtures."""
    state = fluid.state
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
