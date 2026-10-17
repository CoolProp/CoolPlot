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
>>> chart.add_cycle("Cooling", [{"T": 30, "RH": 50}, {"T": 14, "RH": 95}, {"T": 22, "W": 9.5}], closed=False)
>>> chart.save("psychro.png")
"""
from __future__ import annotations

from .chart import Chart
from .core.diagram_type import DiagramType
from .core.errors import deprecated
from .core.limits import Region
from .core.units import get_unit_system
from .engine import CurveCache, Engine
from .spec import DiagramSpec, HumidAirSpec, get_settings
from .core.limits import within


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
        "engineering" (deg C, g/kg, %, kJ/kg), "SI", "IP" or a custom
        UnitSystem.
    theme, settings : optional
        As for :class:`coolplot.PropertyDiagram`.
    points : int, optional
        Points per line; default from ``settings.calc``.
    engine, cache, background, on_ready, workers
        See :class:`coolplot.Chart`.
    """

    kind = "humid_air"

    def __init__(self, p: float = None, T_range=(-10.0, 50.0), W_range=(0.0, 30.0), units="engineering",
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
                                 "(deg C with units='engineering', K with 'SI').".format(
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

    # Old names (0.4 and before); they warn and will go in 1.0 ---------------
    # An air process is a cycle: add_cycle(name, states, closed=False) draws
    # heating, cooling and reheating as an open chain of straight lines.
    @deprecated("use add_cycle(name, states, closed=False)")
    def add_process(self, name, states, closed=False, numbers=True, line_style=None, marker_style=None):
        return self.add_cycle(name, states, numbers=numbers, line_style=line_style, marker_style=marker_style,
                              steps=1, closed=closed)

    @deprecated("use move_cycle_state")
    def move_process_state(self, name, number, x, y):
        self.move_cycle_state(name, number, x, y)

    @deprecated("use remove_cycle")
    def remove_process(self, name):
        self.remove_cycle(name)

    @deprecated("use cycle_states, which lists the states by number")
    def process_states(self, name):
        return list(self.cycle_states(name).values())
