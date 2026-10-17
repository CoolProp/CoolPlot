# -*- coding: utf-8 -*-
"""Psychrometric charts: humid air at one total pressure.

:class:`PsychrometricChart` is a :class:`coolplot.Chart` made for humid
air: the constructor takes the total pressure and the visible ranges of
dry-bulb temperature and humidity ratio. The lines (relative humidity,
wet-bulb temperature, enthalpy, specific volume) are computed with
:mod:`coolplot.thermo.humid_air`, and air processes are cycles whose
paths are drawn straight. Values passed in are in the chart's units
(deg C, g/kg, % and kJ/kg with ``units="EUR"``).

Example
-------
>>> chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))
>>> chart.set_default_lines()
>>> chart.add_process("Cooling", [{"T": 30, "RH": 50}, {"T": 14, "RH": 95}, {"T": 22, "W": 9.5}])
>>> chart.savefig("psychro.png")
"""
from __future__ import annotations

from typing import Sequence

from .chart import Chart
from .core.diagram_type import DiagramType
from .core.limits import Region
from .core.state import StatePoint
from .core.units import get_unit_system
from .engine import CurveCache, Engine
from .spec import DiagramSpec, HumidAirSpec, get_settings
from .spec.fluid import within
from .style.values import LineStyle, MarkerStyle


class PsychrometricChart(Chart):
    """A psychrometric chart: humidity ratio over dry-bulb temperature

    Parameters
    ----------
    p : float
        Total pressure in the chart's pressure unit (bar for "EUR", Pa
        for "SI"); default sea level.
    T_range, W_range : (min, max)
        Visible dry-bulb temperatures and humidity ratios, in the chart's
        units. Lines are computed over the whole temperature range once;
        zooming needs no new calculations.
    units : str or UnitSystem
        "EUR" (deg C, g/kg, %, kJ/kg), "SI" or a custom UnitSystem.
    theme, settings : optional
        As for :class:`coolplot.PropertyDiagram`.
    points : int, optional
        Points per line; default from ``settings.calc``.
    engine, cache, background, on_ready, workers
        See :class:`coolplot.Chart`.
    """

    def __init__(self, p: float = None, T_range=(-10.0, 50.0), W_range=(0.0, 30.0), units="EUR",
                 theme=None, settings=None, points: int = None, engine: Engine = None, cache: CurveCache = None,
                 background: str = None, on_ready=None, workers: int = None):
        units = get_unit_system(units)
        settings = get_settings(settings)
        if theme is not None:
            settings = settings.with_(look=theme)
        if points is not None:
            settings = settings.with_(calc={"points": int(points)})
        p_Pa = 101325.0 if p is None else float(units["p"].to_SI(p))
        T_range_K = tuple(units["T"].to_SI(T_range).tolist())
        for T_K in T_range_K:
            if not within(T_K, HumidAirSpec.T_LIMITS_K):
                raise ValueError("Temperatures have to lie between {0} and {1} K for HAPropsSI, got {2} K "
                                 "(deg C with units='EUR', K with 'SI').".format(
                                     HumidAirSpec.T_LIMITS_K[0], HumidAirSpec.T_LIMITS_K[1], T_range_K))
        W_range = tuple(units["W"].to_SI(W_range).tolist())
        if min(W_range) < 0.0:
            raise ValueError("Humidity ratios have to be at least 0, got {0}.".format(W_range))
        spec = DiagramSpec(fluid=HumidAirSpec(p_Pa), diagram=DiagramType.parse("WT"), units=units,
                           limits=Region((("T", T_range_K), ("W", W_range))), settings=settings)
        Chart.__init__(self, spec, engine, cache, background, on_ready, workers)

    @property
    def p_Pa(self) -> float:
        """The total pressure in Pa."""
        return self.spec.fluid.p_Pa

    @property
    def points(self) -> int:
        """Points per line, from ``settings.calc``."""
        return self.spec.settings.calc.points

    @points.setter
    def points(self, value):
        self.settings = self.spec.settings.with_(calc={"points": int(value)})

    # Lines ------------------------------------------------------------------
    def set_lines(self, key: str, values: Sequence[float] = None, labels: bool = True, num: int = None,
                  points: int = None):
        """Lines of constant "RH", "Twb", "h" or "v"; values in the chart's
        units (RH in %), or about ``num`` round values over the chart if
        None. The same as :meth:`Chart.set_isolines` with rounding and
        labels on."""
        return self.set_isolines(key, values, num=num, rounding=True, points=points, labels=labels)

    def set_default_lines(self, labels: bool = True):
        """Relative humidity every 10 %, and round values of wet-bulb
        temperature, enthalpy and specific volume (usually every 5 K,
        10 kJ/kg and 0.02 m3/kg)."""
        for key in self.spec.diagram.supported_isolines():
            self.set_lines(key, labels=labels)

    def remove_lines(self, key: str):
        self.remove_isolines(key)

    # Air processes: cycles with straight paths ------------------------------
    def add_process(self, name: str, states: Sequence, closed: bool = False, numbers: bool = True,
                    line_style: LineStyle = None, marker_style: MarkerStyle = None):
        """Air states joined by straight lines, each given by two properties
        in the chart's units, e.g. {"T": 30, "RH": 50} or {"T": 14, "W": 9},
        or as a StatePoint of humid air at the chart's pressure. ``closed``
        joins the last state to the first. Raises ValueError right away if
        a state cannot be computed. The process is a cycle: see
        :meth:`Chart.add_cycle`, :meth:`Chart.move_cycle_state` and
        :meth:`Chart.cycle_states`."""
        states = list(states)
        for number, state in enumerate(states, start=1):
            if isinstance(state, StatePoint) and abs(state.p - self.p_Pa) > 1e-6 * self.p_Pa:
                raise ValueError("Process '{0}', state {1}: the state is at {2} Pa, the chart at {3} Pa.".format(
                    name, number, state.p, self.p_Pa))
        numbers_in_order = list(range(1, len(states) + 1))
        loops = [numbers_in_order + ([1] if closed else [])] if len(states) > 1 else []
        return self.add_cycle(name, states, loops=loops, numbers=numbers, line_style=line_style,
                              marker_style=marker_style, steps=1)

    def move_process_state(self, name: str, number: int, x: float, y: float):
        """Put state ``number`` (from 1) of a process at (T, W) in the chart's
        units; the same as :meth:`Chart.move_cycle_state`."""
        self.move_cycle_state(name, number, x, y)

    def remove_process(self, name: str):
        self.remove_cycle(name)

    def process_states(self, name: str):
        """The states of a process in SI units, in order."""
        return list(self.cycle_states(name).values())
