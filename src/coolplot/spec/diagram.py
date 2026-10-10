# -*- coding: utf-8 -*-
"""What a diagram shows, as one immutable value.

:class:`DiagramSpec` holds every choice a user made: fluid, diagram type,
units, calculation region, settings, isoline families, processes, style
overrides, zoom window and title. All values are in SI units. It never
computes anything; the engine and the compose layer turn it into a scene.

Because a spec is immutable, an application can keep old specs for undo,
compare two of them to see what changed, or send one to a worker thread.
Change it with the ``with_*`` methods, which return a new spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional, Tuple

from ..core.diagram_type import DiagramType
from ..core.limits import Relative, TpLimits, get_tp_limits
from ..core.quantities import quantity_key
from ..core.state import StatePoint
from ..core.units import UNIT_SYSTEMS, Unit, UnitSystem, get_unit_system
from ..style.values import LineStyle, MarkerStyle, style_from_dict, style_to_dict
from .fluid import FluidSpec
from .settings import Settings, get_settings

Limits = Optional[Tuple[float, float]]


@dataclass(frozen=True)
class IsolineSet:
    """One family of isolines, values in SI units

    Either ``values_SI`` lists the constant values, or ``num`` values are
    spread over ``range_SI`` (the whole calculation region if None).
    ``points`` overrides ``Settings.calc`` for this family when given.
    """
    key: str
    values_SI: Optional[Tuple[float, ...]] = None
    num: int = 15
    range_SI: Limits = None
    rounding: bool = False
    points: Optional[int] = None
    labels: bool = False

    def __post_init__(self):
        object.__setattr__(self, "key", quantity_key(self.key))
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
        return {"key": self.key, "values_SI": None if self.values_SI is None else list(self.values_SI),
                "num": self.num, "range_SI": None if self.range_SI is None else list(self.range_SI),
                "rounding": self.rounding, "points": self.points, "labels": self.labels}

    @classmethod
    def from_dict(cls, data: dict) -> "IsolineSet":
        return cls(**data)


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
        return {"name": self.name,
                "line_states": [s.to_dict() for s in self.line_states],
                "marker_states": [s.to_dict() for s in self.marker_states],
                "line_style": None if self.line_style is None else style_to_dict(self.line_style),
                "marker_style": None if self.marker_style is None else style_to_dict(self.marker_style)}

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessSpec":
        return cls(data["name"],
                   tuple(StatePoint.from_dict(s) for s in data.get("line_states", ())),
                   tuple(StatePoint.from_dict(s) for s in data.get("marker_states", ())),
                   None if data.get("line_style") is None else style_from_dict(LineStyle, data["line_style"]),
                   None if data.get("marker_style") is None else style_from_dict(MarkerStyle, data["marker_style"]))


@dataclass(frozen=True)
class DiagramSpec:
    """Everything a property diagram shows, see the module docstring

    ``style_overrides`` maps an isoline quantity to LineStyle field changes
    on top of the theme, stored as sorted pairs so the spec stays hashable.
    ``view_SI`` is the zoom window ((x_min, x_max), (y_min, y_max)) in SI
    units, None for the full calculation region.
    """
    fluid: FluidSpec
    diagram: DiagramType = DiagramType("p", "h")
    units: UnitSystem = field(default_factory=lambda: get_unit_system("EUR"))
    limits: TpLimits = field(default_factory=lambda: get_tp_limits("DEF"))
    settings: Settings = field(default_factory=Settings)
    isolines: Tuple[IsolineSet, ...] = ()
    processes: Tuple[ProcessSpec, ...] = ()
    style_overrides: Tuple[Tuple[str, Tuple[Tuple[str, Any], ...]], ...] = ()
    view_SI: Tuple[Limits, Limits] = (None, None)
    title: str = ""

    def __post_init__(self):
        object.__setattr__(self, "fluid", FluidSpec.parse(self.fluid))
        object.__setattr__(self, "diagram", DiagramType.parse(self.diagram))
        object.__setattr__(self, "units", get_unit_system(self.units))
        object.__setattr__(self, "limits", get_tp_limits(self.limits))
        object.__setattr__(self, "settings", get_settings(self.settings))
        keys = [s.key for s in self.isolines]
        if len(set(keys)) != len(keys):
            raise ValueError("Each isoline quantity may appear only once, got {0}.".format(keys))
        for iso_set in self.isolines:
            if not self.diagram.supports(iso_set.key):
                raise ValueError("Lines of constant '{0}' cannot be drawn in a {1} diagram.".format(
                    iso_set.key, self.diagram.name))
        names = [p.name for p in self.processes]
        if len(set(names)) != len(names):
            raise ValueError("Process names have to be unique, got {0}.".format(names))
        view = tuple(None if lim is None else tuple(float(v) for v in lim) for lim in self.view_SI)
        if len(view) != 2 or any(lim is not None and len(lim) != 2 for lim in view):
            raise ValueError("view_SI has to be (x_limits, y_limits), each None or (min, max).")
        object.__setattr__(self, "view_SI", view)
        object.__setattr__(self, "isolines", tuple(self.isolines))
        object.__setattr__(self, "processes", tuple(self.processes))
        object.__setattr__(self, "style_overrides", tuple(sorted(
            (quantity_key(k), tuple(sorted(dict(v).items()))) for k, v in self.style_overrides)))

    # Reading ------------------------------------------------------------------
    def isoline_set(self, key: str) -> Optional[IsolineSet]:
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
        key = quantity_key(key)
        return replace(self, isolines=tuple(s for s in self.isolines if s.key != key))

    def with_process(self, process: ProcessSpec) -> "DiagramSpec":
        """Add a process, or replace the process of the same name in place."""
        if all(p.name != process.name for p in self.processes):
            return replace(self, processes=self.processes + (process,))
        return replace(self, processes=tuple(process if p.name == process.name else p for p in self.processes))

    def without_process(self, name: str) -> "DiagramSpec":
        return replace(self, processes=tuple(p for p in self.processes if p.name != name))

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
                "style_overrides": {k: {name: _plain(v) for name, v in changes}
                                    for k, changes in self.style_overrides},
                "view_SI": [None if lim is None else list(lim) for lim in self.view_SI],
                "title": self.title}

    @classmethod
    def from_dict(cls, data: dict) -> "DiagramSpec":
        overrides = tuple((k, tuple((name, _hashable(v)) for name, v in changes.items()))
                          for k, changes in data.get("style_overrides", {}).items())
        return cls(fluid=FluidSpec.from_dict(data["fluid"]),
                   diagram=DiagramType.parse(data.get("diagram", "ph")),
                   units=_units_from_dict(data.get("units", "EUR")),
                   limits=_limits_from_dict(data.get("limits", "DEF")),
                   settings=Settings.from_dict(data.get("settings", {})),
                   isolines=tuple(IsolineSet.from_dict(s) for s in data.get("isolines", ())),
                   processes=tuple(ProcessSpec.from_dict(p) for p in data.get("processes", ())),
                   style_overrides=overrides,
                   view_SI=tuple(None if lim is None else tuple(lim) for lim in data.get("view_SI", (None, None))),
                   title=data.get("title", ""))


# JSON helpers ----------------------------------------------------------------
def _plain(value):
    """Tuples (such as dash patterns) become lists for JSON."""
    return list(value) if isinstance(value, tuple) else value


def _hashable(value):
    return tuple(value) if isinstance(value, list) else value


def _units_to_dict(units: UnitSystem):
    if UNIT_SYSTEMS.get(units.name) == units:
        return units.name
    return {"name": units.name,
            "units": {k: [u.label, u.scale, u.offset] for k, u in units.units.items()}}


def _units_from_dict(data) -> UnitSystem:
    if isinstance(data, str):
        return get_unit_system(data)
    return UnitSystem(data["name"], {k: Unit(*v) for k, v in data["units"].items()})


def _limits_to_dict(limits: TpLimits) -> dict:
    def bound(value):
        return {"relative": value.factor} if isinstance(value, Relative) else value
    return {name: bound(getattr(limits, name)) for name in ("T_min", "T_max", "p_min", "p_max")}


def _limits_from_dict(data) -> TpLimits:
    if isinstance(data, str):
        return get_tp_limits(data)

    def bound(value):
        return Relative(float(value["relative"])) if isinstance(value, dict) else value
    return TpLimits(**{name: bound(data.get(name)) for name in ("T_min", "T_max", "p_min", "p_max")})
