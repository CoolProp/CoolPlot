# -*- coding: utf-8 -*-
"""All tunable values of a diagram in one immutable value.

:class:`Settings` is split by what a change costs, because that decides
what has to be redone (docs/contributing/architecture.md, section 5):

* ``calc``: how curves are calculated. A change recalculates the affected
  curves, and these values are part of the cache key.
* ``look``: the theme, every colour, line, marker and font. A change only
  restyles items.
* ``labels``: what isoline labels say and where they go. A change only
  rebuilds the labels.
* ``page``: hints for the backends, such as the preferred canvas size. A
  change only affects the layout of the page.
* ``branding``: a badge with logo, references and text lines, and a
  watermark. A change only affects the layout of the page.

Presets cover the common cases; derive variants with :meth:`Settings.with_`.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Tuple

from ..core.numbers import format_number
from ..style.theme import Theme, get_theme

SATURATION_SPACINGS = ("critical", "linear")
SOLVERS = ("auto", "tracer", "flash")


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
    solver : str
        How isolines are calculated. "flash" solves every point on its own
        with CoolProp; "tracer" walks along the line and starts each point
        from the previous one, which is much faster for mixtures; "auto"
        uses the tracer for mixtures and plain flashes for pure fluids.
    preview_points : int
        With a background engine, a missing curve is first computed with
        this many points and drawn while the full curve is computed. 0
        switches the preview off.
    critical_margin : float
        Distance kept from the triple point and the critical point,
        relative to the critical values. Saturation solvers become
        unreliable closer to the critical point.
    warn_failed_fraction : float
        Warn (once per curve) when more than this fraction of its points
        could not be calculated inside the line; failures at the ends only
        make a line shorter. A curve with fewer than two valid points
        is always left out with a warning.
    """
    points: int = 250
    saturation_points: int = 250
    saturation_spacing: str = "critical"
    solver: str = "auto"
    preview_points: int = 40
    critical_margin: float = 1e-7
    warn_failed_fraction: float = 0.1

    def __post_init__(self):
        for name in ("points", "saturation_points"):
            value = int(getattr(self, name))
            if value < 2:
                raise ValueError("CalcSettings.{0} has to be at least 2, not {1}.".format(name, value))
            object.__setattr__(self, name, value)
        preview = int(self.preview_points)
        if preview != 0 and preview < 2:
            raise ValueError("CalcSettings.preview_points has to be 0 (off) or at least 2, not {0}.".format(preview))
        object.__setattr__(self, "preview_points", preview)
        if self.saturation_spacing not in SATURATION_SPACINGS:
            raise ValueError("Unknown saturation_spacing '{0}', expected one of {1}.".format(
                self.saturation_spacing, SATURATION_SPACINGS))
        if self.solver not in SOLVERS:
            raise ValueError("Unknown solver '{0}', expected one of {1}.".format(self.solver, SOLVERS))
        if not 0.0 < float(self.critical_margin) < 0.1:
            raise ValueError("critical_margin has to be between 0 and 0.1, not {0}.".format(self.critical_margin))
        if not 0.0 <= float(self.warn_failed_fraction) <= 1.0:
            raise ValueError("warn_failed_fraction has to be between 0 and 1.")
        object.__setattr__(self, "critical_margin", float(self.critical_margin))
        object.__setattr__(self, "warn_failed_fraction", float(self.warn_failed_fraction))


LABEL_MODES = ("rails", "edge", "margin", "inline")
EDGES = ("top", "right", "bottom", "left")


def _checked_edges(edges, margin_edges):
    """The per-family edges as (family, edges) pairs and the margin edges, all known edge names."""
    edges = tuple((str(family), tuple(e)) for family, e in (edges.items() if isinstance(edges, dict) else edges))
    margin_edges = tuple(margin_edges)
    for edge in [e for _, es in edges for e in es] + list(margin_edges):
        if edge not in EDGES:
            raise ValueError("Unknown edge '{0}', expected one of {1}.".format(edge, EDGES))
    return edges, margin_edges


@dataclass(frozen=True)
class LabelSettings:
    """What isoline labels say and where they sit

    Attributes
    ----------
    mode : str
        "edge": just inside the frame where the lines leave the plot,
        clear of processes (the default). "margin": horizontal, outside the
        frame, like a second set of tick labels. "inline": at ``position``
        along each line, as in older versions.
    keep_out_pt : float
        Distance in points that labels keep from every process and its
        state points in "edge" mode.
    edges : tuple of (family, edges)
        Preferred frame edges per isoline family, best first, for "edge"
        mode. Families not listed use the edges of their
        :class:`coolplot.core.diagram_type.Family`.
    margin_edges : tuple of str
        Edges that carry labels in "margin" mode. The default legend sits
        outside on the right, so only "top" is used unless the legend is
        moved.
    fallback : bool
        In "edge" mode, put a label further along its line when no spot
        near the frame is free. Without it such lines stay unlabelled and
        the middle of the chart stays clear.
    every : int
        Label every n-th line of a family (1: all lines).
    position : float
        Where along the visible part of a line its label sits in "inline"
        mode, from 0 (start) to 1 (end).
    digits : int
        Significant digits of the values shown in labels.
    show_units : bool
        Append the unit to every label value.
    tick_digits : int
        Significant digits of tick labels; every backend writes them with
        :func:`coolplot.core.numbers.format_number`.
    """
    mode: str = "edge"
    keep_out_pt: float = 12.0
    edges: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    margin_edges: Tuple[str, ...] = ("top",)
    fallback: bool = True
    every: int = 1
    position: float = 0.5
    digits: int = 4
    show_units: bool = True
    tick_digits: int = 6

    def __post_init__(self):
        if self.mode not in LABEL_MODES:
            raise ValueError("Unknown label mode '{0}', expected one of {1}.".format(self.mode, LABEL_MODES))
        if not float(self.keep_out_pt) >= 0.0:
            raise ValueError("LabelSettings.keep_out_pt has to be zero or positive.")
        edges, margin_edges = _checked_edges(self.edges, self.margin_edges)
        if int(self.every) < 1:
            raise ValueError("LabelSettings.every has to be at least 1.")
        if not 0.0 <= float(self.position) <= 1.0:
            raise ValueError("LabelSettings.position has to be between 0 and 1.")
        for name in ("digits", "tick_digits"):
            if not 1 <= int(getattr(self, name)) <= 12:
                raise ValueError("LabelSettings.{0} has to be between 1 and 12.".format(name))
            object.__setattr__(self, name, int(getattr(self, name)))
        object.__setattr__(self, "keep_out_pt", float(self.keep_out_pt))
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "margin_edges", margin_edges)
        object.__setattr__(self, "every", int(self.every))
        object.__setattr__(self, "position", float(self.position))

    def preferred_edges(self, family: str, default: Tuple[str, ...] = EDGES) -> Tuple[str, ...]:
        """The edges set for a family, or ``default`` (usually the family's own)."""
        return dict(self.edges).get(family, default)

    def format_value(self, value: float) -> str:
        """A label value in the central number format with ``digits`` digits."""
        return format_number(value, self.digits)


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


BADGE_LOCATIONS = ("auto", "upper left", "upper right", "lower left", "lower right")
REFERENCE_STYLES = ("none", "short", "full")


def _sources(value) -> Tuple[str, ...]:
    """Picture sources as a tuple of strings; one string or path is one source."""
    if isinstance(value, (str, os.PathLike)):
        value = (value,) if os.fspath(value) else ()
    sources = tuple(os.fspath(v) for v in value)
    if any(not s for s in sources):
        raise ValueError("BrandingSettings: an empty picture source.")
    return sources


@dataclass(frozen=True)
class BrandingSettings:
    """Who made a chart and where its data come from

    Everything here is off by default. A change only affects the layout
    of the page, like :class:`PageSettings`; nothing is recalculated.

    The badge is a box in one corner of the plot area. It holds, from top
    to bottom, the logo, the references, the versions line and the
    ``lines`` given here. The watermark is a faint picture in the middle
    of the plot area, behind the grid and the lines.

    Attributes
    ----------
    logo : tuple of str
        The logo as file names or ``data:`` URIs of PNG or SVG files:
        variants of the same picture, best first. The SVG writer uses the
        first one; matplotlib (PNG and PDF output) needs a PNG, so give a
        PNG rendering of an SVG logo as well, for example
        ``("logo.svg", "logo.png")``.
    logo_width_pt : float
        Width of the logo in points.
    references : str
        "none"; "short" for the equation of state of every fluid as first
        author and year ("n-Propane: Lemmon et al. (2009)"); "full" with
        the journal, volume and pages as well. Mixtures add the
        reference of their mixing model, humid air that of ASHRAE RP-1485.
    versions : bool
        Add a line with the CoolProp and CoolPlot versions.
    lines : tuple of str
        Further lines, for example a web address and a date.
    location : str
        "auto" (the corner where the badge covers the fewest points of
        the drawn lines) or a corner:
        "upper left", "upper right", "lower left", "lower right".
    font_size_pt : float
        Size of the badge text (the theme's tick label font family).
    background_alpha : float
        Opacity of the badge background, which has the colour of the plot
        area, so the lines under the badge stay faintly visible.
    frame : bool
        Outline the badge with the colour of the axes frame.
    watermark : tuple of str
        The watermark picture, given like ``logo``. Empty for none.
    watermark_width : float
        Width of the watermark as a fraction of the plot area width; it
        is made smaller if it would be taller than 0.8 of the plot height.
    watermark_opacity : float
        Opacity of the watermark, 0 to 1.
    """
    logo: Tuple[str, ...] = ()
    logo_width_pt: float = 60.0
    references: str = "none"
    versions: bool = False
    lines: Tuple[str, ...] = ()
    location: str = "auto"
    font_size_pt: float = 6.0
    background_alpha: float = 0.85
    frame: bool = True
    watermark: Tuple[str, ...] = ()
    watermark_width: float = 0.5
    watermark_opacity: float = 0.06

    def __post_init__(self):
        object.__setattr__(self, "logo", _sources(self.logo))
        object.__setattr__(self, "watermark", _sources(self.watermark))
        lines = (self.lines,) if isinstance(self.lines, str) else self.lines
        object.__setattr__(self, "lines", tuple(str(line) for line in lines))
        if self.references not in REFERENCE_STYLES:
            raise ValueError("Unknown references style '{0}', expected one of {1}.".format(
                self.references, REFERENCE_STYLES))
        if self.location not in BADGE_LOCATIONS:
            raise ValueError("Unknown badge location '{0}', expected one of {1}.".format(
                self.location, BADGE_LOCATIONS))
        for name in ("logo_width_pt", "font_size_pt"):
            value = float(getattr(self, name))
            if not value > 0.0:
                raise ValueError("BrandingSettings.{0} has to be positive, not {1}.".format(name, value))
            object.__setattr__(self, name, value)
        for name in ("background_alpha", "watermark_opacity"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError("BrandingSettings.{0} has to be between 0 and 1, not {1}.".format(name, value))
            object.__setattr__(self, name, value)
        width = float(self.watermark_width)
        if not 0.0 < width <= 1.0:
            raise ValueError("BrandingSettings.watermark_width has to be in (0, 1], not {0}.".format(width))
        object.__setattr__(self, "watermark_width", width)
        object.__setattr__(self, "versions", bool(self.versions))
        object.__setattr__(self, "frame", bool(self.frame))

    @property
    def has_badge(self) -> bool:
        """Whether the settings ask for a badge at all."""
        return bool(self.logo or self.lines or self.versions or self.references != "none")


@dataclass(frozen=True)
class Settings:
    """Everything that tunes a diagram, see the module docstring"""
    calc: CalcSettings = field(default_factory=CalcSettings)
    look: Theme = field(default_factory=lambda: get_theme("default"))
    labels: LabelSettings = field(default_factory=LabelSettings)
    page: PageSettings = field(default_factory=PageSettings)
    branding: BrandingSettings = field(default_factory=BrandingSettings)

    def __post_init__(self):
        object.__setattr__(self, "look", get_theme(self.look))
        for name, cls in (("calc", CalcSettings), ("labels", LabelSettings), ("page", PageSettings),
                          ("branding", BrandingSettings)):
            if not isinstance(getattr(self, name), cls):
                raise TypeError("Settings.{0} has to be a {1}.".format(name, cls.__name__))

    def with_(self, calc: dict = None, look=None, labels: dict = None, page: dict = None,
              branding: dict = None) -> "Settings":
        """Copy with some values changed.

        ``calc``, ``labels``, ``page`` and ``branding`` take dicts of the
        fields to change, ``look`` a theme or theme name, for example
        ``settings.with_(calc={"points": 100}, look="dark")``. ``calc`` also
        takes a preset name: ``settings.with_(calc="interactive")`` uses few
        points while the user drags and keeps theme, labels and page;
        ``settings.with_(calc="screen")`` goes back to full detail.
        ``branding`` also takes a :class:`BrandingSettings` value.
        """
        if isinstance(calc, str):
            calc_value = get_settings(calc).calc
        elif isinstance(calc, CalcSettings):
            calc_value = calc
        else:
            calc_value = replace(self.calc, **calc) if calc else self.calc
        if isinstance(branding, BrandingSettings):
            branding_value = branding
        else:
            branding_value = replace(self.branding, **branding) if branding else self.branding
        return replace(self,
                       calc=calc_value,
                       look=get_theme(look) if look is not None else self.look,
                       labels=replace(self.labels, **labels) if labels else self.labels,
                       page=replace(self.page, **page) if page else self.page,
                       branding=branding_value)

    def to_dict(self) -> dict:
        """The settings record of docs/reference/contracts.md."""
        return {"calc": asdict(self.calc), "look": self.look.to_dict(),
                "labels": asdict(self.labels), "page": asdict(self.page),
                "branding": asdict(self.branding)}

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """Settings from their record, see :meth:`to_dict`."""
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
                   page=part(PageSettings, data.get("page")),
                   branding=part(BrandingSettings, data.get("branding")))


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
