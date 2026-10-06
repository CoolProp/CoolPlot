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
from typing import Optional, Tuple, Union

import numpy as np

import CoolProp
from CoolProp import AbstractState
from CoolProp import CoolProp as CP

from ..quantities import get_quantity


@lru_cache(maxsize=None)
def parameter_index(key: str) -> int:
    """CoolProp parameter index for a CoolPlot quantity key, e.g. "p" -> iP."""
    return CP.get_parameter_index(get_quantity(key).coolprop_name)


def _new_state(backend: str, fluids, mole_fractions) -> AbstractState:
    state = AbstractState(backend, "&".join(fluids))
    if len(fluids) > 1:
        state.set_mole_fractions(list(mole_fractions))
    return state


class Fluid:
    """A fluid model plus cached constants

    Parameters
    ----------
    fluid_ref : str or CoolProp.AbstractState
        Either a CoolProp fluid string like "HEOS::R290" or
        "HEOS::R32[0.5]&R125[0.5]", or an existing AbstractState. An
        existing state is used as is and will be modified by calculations.
    fractions : str
        How fractions in a fluid string are interpreted: "mole", "mass"
        or "volu".
    """

    def __init__(self, fluid_ref: Union[str, AbstractState], fractions: str = "mole"):
        if isinstance(fluid_ref, AbstractState):
            self._state = fluid_ref
        elif isinstance(fluid_ref, str):
            backend, names = CP.extract_backend(fluid_ref)
            names, values = CP.extract_fractions(names)
            self._state = AbstractState(backend, "&".join(names))
            if len(names) > 1 and len(values) == len(names):
                if fractions == "mole":
                    self._state.set_mole_fractions(values)
                elif fractions == "mass":
                    self._state.set_mass_fractions(values)
                elif fractions == "volu":
                    self._state.set_volu_fractions(values)
                else:
                    raise ValueError("Unknown fraction type '{0}'.".format(fractions))
        else:
            raise TypeError("Expected a fluid string or a CoolProp.AbstractState.")
        self._critical = None
        self._name = fluid_ref if isinstance(fluid_ref, str) else "&".join(self._state.fluid_names())

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
        """Hashable description of the fluid model, used as a cache key.

        Two Fluid objects with the same model key give the same properties,
        so cached isolines can be shared between them. Binary interaction
        parameters set after construction are not captured.
        """
        return (self._state.backend_name(),
                tuple(self._state.fluid_names()),
                tuple(np.round(self._state.get_mole_fractions(), 12)))

    def clone(self) -> "Fluid":
        """An independent Fluid with the same model, for example for a worker thread."""
        backend, names, fractions = self.model_key
        twin = Fluid(_new_state(backend, names, fractions))
        twin._name = self._name
        twin._critical = self._critical
        return twin

    # Property evaluation ---------------------------------------------------
    def update(self, key1: str, value1_SI: float, key2: str, value2_SI: float) -> AbstractState:
        """Set the working state from two quantities given by CoolPlot keys."""
        pair, v1, v2 = CP.generate_update_pair(parameter_index(key1), value1_SI,
                                               parameter_index(key2), value2_SI)
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
        return len(self._state.fluid_names()) == 1

    @property
    def critical(self) -> dict:
        """Critical point properties in SI units, computed once and cached.

        Returns a dict with the keys of :data:`CoolPlot.quantities.QUANTITIES`
        except "Q". Raises ValueError if CoolProp cannot provide the point.
        """
        if self._critical is None:
            self._critical = _critical_point(self)
        return self._critical

    def saturation_range(self, key: str) -> Tuple[float, float]:
        """Lowest and highest saturation temperature or pressure in SI units.

        The range starts slightly above the lowest valid temperature of the
        equation of state and ends slightly below the critical point, where
        the saturation solvers are reliable.
        """
        key = get_quantity(key).key
        if key not in ("T", "p"):
            raise ValueError("Saturation ranges are defined in T or p, not in '{0}'.".format(key))
        crit = self.critical
        rel_small = 1e-7
        T_lo_K = max(v for v in (self.T_triple_K, self.T_min_K, 0.0) if v is not None)
        T_lo_K += crit["T"] * rel_small
        if key == "T":
            return T_lo_K, crit["T"] * (1.0 - rel_small)
        self.update("Q", 0.0, "T", T_lo_K)
        return self.get("p") * (1.0 + rel_small), crit["p"] * (1.0 - rel_small)


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
    backend, names, fractions = fluid.model_key
    crit_state = _new_state(backend, names, fractions)
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
