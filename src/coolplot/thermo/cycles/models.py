# -*- coding: utf-8 -*-
"""Simple cycle models that return a :class:`coolplot.core.cycle.Cycle`.

These are meant for drawing typical cycles on a diagram and for quick
estimates, not for equipment design: pressure drops and heat losses are
neglected, and compression and expansion use a constant isentropic
efficiency.

Conventions
-----------
* Temperatures are given in deg C (``_C``) and temperature differences in
  K (``_K``), as engineers state them; everything in the returned Cycle is
  in SI units.
* For refrigerant blends, the evaporating and the condensing temperature
  are dew point temperatures (as in EN 12900): the evaporating pressure is
  the dew pressure at ``T_evap_C``, the condensing pressure the dew
  pressure at ``T_cond_C``. Superheat is counted from the dew point,
  subcooling from the bubble point.
* Specific results are per kg of refrigerant through the evaporator,
  named ``q_..._J_kg`` for heat and ``w_..._J_kg`` for work.
"""
from __future__ import annotations

import math

from ...core.cycle import Cycle
from ...core.errors import check_old_keyword
from ..fluid import Fluid
from ..process import state_point

C_TO_K = 273.15


def _fluid(fluid) -> Fluid:
    return fluid if isinstance(fluid, Fluid) else Fluid(fluid)


def _compress(fluid, start, p_out_Pa, eta_is):
    """Outlet of a compressor (or pump) with an isentropic efficiency."""
    h_s = state_point(fluid, "p", p_out_Pa, "s", start.s).h
    return state_point(fluid, "p", p_out_Pa, "h", start.h + (h_s - start.h) / eta_is)


def _expand(fluid, start, p_out_Pa, eta_is):
    """Outlet of a turbine with an isentropic efficiency."""
    h_s = state_point(fluid, "p", p_out_Pa, "s", start.s).h
    return state_point(fluid, "p", p_out_Pa, "h", start.h - eta_is * (start.h - h_s))


def _vapour_out(fluid, p_Pa, dT_sh_K):
    """Saturated or superheated vapour at p, superheat counted from the dew point."""
    if dT_sh_K <= 0.0:
        return state_point(fluid, "p", p_Pa, "Q", 1.0)
    T_dew_K = state_point(fluid, "p", p_Pa, "Q", 1.0).T
    return state_point(fluid, "p", p_Pa, "T", T_dew_K + dT_sh_K)


def _liquid_out(fluid, p_Pa, dT_sc_K):
    """Saturated or subcooled liquid at p, subcooling counted from the bubble point."""
    if dT_sc_K <= 0.0:
        return state_point(fluid, "p", p_Pa, "Q", 0.0)
    T_bubble_K = state_point(fluid, "p", p_Pa, "Q", 0.0).T
    return state_point(fluid, "p", p_Pa, "T", T_bubble_K - dT_sc_K)


def _one_of(new, old, default, name):
    """The value given under the new or the old keyword name, or the default."""
    if new is not None and old is not None:
        raise TypeError("Give {0} once, not under its old name as well.".format(name))
    return default if new is None and old is None else (new if new is not None else old)


def _check_lift(T_evap_C, T_cond_C):
    if not T_cond_C > T_evap_C:
        raise ValueError("The condensing temperature ({0} deg C) has to be above the evaporating "
                         "temperature ({1} deg C).".format(T_cond_C, T_evap_C))


def _check(eta_is, *names_values):
    if not 0.0 < eta_is <= 1.0:
        raise ValueError("eta_is has to be between 0 and 1, not {0}.".format(eta_is))
    for name, value in names_values:
        if value < 0.0:
            raise ValueError("{0} cannot be negative, got {1}.".format(name, value))


def simple_compression(fluid, T_evap_C: float, T_cond_C: float, dT_sh_K: float = 5.0, dT_sc_K: float = 2.0,
                       eta_is: float = 0.7, name: str = "Vapour compression") -> Cycle:
    """Single-stage vapour compression cycle (refrigerator or heat pump)

    States: 1 evaporator outlet = compressor inlet, 2 compressor outlet,
    3 condenser outlet, 4 after the expansion valve.

    Results: ``p_evap_Pa``, ``p_cond_Pa``, ``q_evap_J_kg``, ``q_cond_J_kg``,
    ``w_comp_J_kg``, ``COP_cooling``, ``COP_heating``, ``T_comp_out_K``.
    """
    _check(eta_is, ("dT_sh_K", dT_sh_K), ("dT_sc_K", dT_sc_K))
    _check_lift(T_evap_C, T_cond_C)
    fluid = _fluid(fluid)
    p_evap_Pa = state_point(fluid, "T", T_evap_C + C_TO_K, "Q", 1.0).p
    p_cond_Pa = state_point(fluid, "T", T_cond_C + C_TO_K, "Q", 1.0).p
    s1 = _vapour_out(fluid, p_evap_Pa, dT_sh_K)
    s2 = _compress(fluid, s1, p_cond_Pa, eta_is)
    s3 = _liquid_out(fluid, p_cond_Pa, dT_sc_K)
    s4 = state_point(fluid, "p", p_evap_Pa, "h", s3.h)
    q_evap_J_kg, q_cond_J_kg, w_comp_J_kg = s1.h - s4.h, s2.h - s3.h, s2.h - s1.h
    return Cycle(name, {1: s1, 2: s2, 3: s3, 4: s4}, paths={(1, 2): "polytropic"},
                 results={"p_evap_Pa": p_evap_Pa, "p_cond_Pa": p_cond_Pa, "q_evap_J_kg": q_evap_J_kg,
                          "q_cond_J_kg": q_cond_J_kg, "w_comp_J_kg": w_comp_J_kg,
                          "COP_cooling": q_evap_J_kg / w_comp_J_kg, "COP_heating": q_cond_J_kg / w_comp_J_kg,
                          "T_comp_out_K": s2.T},
                 fluid=fluid.name)


def two_stage(fluid, T_evap_C: float, T_cond_C: float, intermediate: str = "flash_tank", p_mid_Pa: float = None,
              dT_sh_K: float = 5.0, dT_sc_K: float = 2.0, eta_is: float = 0.7, dT_econ_K: float = 5.0,
              name: str = None) -> Cycle:
    """Two-stage vapour compression with a flash tank or an economizer

    The intermediate pressure is the geometric mean of the evaporating and
    condensing pressure unless ``p_mid_Pa`` is given. Both compressors use
    ``eta_is``.

    ``intermediate="flash_tank"`` (an open flash tank that also cools the
    low-stage discharge to saturated vapour):
    1 evaporator outlet, 2 low-stage discharge, 3 high-stage suction
    (saturated vapour), 4 high-stage discharge, 5 condenser outlet, 6 after
    the high-pressure valve, 7 saturated liquid from the flash tank, 8 after
    the low-pressure valve. One split chain 1-2-3-4-5-6-7-8-1; draw it as
    two closed cycles with ``loops=[[1, 2, 7, 8, 1], [3, 4, 5, 6, 3]]``.

    ``intermediate="economizer"`` (vapour injection between the stages):
    1 evaporator outlet, 2 low-stage discharge, 3 high-stage suction after
    mixing with the injected vapour, 4 high-stage discharge, 5 condenser
    outlet, 6 main liquid after the economizer (``dT_econ_K`` above the
    intermediate saturation temperature), 7 after the main valve, 8 after
    the injection valve, 9 injected vapour (saturated). Chains: the main
    cycle 1-2-3-4-5-6-7-1 and the injection branch 5-8-9-3.

    Results: ``p_evap_Pa``, ``p_mid_Pa``, ``p_cond_Pa``, ``m_dot_ratio`` (flow
    in the high stage, or injected, per unit flow through the evaporator),
    ``q_evap_J_kg``, ``q_cond_J_kg``, ``w_comp_J_kg`` (both stages, per kg
    through the evaporator), ``COP_cooling``, ``COP_heating``.
    """
    _check(eta_is, ("dT_sh_K", dT_sh_K), ("dT_sc_K", dT_sc_K), ("dT_econ_K", dT_econ_K))
    _check_lift(T_evap_C, T_cond_C)
    fluid = _fluid(fluid)
    p_evap_Pa = state_point(fluid, "T", T_evap_C + C_TO_K, "Q", 1.0).p
    p_cond_Pa = state_point(fluid, "T", T_cond_C + C_TO_K, "Q", 1.0).p
    if p_mid_Pa is None:
        p_mid_Pa = math.sqrt(p_evap_Pa * p_cond_Pa)
    if not p_evap_Pa < p_mid_Pa < p_cond_Pa:
        raise ValueError("The intermediate pressure has to lie between the evaporating and condensing pressure.")
    s1 = _vapour_out(fluid, p_evap_Pa, dT_sh_K)
    s2 = _compress(fluid, s1, p_mid_Pa, eta_is)
    common = {"p_evap_Pa": p_evap_Pa, "p_mid_Pa": p_mid_Pa, "p_cond_Pa": p_cond_Pa}
    if intermediate == "flash_tank":
        s3 = state_point(fluid, "p", p_mid_Pa, "Q", 1.0)
        s4 = _compress(fluid, s3, p_cond_Pa, eta_is)
        s5 = _liquid_out(fluid, p_cond_Pa, dT_sc_K)
        s6 = state_point(fluid, "p", p_mid_Pa, "h", s5.h)
        s7 = state_point(fluid, "p", p_mid_Pa, "Q", 0.0)
        s8 = state_point(fluid, "p", p_evap_Pa, "h", s7.h)
        # Flash tank energy balance per kg through the evaporator:
        # h2 + m_HP * h6 = m_HP * h3 + h7
        ratio = (s2.h - s7.h) / (s3.h - s6.h)
        states = {1: s1, 2: s2, 3: s3, 4: s4, 5: s5, 6: s6, 7: s7, 8: s8}
        loops = [[1, 2, 3, 4, 5, 6, 7, 8, 1]]
        q_evap_J_kg = s1.h - s8.h
        w_comp_J_kg = (s2.h - s1.h) + ratio * (s4.h - s3.h)
        q_cond_J_kg = ratio * (s4.h - s5.h)
        paths = {(1, 2): "polytropic", (3, 4): "polytropic"}
    elif intermediate == "economizer":
        s5 = _liquid_out(fluid, p_cond_Pa, dT_sc_K)
        T_mid_sat_K = state_point(fluid, "p", p_mid_Pa, "Q", 0.0).T
        s6 = state_point(fluid, "p", p_cond_Pa, "T", min(T_mid_sat_K + dT_econ_K, s5.T))
        s7 = state_point(fluid, "p", p_evap_Pa, "h", s6.h)
        s8 = state_point(fluid, "p", p_mid_Pa, "h", s5.h)
        s9 = state_point(fluid, "p", p_mid_Pa, "Q", 1.0)
        # Economizer energy balance per kg of main flow: ratio * (h9 - h8) = h5 - h6
        ratio = (s5.h - s6.h) / (s9.h - s8.h)
        s3 = state_point(fluid, "p", p_mid_Pa, "h", (s2.h + ratio * s9.h) / (1.0 + ratio))
        s4 = _compress(fluid, s3, p_cond_Pa, eta_is)
        states = {1: s1, 2: s2, 3: s3, 4: s4, 5: s5, 6: s6, 7: s7, 8: s8, 9: s9}
        loops = [[1, 2, 3, 4, 5, 6, 7, 1], [5, 8, 9, 3]]
        q_evap_J_kg = s1.h - s7.h
        w_comp_J_kg = (s2.h - s1.h) + (1.0 + ratio) * (s4.h - s3.h)
        q_cond_J_kg = (1.0 + ratio) * (s4.h - s5.h)
        paths = {(1, 2): "polytropic", (3, 4): "polytropic"}
    else:
        raise ValueError("intermediate has to be 'flash_tank' or 'economizer', not {0!r}.".format(intermediate))
    results = dict(common, m_dot_ratio=ratio, q_evap_J_kg=q_evap_J_kg, q_cond_J_kg=q_cond_J_kg,
                   w_comp_J_kg=w_comp_J_kg, COP_cooling=q_evap_J_kg / w_comp_J_kg,
                   COP_heating=q_cond_J_kg / w_comp_J_kg)
    default_name = "Two-stage, " + ("flash tank" if intermediate == "flash_tank" else "economizer")
    return Cycle(name or default_name, states, loops, paths, results, fluid.name)


def rankine(fluid, p_high_Pa: float, p_low_Pa: float, T_live_C: float = None, eta_is_turbine: float = None,
            eta_is_pump: float = None, name: str = "Rankine", **old_names) -> Cycle:
    """Simple Rankine cycle (steam or organic)

    States: 1 condenser outlet = pump inlet (saturated liquid), 2 pump
    outlet, 3 boiler outlet (live steam at ``T_live_C``, saturated vapour
    if None), 4 turbine outlet. ``eta_is_turbine`` and ``eta_is_pump``
    are isentropic efficiencies, 0.85 and 0.75 by default (``eta_turbine``
    and ``eta_pump`` before 0.5).

    Results: ``q_in_J_kg``, ``q_out_J_kg``, ``w_turbine_J_kg``,
    ``w_pump_J_kg``, ``eta_th`` (net work over heat input).
    """
    eta_turbine = _one_of(eta_is_turbine, check_old_keyword(old_names, "eta_turbine", "eta_is_turbine", "rankine"),
                          0.85, "eta_is_turbine")
    eta_pump = _one_of(eta_is_pump, check_old_keyword(old_names, "eta_pump", "eta_is_pump", "rankine"),
                       0.75, "eta_is_pump")
    if old_names:
        raise TypeError("rankine() got unexpected keyword arguments {0}.".format(sorted(old_names)))
    for label, eta in (("eta_is_turbine", eta_turbine), ("eta_is_pump", eta_pump)):
        if not 0.0 < eta <= 1.0:
            raise ValueError("{0} has to be between 0 and 1, not {1}.".format(label, eta))
    if not p_low_Pa < p_high_Pa:
        raise ValueError("p_high_Pa has to be above p_low_Pa.")
    fluid = _fluid(fluid)
    s1 = state_point(fluid, "p", p_low_Pa, "Q", 0.0)
    s2 = _compress(fluid, s1, p_high_Pa, eta_pump)
    if T_live_C is None:
        s3 = state_point(fluid, "p", p_high_Pa, "Q", 1.0)
    else:
        try:
            T_sat_K = state_point(fluid, "p", p_high_Pa, "Q", 1.0).T
        except Exception:
            T_sat_K = None   # supercritical live steam: no saturation temperature
        if T_sat_K is not None and T_live_C + C_TO_K < T_sat_K:
            raise ValueError("The live steam temperature ({0} deg C) is below the saturation temperature "
                             "({1:.1f} deg C) at p_high_Pa.".format(T_live_C, T_sat_K - C_TO_K))
        s3 = state_point(fluid, "p", p_high_Pa, "T", T_live_C + C_TO_K)
    s4 = _expand(fluid, s3, p_low_Pa, eta_turbine)
    w_turbine_J_kg, w_pump_J_kg = s3.h - s4.h, s2.h - s1.h
    q_in_J_kg, q_out_J_kg = s3.h - s2.h, s4.h - s1.h
    return Cycle(name, {1: s1, 2: s2, 3: s3, 4: s4}, paths={(1, 2): "polytropic", (3, 4): "polytropic"},
                 results={"q_in_J_kg": q_in_J_kg, "q_out_J_kg": q_out_J_kg, "w_turbine_J_kg": w_turbine_J_kg,
                          "w_pump_J_kg": w_pump_J_kg, "eta_th": (w_turbine_J_kg - w_pump_J_kg) / q_in_J_kg},
                 fluid=fluid.name)
