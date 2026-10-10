# -*- coding: utf-8 -*-
"""All tunable values of a diagram in one immutable value.

:class:`Settings` is split by what a change costs, because that decides
what has to be redone (docs/architecture.md, section 5):

* ``calc``: how curves are calculated. A change recalculates the affected
  curves, and these values are part of the cache key.
* ``look``: the theme, every colour, line, marker and font. A change only
  restyles items.
* ``labels``: what isoline labels say and where they go. A change only
  rebuilds the labels.
* ``page``: hints for the backends, such as the preferred canvas size. A
  change only affects the layout of the page.

Presets cover the common cases; derive variants with :meth:`Settings.with_`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace

from ..style.theme import Theme, get_theme

SATURATION_SPACINGS = ("critical", "linear")


@dataclass(frozen=True)
class CalcSettings:
    """How curves are calculated

    Attributes
    ----------
    points : int
        Points per isoline. A family of isolines can override it.
    saturation_points : int
        Points per line of constant vapour quality.
    saturation_spacing : str
        "critical" puts the points closer together towards the critical
        point, where the dome bends most; "linear" spaces them evenly in
        temperature.
    critical_margin : float
        Distance kept from the triple point and the critical point,
        relative to the critical values. Saturation solvers become
        unreliable closer to the critical point.
    warn_failed_fraction : float
        Warn (once per curve) when more than this fraction of its points
        could not be calculated. A curve with fewer than two valid points
        is always left out with a warning.
    """
    points: int = 250
    saturation_points: int = 250
    saturation_spacing: str = "critical"
    critical_margin: float = 1e-7
    warn_failed_fraction: float = 0.1

    def __post_init__(self):
        for name in ("points", "saturation_points"):
            value = int(getattr(self, name))
            if value < 2:
                raise ValueError("CalcSettings.{0} has to be at least 2, not {1}.".format(name, value))
            object.__setattr__(self, name, value)
        if self.saturation_spacing not in SATURATION_SPACINGS:
            raise ValueError("Unknown saturation_spacing '{0}', expected one of {1}.".format(
                self.saturation_spacing, SATURATION_SPACINGS))
        if not 0.0 < float(self.critical_margin) < 0.1:
            raise ValueError("critical_margin has to be between 0 and 0.1, not {0}.".format(self.critical_margin))
        if not 0.0 <= float(self.warn_failed_fraction) <= 1.0:
            raise ValueError("warn_failed_fraction has to be between 0 and 1.")
        object.__setattr__(self, "critical_margin", float(self.critical_margin))
        object.__setattr__(self, "warn_failed_fraction", float(self.warn_failed_fraction))


@dataclass(frozen=True)
class LabelSettings:
    """What isoline labels say and where they sit

    Attributes
    ----------
    position : float
        Where along the visible part of a line its label sits, from 0
        (start) to 1 (end).
    digits : int
        Significant digits of the values shown in labels.
    show_units : bool
        Append the unit to every label value.
    """
    position: float = 0.5
    digits: int = 4
    show_units: bool = True

    def __post_init__(self):
        if not 0.0 <= float(self.position) <= 1.0:
            raise ValueError("LabelSettings.position has to be between 0 and 1.")
        if not 1 <= int(self.digits) <= 12:
            raise ValueError("LabelSettings.digits has to be between 1 and 12.")
        object.__setattr__(self, "position", float(self.position))
        object.__setattr__(self, "digits", int(self.digits))

    def format_value(self, value: float) -> str:
        """A label value with the configured number of significant digits."""
        return "{0:.{1}g}".format(value, self.digits)


@dataclass(frozen=True)
class PageSettings:
    """Hints for the backends; each backend may lay out the page its own way

    Attributes
    ----------
    width_pt, height_pt : float
        Preferred canvas size in points (72 pt = 1 inch). Used when a
        renderer is created for the diagram.
    font_scale : float
        Factor applied to every font size of the theme, for example to
        make text readable on a small figure in a paper.
    """
    width_pt: float = 576.0
    height_pt: float = 432.0
    font_scale: float = 1.0

    def __post_init__(self):
        for name in ("width_pt", "height_pt", "font_scale"):
            value = float(getattr(self, name))
            if not value > 0.0:
                raise ValueError("PageSettings.{0} has to be positive, not {1}.".format(name, value))
            object.__setattr__(self, name, value)

    @property
    def size_in(self):
        """(width, height) in inches, the unit matplotlib uses for figures."""
        return self.width_pt / 72.0, self.height_pt / 72.0


@dataclass(frozen=True)
class Settings:
    """Everything that tunes a diagram, see the module docstring"""
    calc: CalcSettings = field(default_factory=CalcSettings)
    look: Theme = field(default_factory=lambda: get_theme("default"))
    labels: LabelSettings = field(default_factory=LabelSettings)
    page: PageSettings = field(default_factory=PageSettings)

    def __post_init__(self):
        object.__setattr__(self, "look", get_theme(self.look))
        for name, cls in (("calc", CalcSettings), ("labels", LabelSettings), ("page", PageSettings)):
            if not isinstance(getattr(self, name), cls):
                raise TypeError("Settings.{0} has to be a {1}.".format(name, cls.__name__))

    def with_(self, calc: dict = None, look=None, labels: dict = None, page: dict = None) -> "Settings":
        """Copy with some values changed.

        ``calc``, ``labels`` and ``page`` take dicts of the fields to change,
        ``look`` a theme or theme name, for example
        ``settings.with_(calc={"points": 100}, look="dark")``.
        """
        return replace(self,
                       calc=replace(self.calc, **calc) if calc else self.calc,
                       look=get_theme(look) if look is not None else self.look,
                       labels=replace(self.labels, **labels) if labels else self.labels,
                       page=replace(self.page, **page) if page else self.page)

    def to_dict(self) -> dict:
        return {"calc": asdict(self.calc), "look": self.look.to_dict(),
                "labels": asdict(self.labels), "page": asdict(self.page)}

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        def part(part_cls, values):
            known = {f.name for f in fields(part_cls)}
            unknown = set(values or {}) - known
            if unknown:
                raise ValueError("Unknown {0} fields: {1}.".format(part_cls.__name__, sorted(unknown)))
            return part_cls(**(values or {}))
        look = data.get("look")
        return cls(calc=part(CalcSettings, data.get("calc")),
                   look=Theme.from_dict(look) if isinstance(look, dict) else get_theme(look or "default"),
                   labels=part(LabelSettings, data.get("labels")),
                   page=part(PageSettings, data.get("page")))


#: Ready-made settings. "interactive" uses few points so that dragging
#: stays smooth; switch to "screen" for the final picture.
PRESETS = {
    "screen": Settings(),
    "print": Settings(look=get_theme("print"), page=PageSettings(504.0, 360.0)),
    "publication": Settings(calc=CalcSettings(points=400, saturation_points=400), look=get_theme("print"),
                            labels=LabelSettings(digits=3),
                            page=PageSettings(252.0, 189.0, font_scale=0.85)),
    "interactive": Settings(calc=CalcSettings(points=60, saturation_points=100)),
}


def get_settings(settings) -> Settings:
    """Accept a Settings value, a preset name or None (the "screen" preset)."""
    if settings is None:
        return PRESETS["screen"]
    if isinstance(settings, Settings):
        return settings
    try:
        return PRESETS[str(settings).lower()]
    except KeyError:
        raise ValueError("Unknown settings preset '{0}', expected one of {1}.".format(settings, sorted(PRESETS)))
