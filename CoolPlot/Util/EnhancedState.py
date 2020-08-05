# -*- coding: utf-8 -*-
from __future__ import print_function, division
from enum import Enum
from typing import Union

import numpy as np

from . import is_string

import CoolProp
from CoolProp import CoolProp as CP


def get_critical_state(state: CoolProp.AbstractState) -> CoolProp.AbstractState:
    """Create a new state instance and update it with the critical point data

    Parameters
    ----------
        state : CoolProp.AbstractState

    Returns
    -------
        CoolProp.AbstractState
    """
    crit_state = CP.PyCriticalState()
    crit_state.T = np.nan
    crit_state.p = np.nan
    crit_state.rhomolar = np.nan
    crit_state.stable = False
    try:
        crit_state.T = state.T_critical()
        crit_state.p = state.p_critical()
        crit_state.rhomolar = state.rhomolar_critical()
        crit_state.stable = True
    except:
        try:
            for crit_state_tmp in state.all_critical_points():
                if crit_state_tmp.stable and (crit_state_tmp.T > crit_state.T or not np.isfinite(crit_state.T)):
                    crit_state.T = crit_state_tmp.T
                    crit_state.p = crit_state_tmp.p
                    crit_state.rhomolar = crit_state_tmp.rhomolar
                    crit_state.stable = crit_state_tmp.stable
        except:
            raise ValueError("Could not calculate the critical point data.")
    new_state = CoolProp.AbstractState(state.backend_name(), '&'.join(state.fluid_names()))
    masses = state.get_mass_fractions()
    if len(masses) > 1:
        new_state.set_mass_fractions(masses)
        # Uses mass fraction to work with incompressible fluids
        # try: new_state.build_phase_envelope("dummy")
        # except: pass
    # TODO: Remove this hack ASAP
    # Avoid problems with https://github.com/CoolProp/CoolProp/issues/1962
    BE = state.backend_name()
    FL = '&'.join(state.fluid_names())
    if BE == "HelmholtzEOSBackend" and FL == "Ammonia":
        crit_state.T *= 1.001
    msg = ""
    if np.isfinite(crit_state.rhomolar) and np.isfinite(crit_state.T):
        try:
            new_state.specify_phase(CoolProp.iphase_critical_point)
            new_state.update(CoolProp.DmolarT_INPUTS, crit_state.rhomolar, crit_state.T)
            return new_state
        except Exception as e:
            msg += str(e) + " - "
            pass
        try:
            new_state.update(CoolProp.DmolarT_INPUTS, crit_state.rhomolar, crit_state.T)
            return new_state
        except Exception as e:
            msg += str(e) + " - "
            pass
    if np.isfinite(crit_state.p) and np.isfinite(crit_state.T):
        try:
            new_state.specify_phase(CoolProp.iphase_critical_point)
            new_state.update(CoolProp.PT_INPUTS, crit_state.p, crit_state.T)
            return new_state
        except Exception as e:
            msg += str(e) + " - "
            pass
        try:
            new_state.update(CoolProp.PT_INPUTS, crit_state.p, crit_state.T)
            return new_state
        except Exception as e:
            msg += str(e) + " - "
            pass
    raise ValueError("Could not calculate the critical point data. " + msg)


class EnhancedState(CoolProp.AbstractState):

    def __init__(self, backend: str, fluid: str):
        CoolProp.AbstractState.__init__(backend, fluid)
        self._critical_state = None
        self._T_critical = None
        self._rhomass_critical = None
        self._rhomolar_critical = None
        self._p_critical = None
        self._smass_critical = None
        self._hmass_critical = None
        self._small = 1e-7

    @classmethod
    def from_abstract_state(cls, state: CoolProp.AbstractState):
        new_state = cls(state.backend_name(), '&'.join(state.fluid_names()))
        # Uses mass fraction to work with incompressible fluids
        masses = state.get_mass_fractions()
        if len(masses) > 1:
            new_state.set_mass_fractions(masses)
        try:
            rho = state.rhomolar()
            T = state.T()
            new_state.update(CoolProp.DmolarT_INPUTS, rho, T)
        except:
            pass
        return new_state

    @property
    def critical_state(self):
        if self._critical_state is None:
            tmp = CoolProp.AbstractState(self.backend_name(), '&'.join(self.fluid_names()))
            self._critical_state = get_critical_state(tmp)
        return self._critical_state

    #@property
    def T_critical(self):
        if self._T_critical is None:
            self._T_critical = self.critical_state.keyed_output(CoolProp.iT)
        return self._T_critical

    #@property
    def rhomass_critical(self):
        if self._rhomass_critical is None:
            self._rhomass_critical = self.critical_state.keyed_output(CoolProp.iDmass)
        return self._rhomass_critical

    #@property
    def rhomolar_critical(self):
        if self._rhomolar_critical is None:
            self._rhomolar_critical = self.critical_state.keyed_output(CoolProp.iDmolar)
        return self._rhomolar_critical

    #@property
    def rho_critical(self):
        return self.rhomass_critical()

    #@property
    def p_critical(self):
        if self._p_critical is None:
            self._p_critical = self.critical_state.keyed_output(CoolProp.iP)
        return self._p_critical

    #@property
    def s_critical(self):
        if self._smass_critical is None:
            self._smass_critical = self.critical_state.keyed_output(CoolProp.iSmass)
        return self._smass_critical

    #@property
    def h_critical(self):
        if self._hmass_critical is None:
            self._hmass_critical = self.critical_state.keyed_output(CoolProp.iHmass)
        return self._hmass_critical

    #@property
    #def delta_p_small(self):
    #    return self.p_critical * self._small

    #@property
    #def delta_T_small(self):
    #    return self.T_critical * self._small


class FractionType(Enum):
    MOLE = 1
    MASS = 2
    VOLU = 3


def process_fluid_state(fluid_ref: Union[str, CoolProp.AbstractState, EnhancedState], fraction: FractionType = FractionType.MOLE) -> EnhancedState:
    """Check input for state object or fluid string

    Parameters
    ----------
        fluid_ref : str, CoolProp.AbstractState, EnhancedState
        fractions : FractionType, switch to set mass, volu or mole fractions

    Returns
    -------
        EnhancedState
    """
    if isinstance(fluid_ref, EnhancedState):
        return fluid_ref
    elif isinstance(fluid_ref, CoolProp.AbstractState):
        return EnhancedState.from_abstract_state(fluid_ref)
    elif is_string(fluid_ref):
        backend, fluids = CP.extract_backend(fluid_ref)
        fluids, fractions = CP.extract_fractions(fluids)
        state = EnhancedState(backend, '&'.join(fluids))
        if len(fluids) > 1 and len(fluids) == len(fractions):
            if fraction == FractionType.MOLE: state.set_mole_fractions(fractions)
            elif fraction == FractionType.MASS: state.set_mass_fractions(fractions)
            elif fraction == FractionType.VOLU: state.set_volu_fractions(fractions)
            else: raise ValueError("Unknown composition type received.")
        return state
    raise TypeError("Invalid fluid_ref input, expected a string or an AbstractState instance.")
