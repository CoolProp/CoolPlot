# -*- coding: utf-8 -*-
"""Psychrometric charts: humid air at one total pressure.

:class:`PsychrometricChart` is the facade for psychrometric charts, as
:class:`coolplot.PropertyDiagram` is for property diagrams. It holds a
:class:`coolplot.spec.psychro.PsychroSpec`, computes the lines with
:mod:`coolplot.thermo.humid_air` (each line once, kept in a cache) and
hands the composed scene to any renderer. Values passed in are in the
chart's units (deg C, g/kg, % and kJ/kg with ``units="EUR"``).

Example
-------
>>> chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))
>>> chart.set_default_lines()
>>> chart.add_process("Cooling", [{"T": 30, "RH": 50}, {"T": 14, "RH": 95}, {"T": 22, "W": 9.5}])
>>> chart.savefig("psychro.png")
"""
from __future__ import annotations

import warnings
from typing import Sequence

from .compose.psychro import compose_psychro
from .engine.cache import CurveCache
from .scene import Scene
from .spec.psychro import LINE_KEYS, STATE_KEYS, AirProcessSpec, PsychroLines, PsychroSpec, psychro_units
from .spec.settings import get_settings
from .style.theme import get_theme
from .style.values import LineStyle, MarkerStyle
from .thermo.humid_air import AirState, air_state, chart_ranges, default_values, psychro_line


class PsychrometricChart:
    """A psychrometric chart: dry-bulb temperature over humidity ratio

    Parameters
    ----------
    p : float
        Total pressure in the chart's pressure unit (bar for "EUR", Pa
        for "SI"); default sea level.
    T_range, W_range : (min, max)
        Visible dry-bulb temperatures and humidity ratios, in the chart's
        units.
    units : str
        "EUR" (deg C, g/kg, %, kJ/kg) or "SI".
    theme, settings : optional
        As for :class:`coolplot.PropertyDiagram`.
    points : int
        Points per line.
    """

    def __init__(self, p: float = None, T_range=(-10.0, 50.0), W_range=(0.0, 30.0), units: str = "EUR",
                 theme=None, settings=None, points: int = 100):
        units_table = psychro_units(units)
        settings = get_settings(settings)
        if theme is not None:
            settings = settings.with_(look=theme)
        p_Pa = 101325.0 if p is None else float(units_table["p"].to_SI(p))
        self.spec = PsychroSpec(p_Pa=p_Pa, T_range_K=tuple(units_table["T"].to_SI(T_range).tolist()),
                                W_range=tuple(units_table["W"].to_SI(W_range).tolist()), units=units,
                                settings=settings, points=points)
        self.cache = CurveCache()
        self.scene = Scene()
        self._plot_size_pt = None
        self._default_renderer = None
        self._warned = set()

    @classmethod
    def from_spec(cls, spec: PsychroSpec) -> "PsychrometricChart":
        """A chart for a saved spec, e.g. PsychroSpec.from_dict(json.load(f))."""
        chart = cls()
        chart.spec = spec
        return chart

    @property
    def points(self) -> int:
        return self.spec.points

    @points.setter
    def points(self, value):
        self.spec = self.spec.with_(points=int(value))
    # Settings ---------------------------------------------------------------
    @property
    def units(self) -> dict:
        return psychro_units(self.spec.units)

    @property
    def title(self) -> str:
        return self.spec.title

    @title.setter
    def title(self, value):
        self.spec = self.spec.with_(title=str(value))

    @property
    def theme(self):
        return self.spec.settings.look

    @theme.setter
    def theme(self, value):
        self.spec = self.spec.with_(settings=self.spec.settings.with_(look=get_theme(value)))

    @property
    def settings(self):
        return self.spec.settings

    @settings.setter
    def settings(self, value):
        self.spec = self.spec.with_(settings=get_settings(value))

    # Content ----------------------------------------------------------------
    def set_lines(self, key: str, values: Sequence[float] = None, labels: bool = True):
        """Lines of constant "RH", "Twb", "h" or "v"; values in the chart's
        units (RH in %), or round values over the chart if None."""
        if key not in LINE_KEYS:
            raise ValueError("Unknown line family '{0}', expected one of {1}.".format(key, LINE_KEYS))
        values_SI = () if values is None else tuple(float(v) for v in self.units[key].to_SI(values).ravel())
        self.spec = self.spec.with_lines(PsychroLines(key, values_SI, labels))

    def set_default_lines(self, labels: bool = True):
        """Relative humidity every 10 %, wet-bulb temperature every 5 K,
        enthalpy every 10 kJ/kg and specific volume every 0.02 m3/kg."""
        for key in LINE_KEYS:
            self.set_lines(key, labels=labels)

    def remove_lines(self, key: str):
        self.spec = self.spec.without_lines(key)

    def set_view(self, x_limits=None, y_limits=None):
        """Show only a window of the chart, in the chart's units (None: all).

        The lines are computed over the full temperature range once, so
        zooming and panning (see :class:`coolplot.interaction.Interaction`)
        only lay out the labels again; outside that range there are no lines.
        """
        units = self.units
        self.spec = self.spec.with_(
            view_T_K=None if x_limits is None else tuple(units["T"].to_SI(x_limits).tolist()),
            view_W=None if y_limits is None else tuple(units["W"].to_SI(y_limits).tolist()))

    def add_process(self, name: str, states: Sequence[dict], closed: bool = False, numbers: bool = True,
                    line_style: LineStyle = None, marker_style: MarkerStyle = None):
        """Air states joined by straight lines, each given by two properties
        in the chart's units, e.g. {"T": 30, "RH": 50} or {"T": 14, "W": 9}.
        Raises ValueError right away if a state cannot be computed."""
        given = [self._given(state, "Process '{0}'".format(name)) for state in states]
        process = AirProcessSpec(str(name), tuple(given), closed, numbers, line_style, marker_style)
        self._states(process)   # compute now, so that errors show up here
        self.spec = self.spec.with_process(process)
        return process.name

    def _given(self, state, where: str):
        """A state in SI units as ((key, value), (key, value))."""
        if isinstance(state, AirState):
            if abs(state.p - self.spec.p_Pa) > 1e-6 * self.spec.p_Pa:
                raise ValueError("{0}: the state is at {1} Pa, the chart at {2} Pa.".format(
                    where, state.p, self.spec.p_Pa))
            return (("T", state.T), ("W", state.W))
        unknown = [k for k in dict(state) if k not in STATE_KEYS]
        if unknown:
            raise ValueError("{0}: unknown properties {1}, expected two of {2}.".format(where, unknown, STATE_KEYS))
        return tuple((k, float(self.units[k].to_SI(v))) for k, v in dict(state).items())

    def move_process_state(self, name: str, number: int, x: float, y: float):
        """Put state ``number`` (from 1) of a process at (T, W) in the chart's
        units; what dragging a state marker does. Raises ValueError, and
        leaves the process unchanged, if there is no air state there."""
        process = next((p for p in self.spec.processes if p.name == name), None)
        if process is None:
            raise KeyError("No process named {0!r}.".format(name))
        if isinstance(number, bool) or int(number) != number or not 1 <= number <= len(process.states):
            raise KeyError("Process {0!r} has no state {1!r}.".format(name, number))
        moved = self._given({"T": x, "W": y}, "Process '{0}'".format(name))
        states = tuple(moved if n == int(number) else given for n, given in enumerate(process.states, start=1))
        new = AirProcessSpec(process.name, states, process.closed, process.numbers, process.line_style,
                             process.marker_style)
        self._states(new)   # raises if it cannot be computed; spec unchanged
        self.spec = self.spec.with_process(new)

    def remove_process(self, name: str):
        self.spec = self.spec.without_process(name)

    def process_states(self, name: str):
        """The AirStates of a process, in SI units."""
        process = next((p for p in self.spec.processes if p.name == name), None)
        if process is None:
            raise KeyError("No process named {0!r}.".format(name))
        return self._states(process)

    def _states(self, process: AirProcessSpec):
        out = []
        for number, given in enumerate(process.states, start=1):
            (k1, v1), (k2, v2) = given
            try:
                out.append(air_state(k1, v1, k2, v2, self.spec.p_Pa))
            except Exception as e:
                raise ValueError("State {0} of process '{1}' could not be computed: {2}".format(
                    number, process.name, e)) from e
        return out

    def state_at(self, x: float, y: float) -> AirState:
        """The air state at a point in the chart's units, e.g. under the mouse."""
        return air_state("T", float(self.units["T"].to_SI(x)), "W", float(self.units["W"].to_SI(y)), self.spec.p_Pa)

    # Scene ------------------------------------------------------------------
    def _curves(self):
        spec = self.spec
        ranges = None
        out = []
        for family in spec.lines:
            values = family.values_SI
            if not values:
                ranges = ranges or chart_ranges(spec.p_Pa, spec.T_range_K, spec.W_range)
                values = default_values(family.key, ranges)
            for value in values:
                key = ("humid air", spec.p_Pa, spec.T_range_K, family.key, value, spec.points)
                curve = self.cache.get_or_compute(key, lambda v=value, k=family.key: psychro_line(
                    k, v, spec.p_Pa, spec.T_range_K, spec.points))
                if curve.n_failed > spec.settings.calc.warn_failed_fraction * spec.points and key not in self._warned:
                    self._warned.add(key)
                    warnings.warn("The line {0}={1:.6g} has gaps: HAPropsSI failed for {2} of {3} points.".format(
                        family.key, value, curve.n_failed, spec.points), UserWarning, stacklevel=3)
                out.append((family.key, value, family.labels, curve))
        return out

    def update_scene(self, plot_size_pt=None) -> Scene:
        """Bring :attr:`scene` up to date and return it; see PropertyDiagram.update_scene."""
        if plot_size_pt is not None:
            self._plot_size_pt = tuple(float(v) for v in plot_size_pt)
        processes = [(p, [(s.T, s.W) for s in self._states(p)]) for p in self.spec.processes]
        previous = {item.id: item for item in self.scene if item.role == "isoline_label"}
        items, axes = compose_psychro(self.spec, self._curves(), processes, self._plot_size_pt, previous)
        self.scene.replace_all(items, axes=axes)
        return self.scene

    def draw(self, renderer=None):
        """Synchronise a renderer; creates a MatplotlibRenderer if none is given."""
        if renderer is None:
            renderer = self._default_renderer
            if renderer is None:
                from .render.mpl import MatplotlibRenderer
                renderer = self._default_renderer = MatplotlibRenderer(figsize=self.spec.settings.page.size_in)
        renderer.sync(self.update_scene(renderer.plot_size_pt()))
        size = renderer.plot_size_pt()
        if size is not None and self._plot_size_pt is not None and any(
                abs(a - b) > 0.02 * b for a, b in zip(size, self._plot_size_pt)):
            renderer.sync(self.update_scene(size))
        return renderer

    def show(self):
        self.draw().show()

    def savefig(self, path, **kwargs):
        self.draw().save(path, **kwargs)
