# -*- coding: utf-8 -*-
"""The property diagram: what the user asked for, turned into a scene.

:class:`PropertyDiagram` is the object applications work with. It stores
the user's choices (fluid, diagram type, units, limits, isolines, processes,
theme) and turns them into a :class:`CoolPlot.scene.Scene` on request.
It never draws anything itself; a renderer from :mod:`CoolPlot.render`
does that.

How updates stay cheap
----------------------
Changing a setting does not compute anything right away. The next call to
:meth:`PropertyDiagram.update_scene` rebuilds the full description of the
plot from the current settings, but

* every isoline comes from a cache keyed by the inputs that determine it
  (fluid model, diagram type, quantity, value, calculation domain), so only
  lines with new inputs are computed, and
* the scene compares the new items with the old ones, so a renderer only
  redraws the items that really changed.

For example, switching from EUR to SI units reuses every cached curve and
updates the coordinates of all items, whereas changing the colour of the
isotherms reuses every curve and only restyles the isotherms. Moving one
state of a cycle only touches the two items of that cycle.

All values are stored in SI units. Values passed to the public methods are
in the current unit system of the diagram and converted on entry.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

from .quantities import get_quantity, quantity_key
from .scene import AxesSpec, Line, Markers, Scene, Text
from .style import LineStyle, MarkerStyle
from .theme import Theme, get_theme
from .thermo.diagram_type import DiagramType
from .thermo.fluid import Fluid
from .thermo.isolines import CurveCache, compute_isoline, value_grid
from .thermo.limits import axis_ranges_SI, get_tp_limits, property_range_SI
from .thermo.process import StatePoint, state_point
from .units import get_unit_system


@dataclass(frozen=True)
class IsolineSet:
    """One family of isolines as requested, values in SI units

    Either ``values_SI`` lists the constant values, or ``num`` values are
    spread over ``range_SI`` (or over the whole plot if that is None).
    """
    key: str
    values_SI: Optional[Tuple[float, ...]] = None
    num: int = 15
    range_SI: Optional[Tuple[float, float]] = None
    rounding: bool = False
    points: int = 250
    labels: bool = False


@dataclass(frozen=True)
class ProcessSet:
    """A process or cycle to draw: a line through some states, markers on others."""
    name: str
    line_states: Tuple[StatePoint, ...]
    marker_states: Tuple[StatePoint, ...] = ()
    line_style: Optional[LineStyle] = None
    marker_style: Optional[MarkerStyle] = None


def nice_values(values) -> np.ndarray:
    """Round values to as few significant digits as possible while keeping them distinct.

    Isoline labels look better with round numbers, but the spacing of the
    lines is not known in advance, so a fixed number of digits could merge
    neighbouring lines. This tries 1, 2, 3, ... significant digits until
    all values stay distinct.
    """
    values = np.unique(np.asarray(values, dtype=float))
    for digits in range(1, 12):
        rounded = np.array([float("{0:.{1}g}".format(v, digits)) for v in values])
        if len(np.unique(rounded)) == len(values):
            return rounded
    return values


class PropertyDiagram:
    """A thermodynamic property diagram for one fluid

    Parameters
    ----------
    fluid : str, CoolProp.AbstractState or Fluid
        For example "HEOS::R290".
    diagram_type : str
        Vertical axis first: "ph", "Ts", "hs", "ps", "prho", "Trho", "pT".
    units : str or UnitSystem
        "SI", "KSI", "EUR" or a custom UnitSystem.
    tp_limits : str, TpLimits or sequence
        The temperature and pressure region to cover, see
        :mod:`CoolPlot.thermo.limits`.
    theme : str or Theme, optional
        "default", "dark", "print", "classic" or a Theme; see docs/styling.md.
    cache : CurveCache, optional
        Share one cache between several diagrams of the same fluid.

    Examples
    --------
    >>> from CoolPlot import PropertyDiagram
    >>> from CoolPlot.render.mpl import MatplotlibRenderer
    >>> diagram = PropertyDiagram("HEOS::R290", "ph", units="EUR")
    >>> diagram.set_isolines("Q", num=11)
    >>> diagram.set_isolines("T", num=12)
    >>> renderer = MatplotlibRenderer()
    >>> renderer.sync(diagram.update_scene())   # first draw
    >>> diagram.units = "KSI"
    >>> renderer.sync(diagram.update_scene())   # no new property calls
    """

    def __init__(self, fluid, diagram_type="ph", units="EUR", tp_limits="DEF",
                 theme="default", cache: CurveCache = None):
        self._fluid = fluid if isinstance(fluid, Fluid) else Fluid(fluid)
        self._diagram = DiagramType.parse(diagram_type)
        self._units = get_unit_system(units)
        self._tp_limits = get_tp_limits(tp_limits)
        self._theme = get_theme(theme)
        self._style_overrides: Dict[str, dict] = {}
        self._isolines: Dict[str, IsolineSet] = {}
        self._processes: Dict[str, ProcessSet] = {}
        self._view: Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]] = (None, None)
        self._domain = None
        self.title = ""
        self.cache = cache if cache is not None else CurveCache()
        self.scene = Scene()

    # ------------------------------------------------------------------
    # Settings. Setters only store; update_scene does the work.
    # ------------------------------------------------------------------
    @property
    def fluid(self) -> Fluid:
        return self._fluid

    @fluid.setter
    def fluid(self, value):
        self._fluid = value if isinstance(value, Fluid) else Fluid(value)
        self._domain = None

    @property
    def diagram_type(self) -> DiagramType:
        return self._diagram

    @diagram_type.setter
    def diagram_type(self, value):
        self._diagram = DiagramType.parse(value)
        self._domain = None
        self._view = (None, None)

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self, value):
        new_units = get_unit_system(value)
        # The zoom window is stored in display units; carry it over.
        self._view = tuple(
            None if lim is None else tuple(new_units[key].from_SI(self._units[key].to_SI(lim)).tolist())
            for lim, key in zip(self._view, (self._diagram.x, self._diagram.y)))
        self._units = new_units

    @property
    def tp_limits(self):
        return self._tp_limits

    @tp_limits.setter
    def tp_limits(self, value):
        self._tp_limits = get_tp_limits(value)
        self._domain = None

    @property
    def theme(self) -> Theme:
        return self._theme

    @theme.setter
    def theme(self, value):
        self._theme = get_theme(value)

    def set_isoline_style(self, key: str, **changes):
        """Override the theme for one isoline family in this diagram.

        Accepts any LineStyle field, e.g. set_isoline_style("T",
        color="blue", width_pt=1.0). Call without changes to go back to
        the theme. Only the affected lines are restyled; nothing is
        recalculated.
        """
        key = quantity_key(key)
        if changes:
            LineStyle().with_(**changes)   # validate now, not at the next update
            self._style_overrides[key] = dict(self._style_overrides.get(key, {}), **changes)
        else:
            self._style_overrides.pop(key, None)

    def set_view(self, x_limits=None, y_limits=None):
        """Show only part of the diagram (zoom), in display units. None resets.

        This does not change the calculation domain and needs no property
        calculations.
        """
        self._view = (None if x_limits is None else tuple(x_limits),
                      None if y_limits is None else tuple(y_limits))

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------
    def set_isolines(self, key: str, values=None, num: int = None, range=None,
                     rounding: bool = False, points: int = 250, labels: bool = False):
        """Add or replace the family of isolines of one quantity.

        Parameters
        ----------
        key : str
            Quantity held constant: "T", "p", "h", "s", "rho", "u" or "Q".
        values : sequence, optional
            Explicit constant values in display units.
        num : int, optional
            Number of lines if no values are given. Default 11 for quality
            (steps of 0.1) and 15 otherwise.
        range : (min, max), optional
            Span for the ``num`` lines in display units. Default: the whole
            plotting region.
        rounding : bool
            Round automatically generated values for nicer labels.
        points : int
            Points per line.
        labels : bool
            Put a value label on each line.
        """
        key = quantity_key(key)
        if not self._diagram.supports(key):
            raise ValueError("Lines of constant '{0}' cannot be drawn in a {1} diagram.".format(
                key, self._diagram.name))
        unit = self._units[key]
        values_SI = None if values is None else tuple(float(v) for v in unit.to_SI(values).ravel())
        range_SI = None if range is None else tuple(sorted(float(v) for v in unit.to_SI(range)))
        if num is None:
            num = 11 if key == "Q" else 15
        self._isolines[key] = IsolineSet(key, values_SI, int(num), range_SI, rounding, int(points), labels)
        return key

    def set_default_isolines(self, num: int = None, **kwargs):
        """Isolines of every common quantity that makes sense in this diagram.

        Internal energy is left out to keep the chart readable; add it with
        set_isolines("u") if needed.
        """
        for key in self._diagram.supported_isolines():
            if key != "u":
                self.set_isolines(key, num=num, **kwargs)

    def remove_isolines(self, key: str):
        self._isolines.pop(quantity_key(key), None)

    def isoline_sets(self):
        return dict(self._isolines)

    def set_process(self, name: str, line_states: Sequence[StatePoint],
                    marker_states: Sequence[StatePoint] = (),
                    line_style: LineStyle = None, marker_style: MarkerStyle = None):
        """Add or replace a process or cycle, given as states in SI units.

        ``line_states`` are connected by a line, ``marker_states`` get a
        marker. Use :func:`CoolPlot.thermo.process_path` to fill in the
        states along a compression or heat exchange.
        """
        self._processes[name] = ProcessSet(name, tuple(line_states), tuple(marker_states),
                                           line_style, marker_style)

    def remove_process(self, name: str):
        self._processes.pop(name, None)

    # ------------------------------------------------------------------
    # Interaction helpers
    # ------------------------------------------------------------------
    def state_at(self, x: float, y: float) -> StatePoint:
        """The full state at a point given in display units, e.g. under the mouse."""
        x_SI = float(self._units[self._diagram.x].to_SI(x))
        y_SI = float(self._units[self._diagram.y].to_SI(y))
        return state_point(self._fluid, self._diagram.x, x_SI, self._diagram.y, y_SI)

    def to_display(self, key: str, value_SI):
        return self._units[key].from_SI(value_SI)

    # ------------------------------------------------------------------
    # Scene building
    # ------------------------------------------------------------------
    def domain_SI(self):
        """(tp_box, x_range_SI, y_range_SI) of the calculation domain, cached."""
        if self._domain is None:
            tp_box = self._tp_limits.resolve(self._fluid)
            x_range_SI, y_range_SI = axis_ranges_SI(self._fluid, self._diagram, tp_box)
            self._domain = (tp_box, x_range_SI, y_range_SI)
        return self._domain

    def update_scene(self) -> Scene:
        """Bring :attr:`scene` up to date with the settings and return it."""
        tp_box, x_range_SI, y_range_SI = self.domain_SI()
        axes = self._axes_spec(x_range_SI, y_range_SI)
        items = []
        for iso_set in self._isolines.values():
            items.extend(self._isoline_items(iso_set, tp_box, axes))
        for index, process in enumerate(self._processes.values()):
            items.extend(self._process_items(process, index))
        self.scene.replace_all(items, axes=axes)
        return self.scene

    def _axes_spec(self, x_range_SI, y_range_SI) -> AxesSpec:
        def label(key):
            q = get_quantity(key)
            return "{0} {1} / {2}".format(q.label, q.symbol, self._units[key].label)

        ux, uy = self._units[self._diagram.x], self._units[self._diagram.y]
        x_view, y_view = self._view
        x_limits = x_view or tuple(sorted(ux.from_SI(x_range_SI).tolist()))
        y_limits = y_view or tuple(sorted(uy.from_SI(y_range_SI).tolist()))
        return AxesSpec(x_label=label(self._diagram.x), y_label=label(self._diagram.y),
                        x_log=self._diagram.x_log, y_log=self._diagram.y_log,
                        x_limits=x_limits, y_limits=y_limits, title=self.title, style=self._theme.axes)

    def _isoline_values_SI(self, iso_set: IsolineSet, tp_box) -> np.ndarray:
        if iso_set.values_SI is not None:
            return np.asarray(iso_set.values_SI)
        lo, hi = iso_set.range_SI or property_range_SI(self._fluid, iso_set.key, tp_box)
        values = value_grid(iso_set.key, lo, hi, iso_set.num)
        if iso_set.rounding:
            # Round in display units, so that labels read 25 deg C, not 298.15 K
            unit = self._units[iso_set.key]
            values = unit.to_SI(nice_values(unit.from_SI(values)))
        return values

    def _isoline_look(self, key: str, value_SI: float, legends_given: set):
        """(style, role, legend text) of one isoline, from the theme.

        The first line of every family carries the legend entry for it.
        """
        if key == "Q":
            role = "saturation" if value_SI in (0.0, 1.0) else "quality"
            style = self._theme.saturation if role == "saturation" else self._theme.quality
            text = "Saturation" if role == "saturation" else "Vapour quality"
        else:
            role = "isoline"
            families = [k for k in self._diagram.supported_isolines() if k != "Q"]
            style = self._theme.isoline_style(key, families)
            text = get_quantity(key).label
        if key in self._style_overrides:
            style = style.with_(**self._style_overrides[key])
        legend_key = role if key == "Q" else key
        legend = None if legend_key in legends_given else text
        legends_given.add(legend_key)
        return style, role, legend

    def _isoline_items(self, iso_set: IsolineSet, tp_box, axes: AxesSpec):
        key = iso_set.key
        ux, uy = self._units[self._diagram.x], self._units[self._diagram.y]
        uk = self._units[key]
        items = []
        legends_given = set()
        for value_SI in self._isoline_values_SI(iso_set, tp_box):
            value_SI = float(value_SI)
            if key == "Q":
                # Quality lines do not depend on the T-p region
                cache_key = (self._fluid.model_key, self._diagram, key, value_SI, iso_set.points)
            else:
                cache_key = (self._fluid.model_key, self._diagram, key, value_SI,
                             tuple(tp_box), iso_set.points)
            curve = self.cache.get_or_compute(cache_key, lambda: compute_isoline(
                self._fluid, self._diagram, key, value_SI, tp_box, iso_set.points))
            if curve.n_valid < 2:
                warnings.warn("Skipping the line {0}={1} in {2}: CoolProp failed for {3} of {4} points.".format(
                    key, value_SI, self._fluid.name, curve.n_failed, len(curve.x)), UserWarning)
                continue
            is_saturation = key == "Q" and value_SI in (0.0, 1.0)
            style, role, legend = self._isoline_look(key, value_SI, legends_given)
            item_id = "iso/{0}/{1:.12g}".format(key, value_SI)
            x, y = ux.from_SI(curve.x), uy.from_SI(curve.y)
            items.append(Line(id=item_id, group="iso/" + key, role=role, legend=legend, x=x, y=y,
                              style=style, z_order=2.0 if is_saturation else 1.0))
            if iso_set.labels:
                label = self._isoline_label(item_id, key, float(uk.from_SI(value_SI)), x, y, axes)
                if label is not None:
                    items.append(label)
        return items

    def _isoline_label(self, line_id, key, value, x, y, axes: AxesSpec) -> Optional[Text]:
        """A label at the middle of the visible part of a line, aligned with it."""
        (x_lo, x_hi), (y_lo, y_hi) = axes.x_limits, axes.y_limits
        inside = np.flatnonzero(np.isfinite(x) & np.isfinite(y) &
                                (x >= x_lo) & (x <= x_hi) & (y >= y_lo) & (y <= y_hi))
        if len(inside) < 3:
            return None
        i = int(inside[len(inside) // 2])
        i0, i1 = max(i - 1, 0), min(i + 1, len(x) - 1)
        direction = (float(x[i1] - x[i0]), float(y[i1] - y[i0]))
        if not all(np.isfinite(direction)):
            direction = None
        q = get_quantity(key)
        text = "{0}={1:.4g} {2}".format(q.symbol, value, self._units[key].label)
        return Text(id=line_id + "/label", group="iso/" + key + "/label", role="isoline_label",
                    x=float(x[i]), y=float(y[i]),
                    text=text, direction=direction, style=self._theme.isoline_label, z_order=4.0)

    def _process_items(self, process: ProcessSet, index: int):
        ux, uy = self._units[self._diagram.x], self._units[self._diagram.y]
        kx, ky = self._diagram.x, self._diagram.y
        group = "process/" + process.name
        items = []
        if process.line_states:
            x = ux.from_SI([s[kx] for s in process.line_states])
            y = uy.from_SI([s[ky] for s in process.line_states])
            items.append(Line(id=group + "/line", group=group, role="process", legend=process.name,
                              x=x, y=y, style=process.line_style or self._theme.process_style(index),
                              z_order=5.0))
        if process.marker_states:
            x = ux.from_SI([s[kx] for s in process.marker_states])
            y = uy.from_SI([s[ky] for s in process.marker_states])
            items.append(Markers(id=group + "/points", group=group, role="state_points",
                                 legend=process.name, x=x, y=y,
                                 style=process.marker_style or self._theme.state_point_style(index),
                                 z_order=6.0))
        return items

    # ------------------------------------------------------------------
    # Convenience for scripts. Imports matplotlib only when called.
    # ------------------------------------------------------------------
    def draw(self, renderer=None):
        """Synchronise a renderer with the diagram; creates a MatplotlibRenderer if none is given."""
        if renderer is None:
            renderer = getattr(self, "_default_renderer", None)
            if renderer is None:
                from .render.mpl import MatplotlibRenderer
                renderer = self._default_renderer = MatplotlibRenderer()
        renderer.sync(self.update_scene())
        return renderer

    def show(self):
        self.draw().show()

    def savefig(self, path, **kwargs):
        self.draw().save(path, **kwargs)
