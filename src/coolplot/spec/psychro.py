# -*- coding: utf-8 -*-
"""What a psychrometric chart shows, as one immutable value.

Like :class:`coolplot.spec.DiagramSpec` for property diagrams, a
:class:`PsychroSpec` holds every choice for a psychrometric chart in SI
units: total pressure, the visible region, the line families, the air
processes and the settings. It computes nothing and saves to JSON.

Display units are a small table of their own (``PSYCHRO_UNITS``), because
humid air has quantities the property diagrams do not use (humidity ratio,
relative humidity, wet-bulb temperature).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional, Tuple

from ..core.units import Unit
from ..style.values import LineStyle, MarkerStyle, style_from_dict, style_to_dict
from .settings import Settings, get_settings

#: Display units per unit system: key -> Unit.
PSYCHRO_UNITS = {
    "EUR": {"T": Unit("deg C", 1.0, -273.15), "Twb": Unit("deg C", 1.0, -273.15), "Tdp": Unit("deg C", 1.0, -273.15),
            "W": Unit("g/kg", 1e3), "RH": Unit("%", 100.0), "h": Unit("kJ/kg", 1e-3), "v": Unit("m3/kg"),
            "p": Unit("bar", 1e-5)},
    "SI": {"T": Unit("K"), "Twb": Unit("K"), "Tdp": Unit("K"), "W": Unit("kg/kg"), "RH": Unit("-"),
           "h": Unit("J/kg"), "v": Unit("m3/kg"), "p": Unit("Pa")},
}

#: Symbols and names used in axis titles, labels and the legend.
PSYCHRO_QUANTITIES = {
    "T": ("T", "Dry-bulb temperature"), "Twb": ("Twb", "Wet-bulb temperature"),
    "Tdp": ("Tdp", "Dew-point temperature"), "W": ("W", "Humidity ratio"),
    "RH": ("RH", "Relative humidity"), "h": ("h", "Specific enthalpy"), "v": ("v", "Specific volume"),
    "p": ("p", "Pressure"),
}

LINE_KEYS = ("RH", "Twb", "h", "v")
STATE_KEYS = ("T", "W", "RH", "Twb", "Tdp", "h", "v")


def psychro_units(units) -> dict:
    try:
        return PSYCHRO_UNITS[str(units).upper()]
    except KeyError:
        raise ValueError("Unknown unit system '{0}' for psychrometric charts, expected one of {1}.".format(
            units, sorted(PSYCHRO_UNITS)))


@dataclass(frozen=True)
class PsychroLines:
    """One family of lines; no values means round values over the chart"""
    key: str
    values_SI: Tuple[float, ...] = ()
    labels: bool = True

    def __post_init__(self):
        if self.key not in LINE_KEYS:
            raise ValueError("Unknown line family '{0}', expected one of {1}.".format(self.key, LINE_KEYS))
        values = tuple(float(v) for v in self.values_SI)
        if self.key == "RH" and any(not 0.0 < v <= 1.0 for v in values):
            raise ValueError("Relative humidity has to be above 0 and at most 100 %, got {0} (as fractions).".format(
                values))
        if self.key in ("Twb", "v") and any(not v > 0.0 for v in values):
            raise ValueError("Values of '{0}' have to be positive in SI units, got {1}.".format(self.key, values))
        object.__setattr__(self, "values_SI", values)
        object.__setattr__(self, "labels", bool(self.labels))


@dataclass(frozen=True)
class AirProcessSpec:
    """Air states joined by straight lines, e.g. heating, cooling and mixing

    Each state is given by two properties in SI units, e.g.
    (("T", 297.15), ("RH", 0.5)). ``closed`` joins the last state to the
    first.
    """
    name: str
    states: Tuple[Tuple[Tuple[str, float], ...], ...]
    closed: bool = False
    numbers: bool = True
    line_style: Optional[LineStyle] = None
    marker_style: Optional[MarkerStyle] = None

    def __post_init__(self):
        states = []
        for given in self.states:
            given = tuple((str(k), float(v)) for k, v in given)
            keys = [k for k, _ in given]
            if len(given) != 2 or len(set(keys)) != 2 or any(k not in STATE_KEYS for k in keys):
                raise ValueError("Process '{0}': a state needs two different properties out of {1}, not {2}."
                                 .format(self.name, STATE_KEYS, dict(given)))
            states.append(given)
        if not states:
            raise ValueError("Process '{0}' has no states.".format(self.name))
        object.__setattr__(self, "states", tuple(states))


@dataclass(frozen=True)
class PsychroSpec:
    """Everything a psychrometric chart shows, in SI units"""
    p_Pa: float = 101325.0
    T_range_K: Tuple[float, float] = (263.15, 323.15)
    W_range: Tuple[float, float] = (0.0, 0.030)
    units: str = "EUR"
    lines: Tuple[PsychroLines, ...] = ()
    processes: Tuple[AirProcessSpec, ...] = ()
    settings: Settings = field(default_factory=Settings)
    title: str = ""

    def __post_init__(self):
        if not float(self.p_Pa) > 0.0:
            raise ValueError("The total pressure has to be positive, not {0}.".format(self.p_Pa))
        object.__setattr__(self, "p_Pa", float(self.p_Pa))
        for name in ("T_range_K", "W_range"):
            lo, hi = sorted(float(v) for v in getattr(self, name))
            if not hi > lo:
                raise ValueError("{0} needs two different values, not {1}.".format(name, getattr(self, name)))
            object.__setattr__(self, name, (lo, hi))
        if self.T_range_K[0] <= 0.0 or self.W_range[0] < 0.0:
            raise ValueError("Temperatures have to be above 0 K and humidity ratios at least 0.")
        psychro_units(self.units)
        object.__setattr__(self, "units", str(self.units).upper())
        object.__setattr__(self, "settings", get_settings(self.settings))
        keys = [f.key for f in self.lines]
        if len(set(keys)) != len(keys):
            raise ValueError("Each line family may appear only once, got {0}.".format(keys))
        names = [p.name for p in self.processes]
        if len(set(names)) != len(names):
            raise ValueError("Process names have to be unique, got {0}.".format(names))
        object.__setattr__(self, "lines", tuple(self.lines))
        object.__setattr__(self, "processes", tuple(self.processes))

    def with_(self, **changes) -> "PsychroSpec":
        return replace(self, **changes)

    def with_lines(self, family: PsychroLines) -> "PsychroSpec":
        if all(f.key != family.key for f in self.lines):
            return replace(self, lines=self.lines + (family,))
        return replace(self, lines=tuple(family if f.key == family.key else f for f in self.lines))

    def without_lines(self, key: str) -> "PsychroSpec":
        return replace(self, lines=tuple(f for f in self.lines if f.key != key))

    def with_process(self, process: AirProcessSpec) -> "PsychroSpec":
        if all(p.name != process.name for p in self.processes):
            return replace(self, processes=self.processes + (process,))
        return replace(self, processes=tuple(process if p.name == process.name else p for p in self.processes))

    def without_process(self, name: str) -> "PsychroSpec":
        return replace(self, processes=tuple(p for p in self.processes if p.name != name))

    def to_dict(self) -> dict:
        return {"p_Pa": self.p_Pa, "T_range_K": list(self.T_range_K), "W_range": list(self.W_range),
                "units": self.units, "title": self.title, "settings": self.settings.to_dict(),
                "lines": [{"key": f.key, "values_SI": list(f.values_SI), "labels": f.labels} for f in self.lines],
                "processes": [{"name": p.name, "states": [[list(kv) for kv in s] for s in p.states],
                               "closed": p.closed, "numbers": p.numbers,
                               "line_style": None if p.line_style is None else style_to_dict(p.line_style),
                               "marker_style": None if p.marker_style is None else style_to_dict(p.marker_style)}
                              for p in self.processes]}

    @classmethod
    def from_dict(cls, data: dict) -> "PsychroSpec":
        return cls(p_Pa=data.get("p_Pa", 101325.0), T_range_K=tuple(data.get("T_range_K", (263.15, 323.15))),
                   W_range=tuple(data.get("W_range", (0.0, 0.03))), units=data.get("units", "EUR"),
                   title=data.get("title", ""), settings=Settings.from_dict(data.get("settings", {})),
                   lines=tuple(PsychroLines(f["key"], tuple(f.get("values_SI", ())), f.get("labels", True))
                               for f in data.get("lines", ())),
                   processes=tuple(AirProcessSpec(
                       p["name"], tuple(tuple(tuple(kv) for kv in s) for s in p["states"]), p.get("closed", False),
                       p.get("numbers", True),
                       None if p.get("line_style") is None else style_from_dict(LineStyle, p["line_style"]),
                       None if p.get("marker_style") is None else style_from_dict(MarkerStyle, p["marker_style"]))
                       for p in data.get("processes", ())))
