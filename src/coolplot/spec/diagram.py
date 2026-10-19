# -*- coding: utf-8 -*-
"""What a chart shows, as one immutable value.

:class:`DiagramSpec` holds every choice a user made: fluid (a CoolProp
fluid or humid air), diagram type, units, calculation region, settings,
isoline families, cycles, style overrides, zoom window and title. All
values are in SI units. It never computes anything; the engine and the
compose layer turn it into a scene. A property diagram and a
psychrometric chart are the same kind of value; the diagram type carries
the chart kind.

Because a spec is immutable, an application can keep old specs for undo,
compare two of them to see what changed, or send one to a worker thread.
Change it with the ``with_*`` methods, which return a new spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional, Tuple

from ..core.cycle import Cycle, StateInput, check_loops, check_paths, default_loops
from ..core.diagram_type import DiagramType
from ..core.limits import Region, Relative, TpLimits, get_tp_limits
from ..core.quantities import quantity_key
from ..core.state import StatePoint
from ..core.units import UNIT_SYSTEMS, Unit, UnitSystem, get_unit_system
from ..style.values import LineStyle, MarkerStyle, style_from_dict, style_to_dict
from .fluid import FluidSpec, HumidAirSpec, fluid_spec_from_dict
from .settings import Settings, get_settings

Limits = Optional[Tuple[float, float]]

#: The saturation quantities a family of lines can be placed by.
ANCHOR_KEYS = ("T", "p")

#: How lines placed by saturation states are labelled.
ANCHOR_LABELS = ("saturation", "value")


def _snap(value: float) -> float:
    """12 significant digits, as coolplot.engine.planning.snap does for isoline values."""
    return float("{0:.12g}".format(value))


@dataclass(frozen=True)
class SaturationAnchor:
    """Place a family of lines through saturation states at even steps

    For example the isentropes of a log(p)-h chart through the saturated
    vapour every 10 K of saturation temperature: ``by="T"``,
    ``step_SI=10.0``, ``Q=1.0``. The steps land on round values in the
    chart's display units (0, 10, 20 deg C, not 273.15, 283.15 K), from
    the lowest saturation state of the chart to just below the critical
    point, or within ``range_SI`` when given.

    Attributes
    ----------
    by : str
        "T" (saturation temperature) or "p" (saturation pressure).
    step_SI : float
        The step as a difference in SI units: K for "T", Pa for "p".
    Q : float
        Vapour quality of the saturation states: 1 the saturated vapour
        (dew point of a blend), 0 the saturated liquid (bubble point).
    range_SI : (min, max) or None
        Saturation temperatures or pressures to place lines between, in SI
        units; None for the whole saturation range of the chart.
    label : str
        "value" (the default) labels each line with its own value, e.g.
        "s=2.321 kJ/kg/K"; "saturation" with the saturation state it was
        placed through, e.g. "T_sat=0 deg C".
    """
    by: str = "T"
    step_SI: float = 10.0
    Q: float = 1.0
    range_SI: Limits = None
    label: str = "value"

    def __post_init__(self):
        by = quantity_key(self.by)
        if by not in ANCHOR_KEYS:
            raise ValueError("Lines can be placed by saturation temperature 'T' or pressure 'p', "
                             "not '{0}'.".format(self.by))
        # Snapped like isoline values: -40 deg C converted to K is 233.14999999999998
        step = _snap(float(self.step_SI))
        if not step > 0.0:
            raise ValueError("The step between saturation states has to be positive, not {0}.".format(self.step_SI))
        Q = float(self.Q)
        if not 0.0 <= Q <= 1.0:
            raise ValueError("The vapour quality of the saturation states has to lie between 0 and 1, "
                             "not {0}.".format(self.Q))
        if self.label not in ANCHOR_LABELS:
            raise ValueError("The label of lines placed by saturation states is one of {0}, not '{1}'.".format(
                ANCHOR_LABELS, self.label))
        object.__setattr__(self, "by", by)
        object.__setattr__(self, "step_SI", step)
        object.__setattr__(self, "Q", Q)
        if self.range_SI is not None:
            lo, hi = sorted(_snap(float(v)) for v in self.range_SI)
            object.__setattr__(self, "range_SI", (lo, hi))

    def to_dict(self) -> dict:
        """The record of docs/reference/contracts.md for this placement."""
        return {"by": self.by, "step_SI": self.step_SI, "Q": self.Q,
                "range_SI": None if self.range_SI is None else list(self.range_SI), "label": self.label}

    @classmethod
    def from_dict(cls, data: dict) -> "SaturationAnchor":
        """A placement from its record, see :meth:`to_dict`."""
        return cls(**data)


@dataclass(frozen=True)
class IsolineSet:
    """One family of isolines, values in SI units

    Either ``values_SI`` lists the constant values, or ``anchor`` places
    the lines through saturation states (see :class:`SaturationAnchor`),
    or ``num`` values are spread over ``range_SI`` (the whole calculation
    region if None). ``points`` overrides ``Settings.calc`` for this
    family when given.
    """
    key: str
    values_SI: Optional[Tuple[float, ...]] = None
    num: int = 15
    range_SI: Limits = None
    rounding: bool = False
    points: Optional[int] = None
    labels: bool = False
    anchor: Optional[SaturationAnchor] = None

    def __post_init__(self):
        object.__setattr__(self, "key", quantity_key(self.key))
        if self.anchor is not None:
            if isinstance(self.anchor, dict):
                object.__setattr__(self, "anchor", SaturationAnchor.from_dict(self.anchor))
            elif not isinstance(self.anchor, SaturationAnchor):
                raise TypeError("anchor has to be a SaturationAnchor, not {0}.".format(type(self.anchor).__name__))
            if self.values_SI is not None or self.range_SI is not None:
                raise ValueError("Give either the values or range of the lines or their saturation anchor, not "
                                 "both; the anchor has its own range.")
            if self.key == "Q":
                raise ValueError("Lines of constant vapour quality cannot be placed by saturation states.")
        if self.values_SI is not None:
            object.__setattr__(self, "values_SI", tuple(float(v) for v in self.values_SI))
        if self.range_SI is not None:
            lo, hi = sorted(float(v) for v in self.range_SI)
            object.__setattr__(self, "range_SI", (lo, hi))
        if int(self.num) < 1:
            raise ValueError("Ask for at least one isoline, not {0}.".format(self.num))
        object.__setattr__(self, "num", int(self.num))
        if self.points is not None:
            if int(self.points) < 2:
                raise ValueError("An isoline needs at least 2 points, not {0}.".format(self.points))
            object.__setattr__(self, "points", int(self.points))

    def to_dict(self) -> dict:
        """The record of docs/reference/contracts.md for this family of lines."""
        return {"key": self.key, "values_SI": None if self.values_SI is None else list(self.values_SI),
                "num": self.num, "range_SI": None if self.range_SI is None else list(self.range_SI),
                "rounding": self.rounding, "points": self.points, "labels": self.labels,
                "anchor": None if self.anchor is None else self.anchor.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "IsolineSet":
        """A family of lines from its record, see :meth:`to_dict`. Records of 1.0 have no anchor."""
        data = dict(data)
        anchor = data.pop("anchor", None)
        return cls(**data, anchor=None if anchor is None else SaturationAnchor.from_dict(anchor))


@dataclass(frozen=True)
class ProcessSpec:
    """A process or cycle to draw: a line through some states, markers on others"""
    name: str
    line_states: Tuple[StatePoint, ...] = ()
    marker_states: Tuple[StatePoint, ...] = ()
    line_style: Optional[LineStyle] = None
    marker_style: Optional[MarkerStyle] = None

    def __post_init__(self):
        object.__setattr__(self, "line_states", tuple(self.line_states))
        object.__setattr__(self, "marker_states", tuple(self.marker_states))
        for state in self.line_states + self.marker_states:
            if not isinstance(state, StatePoint):
                raise TypeError("Process '{0}': expected StatePoint values, got {1}.".format(
                    self.name, type(state).__name__))

    def to_dict(self) -> dict:
        """The record of docs/reference/contracts.md for this process."""
        return {"name": self.name,
                "line_states": [s.to_dict() for s in self.line_states],
                "marker_states": [s.to_dict() for s in self.marker_states],
                "line_style": None if self.line_style is None else style_to_dict(self.line_style),
                "marker_style": None if self.marker_style is None else style_to_dict(self.marker_style)}

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessSpec":
        """A process from its record, see :meth:`to_dict`."""
        return cls(data["name"],
                   tuple(StatePoint.from_dict(s) for s in data.get("line_states", ())),
                   tuple(StatePoint.from_dict(s) for s in data.get("marker_states", ())),
                   None if data.get("line_style") is None else style_from_dict(LineStyle, data["line_style"]),
                   None if data.get("marker_style") is None else style_from_dict(MarkerStyle, data["marker_style"]))


def _checked_states(name: str, states) -> Tuple[Tuple[int, StateInput], ...]:
    """(number, StateInput) pairs sorted by number; numbers unique, at least one state."""
    items = states.items() if isinstance(states, dict) else states
    checked = tuple(sorted((int(n), s) for n, s in items))
    if not checked:
        raise ValueError("Cycle '{0}' has no states.".format(name))
    if len({n for n, _ in checked}) != len(checked):
        raise ValueError("Cycle '{0}': a state number is used twice.".format(name))
    for number, given in checked:
        if not isinstance(given, StateInput):
            raise TypeError("Cycle '{0}', state {1}: expected a StateInput.".format(name, number))
    return checked


@dataclass(frozen=True)
class CycleSpec:
    """A cycle to draw: numbered states, the chains through them and how paths are drawn

    ``states`` are (number, StateInput) pairs in SI units, ``loops`` chains
    of state numbers (one closed loop through all states in ascending order
    if empty), ``paths`` (from, to) -> path kind for connections that should
    not use "auto". ``numbers`` shows the state numbers. ``steps`` is the
    number of segments per drawn path.
    """
    name: str
    states: Tuple[Tuple[int, StateInput], ...]
    loops: Tuple[Tuple[int, ...], ...] = ()
    paths: Tuple[Tuple[Tuple[int, int], str], ...] = ()
    numbers: bool = True
    line_style: Optional[LineStyle] = None
    marker_style: Optional[MarkerStyle] = None
    steps: int = 20

    def __post_init__(self):
        states = _checked_states(self.name, self.states)
        numbers = [n for n, _ in states]
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "loops", check_loops(numbers, self.loops) if self.loops else default_loops(numbers))
        object.__setattr__(self, "paths", check_paths(self.paths))
        if int(self.steps) < 1:
            raise ValueError("Cycle '{0}': steps has to be at least 1.".format(self.name))
        object.__setattr__(self, "steps", int(self.steps))
        object.__setattr__(self, "numbers", bool(self.numbers))

    @classmethod
    def from_cycle(cls, cycle: Cycle, **changes) -> "CycleSpec":
        """A spec that draws a computed :class:`coolplot.core.cycle.Cycle` as it is."""
        values = dict(name=cycle.name, states=tuple((n, StateInput(state=s)) for n, s in cycle.states),
                      loops=cycle.loops, paths=cycle.paths)
        values.update({k: v for k, v in changes.items() if v is not None})
        return cls(**values)

    def to_dict(self) -> dict:
        """The record of docs/reference/contracts.md for this cycle."""
        return {"name": self.name, "states": [[n, s.to_dict()] for n, s in self.states],
                "loops": [list(c) for c in self.loops], "paths": [[list(p), k] for p, k in self.paths],
                "numbers": self.numbers, "steps": self.steps,
                "line_style": None if self.line_style is None else style_to_dict(self.line_style),
                "marker_style": None if self.marker_style is None else style_to_dict(self.marker_style)}

    @classmethod
    def from_dict(cls, data: dict) -> "CycleSpec":
        """A cycle from its record, see :meth:`to_dict`."""
        return cls(data["name"], tuple((n, StateInput.from_dict(s)) for n, s in data["states"]),
                   tuple(tuple(c) for c in data.get("loops", ())),
                   tuple((tuple(p), k) for p, k in data.get("paths", ())), data.get("numbers", True),
                   None if data.get("line_style") is None else style_from_dict(LineStyle, data["line_style"]),
                   None if data.get("marker_style") is None else style_from_dict(MarkerStyle, data["marker_style"]),
                   data.get("steps", 20))


@dataclass(frozen=True)
class DiagramSpec:
    """Everything a chart shows, see the module docstring

    ``fluid`` is a :class:`FluidSpec` for a property diagram or a
    :class:`HumidAirSpec` for a psychrometric chart, and ``limits`` a
    :class:`TpLimits` (fluid) or a :class:`Region` with bounds on T and W
    (humid air); the chart kind of ``diagram`` has to match.
    ``style_overrides`` maps an isoline quantity to LineStyle field changes
    on top of the theme, stored as sorted pairs so the spec stays hashable.
    ``view_SI`` is the zoom window ((x_min, x_max), (y_min, y_max)) in SI
    units, None for the full calculation region.
    """
    fluid: Any
    diagram: DiagramType = DiagramType("p", "h")
    units: UnitSystem = field(default_factory=lambda: get_unit_system("engineering"))
    limits: Any = field(default_factory=lambda: get_tp_limits("DEF"))
    settings: Settings = field(default_factory=Settings)
    isolines: Tuple[IsolineSet, ...] = ()
    processes: Tuple[ProcessSpec, ...] = ()
    cycles: Tuple[CycleSpec, ...] = ()
    style_overrides: Tuple[Tuple[str, Tuple[Tuple[str, Any], ...]], ...] = ()
    view_SI: Tuple[Limits, Limits] = (None, None)
    title: str = ""

    def __post_init__(self):
        fluid = self.fluid if isinstance(self.fluid, HumidAirSpec) else FluidSpec.parse(self.fluid)
        diagram = DiagramType.parse(self.diagram)
        if diagram.kind != fluid.kind:
            raise ValueError("A {0} diagram cannot show {1}.".format(diagram.name, fluid.name))
        limits = _checked_limits(diagram, self.limits)
        object.__setattr__(self, "fluid", fluid)
        object.__setattr__(self, "diagram", diagram)
        object.__setattr__(self, "units", get_unit_system(self.units))
        object.__setattr__(self, "limits", limits)
        object.__setattr__(self, "settings", get_settings(self.settings))
        _unique([s.key for s in self.isolines], "Each isoline quantity may appear only once")
        for iso_set in self.isolines:
            if not diagram.supports(iso_set.key):
                raise ValueError("Lines of constant '{0}' cannot be drawn in a {1} diagram.".format(
                    iso_set.key, diagram.name))
            if iso_set.anchor is not None and fluid.kind != "fluid":
                raise ValueError("Lines are placed by saturation states only in charts of a fluid, "
                                 "not of {0}.".format(fluid.name))
        _unique([p.name for p in self.processes], "Process names have to be unique")
        _unique([c.name for c in self.cycles], "Cycle names have to be unique")
        object.__setattr__(self, "cycles", tuple(self.cycles))
        object.__setattr__(self, "view_SI", _checked_view(self.view_SI))
        object.__setattr__(self, "isolines", tuple(self.isolines))
        object.__setattr__(self, "processes", tuple(self.processes))
        object.__setattr__(self, "style_overrides", tuple(sorted(
            (quantity_key(k), tuple(sorted(dict(v).items()))) for k, v in self.style_overrides)))

    # Reading ------------------------------------------------------------------
    def isoline_set(self, key: str) -> Optional[IsolineSet]:
        """The family of lines of constant ``key``, or None."""
        key = quantity_key(key)
        return next((s for s in self.isolines if s.key == key), None)

    def style_override(self, key: str) -> Dict[str, Any]:
        """LineStyle changes for one isoline family, empty if none."""
        return dict(dict(self.style_overrides).get(quantity_key(key), ()))

    # Deriving -----------------------------------------------------------------
    def with_(self, **changes) -> "DiagramSpec":
        """Copy with some fields changed, e.g. spec.with_(units="SI")."""
        return replace(self, **changes)

    def with_isolines(self, iso_set: IsolineSet) -> "DiagramSpec":
        """Add a family, or replace the family of the same quantity in place."""
        if self.isoline_set(iso_set.key) is None:
            return replace(self, isolines=self.isolines + (iso_set,))
        return replace(self, isolines=tuple(iso_set if s.key == iso_set.key else s for s in self.isolines))

    def without_isolines(self, key: str) -> "DiagramSpec":
        """A copy without the family of lines of constant ``key``."""
        key = quantity_key(key)
        return replace(self, isolines=tuple(s for s in self.isolines if s.key != key))

    def with_process(self, process: ProcessSpec) -> "DiagramSpec":
        """Add a process, or replace the process of the same name in place."""
        if all(p.name != process.name for p in self.processes):
            return replace(self, processes=self.processes + (process,))
        return replace(self, processes=tuple(process if p.name == process.name else p for p in self.processes))

    def without_process(self, name: str) -> "DiagramSpec":
        """A copy without the process called ``name``."""
        return replace(self, processes=tuple(p for p in self.processes if p.name != name))

    def with_cycle(self, cycle: CycleSpec) -> "DiagramSpec":
        """Add a cycle, or replace the cycle of the same name in place."""
        if all(c.name != cycle.name for c in self.cycles):
            return replace(self, cycles=self.cycles + (cycle,))
        return replace(self, cycles=tuple(cycle if c.name == cycle.name else c for c in self.cycles))

    def without_cycle(self, name: str) -> "DiagramSpec":
        """A copy without the cycle called ``name``."""
        return replace(self, cycles=tuple(c for c in self.cycles if c.name != name))

    def with_style_override(self, key: str, **changes) -> "DiagramSpec":
        """Add LineStyle changes for one family; without changes, remove its overrides."""
        key = quantity_key(key)
        overrides = dict(self.style_overrides)
        if changes:
            overrides[key] = tuple(dict(dict(overrides.get(key, ())), **changes).items())
        else:
            overrides.pop(key, None)
        return replace(self, style_overrides=tuple(overrides.items()))

    # Storage ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """Plain data, e.g. for json.dump. :meth:`from_dict` reverses it."""
        return {"fluid": self.fluid.to_dict(), "diagram": self.diagram.name,
                "units": _units_to_dict(self.units), "limits": _limits_to_dict(self.limits),
                "settings": self.settings.to_dict(),
                "isolines": [s.to_dict() for s in self.isolines],
                "processes": [p.to_dict() for p in self.processes],
                "cycles": [c.to_dict() for c in self.cycles],
                "style_overrides": {k: {name: _plain(v) for name, v in changes}
                                    for k, changes in self.style_overrides},
                "view_SI": [None if lim is None else list(lim) for lim in self.view_SI],
                "title": self.title}

    @classmethod
    def from_dict(cls, data: dict) -> "DiagramSpec":
        """A spec from its record, see :meth:`to_dict`."""
        overrides = tuple((k, tuple((name, _hashable(v)) for name, v in changes.items()))
                          for k, changes in data.get("style_overrides", {}).items())
        return cls(fluid=fluid_spec_from_dict(data["fluid"]),
                   diagram=DiagramType.parse(data.get("diagram", "ph")),
                   units=_units_from_dict(data.get("units", "engineering")),
                   limits=_limits_from_dict(data.get("limits", "DEF")),
                   settings=Settings.from_dict(data.get("settings", {})),
                   isolines=tuple(IsolineSet.from_dict(s) for s in data.get("isolines", ())),
                   processes=tuple(ProcessSpec.from_dict(p) for p in data.get("processes", ())),
                   cycles=tuple(CycleSpec.from_dict(c) for c in data.get("cycles", ())),
                   style_overrides=overrides,
                   view_SI=tuple(None if lim is None else tuple(lim) for lim in data.get("view_SI", (None, None))),
                   title=data.get("title", ""))


# Validation helpers ----------------------------------------------------------
def _checked_limits(diagram: DiagramType, limits):
    """The limits value of a spec: TpLimits for a fluid, a Region on the axes for humid air."""
    if diagram.kind == "fluid":
        if isinstance(limits, Region):
            raise ValueError("A {0} diagram takes TpLimits (bounds on T and p), not a Region.".format(diagram.name))
        return get_tp_limits(limits)
    if not isinstance(limits, Region) or any(k not in dict(limits.bounds) for k in (diagram.x, diagram.y)):
        raise ValueError("A {0} chart needs a Region with bounds on '{1}' and '{2}', not {3!r}.".format(
            diagram.name, diagram.x, diagram.y, limits))
    return limits


def _unique(names, message: str):
    if len(set(names)) != len(names):
        raise ValueError("{0}, got {1}.".format(message, names))


def _checked_view(view_SI):
    view = tuple(None if lim is None else tuple(float(v) for v in lim) for lim in view_SI)
    if len(view) != 2 or any(lim is not None and len(lim) != 2 for lim in view):
        raise ValueError("view_SI has to be (x_limits, y_limits), each None or (min, max).")
    return view


# JSON helpers ----------------------------------------------------------------
def _plain(value):
    """Tuples (such as dash patterns) become lists for JSON."""
    return list(value) if isinstance(value, tuple) else value


def _hashable(value):
    return tuple(value) if isinstance(value, list) else value


def _units_to_dict(units: UnitSystem):
    if UNIT_SYSTEMS.get(units.name.upper()) == units:
        return units.name
    return {"name": units.name,
            "units": {k: [u.label, u.scale, u.offset] + ([u.difference_label] if u.difference_label else [])
                      for k, u in units.units.items()}}


def _units_from_dict(data) -> UnitSystem:
    if isinstance(data, str):
        # A record saved by CoolPlot 0.4 names the engineering system "EUR";
        # it still reads (a saved file is data, not a call). The name is
        # refused in calls since 1.0, see get_unit_system.
        return get_unit_system("engineering" if data.strip().upper() == "EUR" else data)
    return UnitSystem(data["name"], {k: Unit(*v) for k, v in data["units"].items()})


def _limits_to_dict(limits) -> dict:
    if isinstance(limits, Region):
        return limits.to_dict()

    def bound(value):
        return {"relative": value.factor} if isinstance(value, Relative) else value
    return {name: bound(getattr(limits, name)) for name in ("T_min", "T_max", "p_min", "p_max")}


def _limits_from_dict(data):
    if isinstance(data, str):
        return get_tp_limits(data)
    if "bounds" in data:
        return Region.from_dict(data)

    def bound(value):
        return Relative(float(value["relative"])) if isinstance(value, dict) else value
    return TpLimits(**{name: bound(data.get(name)) for name in ("T_min", "T_max", "p_min", "p_max")})
