# -*- coding: utf-8 -*-
"""Psychrometric charts: humid air at one total pressure.

:class:`PsychrometricChart` is a :class:`coolplot.Chart` made for humid
air: the constructor takes the total pressure and the visible ranges of
dry-bulb temperature and humidity ratio. The lines (relative humidity,
wet-bulb temperature, enthalpy, specific volume) are computed with
:mod:`coolplot.thermo.humid_air`, and air processes are cycles whose
paths are drawn straight. Values passed in are in the chart's units
(deg C, g/kg, % and kJ/kg with ``units="engineering"``).

Example
-------
>>> chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))
>>> chart.set_default_lines()
>>> chart.add_cycle("Cooling", [{"T": 30, "RH": 50}, {"T": 14, "RH": 95}, {"T": 22, "W": 9.5}], closed=False)
>>> chart.save("psychro.png")
"""
from __future__ import annotations

import numpy as np

from .chart import REMOVED_NAMES, Chart
from .core.diagram_type import DiagramType
from .core.limits import Region
from .core.units import get_unit_system
from .engine import CurveCache, Engine
from .spec import DiagramSpec, HumidAirSpec, get_settings
from .core.limits import within
from .core.errors import PropertyError
from .core.state import StatePoint
from .style.values import LineStyle, MarkerStyle
from .thermo.humid_air import mixed_air


class PsychrometricChart(Chart):
    """A psychrometric chart: humidity ratio over dry-bulb temperature

    Parameters
    ----------
    p : float
        Total pressure in the chart's pressure unit (bar for "engineering", Pa
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
    _removed_names = dict(REMOVED_NAMES, add_process="use add_cycle(name, states, closed=False)",
                          move_process_state="use move_cycle_state", remove_process="use remove_cycle",
                          process_states="use cycle_states, which lists the states by number")

    def __init__(self, p: float = None, T_range=(-10.0, 50.0), W_range=(0.0, 30.0), units="engineering",
                 theme=None, settings=None, points: int = None, engine: Engine = None, cache: CurveCache = None,
                 background: str = None, on_ready=None, workers: int = None):
        units = get_unit_system(units, stacklevel=3)
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

    def add_zone(self, name: str, T_range, RH_range, label: str = None, line_style: LineStyle = None,
                 units=None, segments: int = 12) -> str:
        """Outline a region of dry-bulb temperature and relative humidity, e.g. a comfort zone.

        ``T_range`` and ``RH_range`` are (min, max) in the chart's units or
        in ``units`` (deg C and % with "engineering"). The outline is a
        closed cycle without markers or state numbers: straight edges at
        the two temperatures, and two edges that follow the lines of
        constant relative humidity, each drawn with ``segments`` straight
        pieces. ``label``, if given, is written at the corner of the
        lowest temperature and highest humidity. Returns the name; the
        zone is removed with :meth:`remove_cycle`.

        >>> chart = PsychrometricChart()
        >>> chart.add_zone("Comfort", T_range=(20, 26), RH_range=(30, 60), label="comfort")
        'Comfort'
        """
        T_lo, T_hi = sorted(float(t) for t in T_range)
        RH_lo, RH_hi = sorted(float(rh) for rh in RH_range)
        if not T_lo < T_hi or not RH_lo < RH_hi:
            raise ValueError("A zone needs two different temperatures and two different humidities, not {0} "
                             "and {1}.".format(tuple(T_range), tuple(RH_range)))
        if int(segments) < 1:
            raise ValueError("segments has to be at least 1, not {0}.".format(segments))
        T_edge = np.linspace(T_lo, T_hi, int(segments) + 1)
        # Along the lower humidity edge to the warm side, back along the upper edge
        states = [{"T": T, "RH": RH_lo} for T in T_edge] + [{"T": T, "RH": RH_hi} for T in T_edge[::-1]]
        labels = {len(states): label} if label else None   # the last state is (T_lo, RH_hi)
        return self.add_cycle(name, states, numbers=False, units=units, line_style=line_style,
                              marker_style=MarkerStyle(size_pt=0.0, face_color="none", edge_color="none"),
                              labels=labels)

    def mix(self, a, b, m_dot_a_kg_s: float = 1.0, m_dot_b_kg_s: float = 1.0, units=None) -> StatePoint:
        """The state (SI units) after two streams of air mix adiabatically.

        ``a`` and ``b`` are StatePoints or dicts of two properties in the
        chart's units (or in ``units``), e.g. ``{"T": 32, "RH": 40}``.
        ``m_dot_a_kg_s`` and ``m_dot_b_kg_s`` are their mass flows of dry
        air; only the ratio matters. The mixed state lies on the straight
        line between the two states, closer to the larger stream; it can
        be given to :meth:`add_cycle` as it is.

        >>> chart = PsychrometricChart()
        >>> mixed = chart.mix({"T": 32, "RH": 40}, {"T": 24, "RH": 50}, m_dot_a_kg_s=0.3, m_dot_b_kg_s=0.7)
        >>> round(mixed.T - 273.15, 1)
        26.4
        """
        try:
            return mixed_air(self.state(a, units), self.state(b, units), m_dot_a_kg_s, m_dot_b_kg_s)
        except PropertyError as e:
            raise self._in_units(e) from None
