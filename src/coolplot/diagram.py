# -*- coding: utf-8 -*-
"""The property diagram: the object applications work with.

:class:`PropertyDiagram` is a thin facade. It holds a
:class:`coolplot.spec.DiagramSpec` with every choice the user made and
replaces it with a new spec on each change. :meth:`update_scene` runs the
pipeline:

1. the :class:`coolplot.engine.Engine` resolves the calculation domain,
2. :func:`coolplot.engine.plan` lists the isolines the spec needs,
3. the engine returns their curves, computing only those it has not seen,
4. :func:`coolplot.compose.compose` turns the curves into scene items, and
5. the scene compares the items with the previous ones, so a renderer only
   redraws what really changed.

For example, switching from EUR to SI units reuses every cached curve and
updates the coordinates of all items, whereas changing the colour of the
isotherms reuses every curve and only restyles the isotherms. Moving one
state of a cycle only touches the two items of that cycle.

All values are stored in SI units. Values passed to the public methods are
in the current unit system of the diagram and converted on entry.
"""
from __future__ import annotations

import warnings
from typing import Sequence

import numpy as np
from CoolProp import AbstractState

from .compose import compose
from .core.cycle import Cycle, StateInput
from .core.diagram_type import DiagramType
from .core.limits import get_tp_limits
from .core.quantities import quantity_key
from .core.state import StatePoint
from .core.units import get_unit_system
from .engine import CurveCache, Engine, plan
from .scene import Scene
from .spec import CycleSpec, DiagramSpec, FluidSpec, IsolineSet, ProcessSpec, get_settings
from .style.theme import Theme, get_theme
from .style.values import LineStyle, MarkerStyle
from .thermo.fluid import Fluid
from .thermo.process import state_point


def _state_input(entry, units) -> StateInput:
    """A StateInput from a StatePoint, a StateInput or a dict in ``units``."""
    if isinstance(entry, StateInput):
        return entry
    if isinstance(entry, StatePoint):
        return StateInput(state=entry)
    if not isinstance(entry, dict):
        raise TypeError("A state is a StatePoint or a dict of properties, not {0}.".format(type(entry).__name__))
    entry = dict(entry)
    via = entry.pop("via", None)
    eta_is = float(entry.pop("eta_is", 1.0))
    props = tuple((quantity_key(k), float(units[k].to_SI(v))) for k, v in entry.items())
    return StateInput(props, via, eta_is)


def fluid_spec(fluid) -> FluidSpec:
    """A FluidSpec from a FluidSpec, a fluid string, a Fluid or a CoolProp.AbstractState.

    An AbstractState is copied (fluid, fractions and interaction
    parameters); later changes to it do not affect the diagram.
    """
    if isinstance(fluid, FluidSpec):
        return fluid
    if isinstance(fluid, str):
        return FluidSpec.parse(fluid)
    if isinstance(fluid, AbstractState):
        fluid = Fluid(fluid)
    if isinstance(fluid, Fluid):
        return FluidSpec(*fluid.model_key)
    raise TypeError("Expected a fluid string, a FluidSpec, a Fluid or a CoolProp.AbstractState.")


class PropertyDiagram:
    """A thermodynamic property diagram for one fluid

    Parameters
    ----------
    fluid : str, FluidSpec, CoolProp.AbstractState or Fluid
        For example "HEOS::R290" or "HEOS::R32[0.7]&R125[0.3]".
    diagram_type : str
        Vertical axis first: "ph", "Ts", "hs", "ps", "prho", "Trho", "pT".
    units : str or UnitSystem
        "SI", "KSI", "EUR" or a custom UnitSystem.
    tp_limits : str, TpLimits or sequence
        The temperature and pressure region to cover, see
        :mod:`coolplot.core.limits`.
    theme : str or Theme, optional
        "default", "dark", "print", "classic" or a Theme; see docs/styling.md.
        Replaces the theme of ``settings``.
    settings : str or Settings, optional
        "screen" (default), "print", "publication", "interactive" or a
        Settings value; see :mod:`coolplot.spec.settings`.
    engine : Engine, optional
        Share one engine (and its caches) between several diagrams.
    cache : CurveCache, optional
        Curve store for a new engine; ignored when ``engine`` is given.

    Examples
    --------
    >>> from coolplot import PropertyDiagram
    >>> from coolplot.render.mpl import MatplotlibRenderer
    >>> diagram = PropertyDiagram("HEOS::R290", "ph", units="EUR")
    >>> diagram.set_isolines("Q", num=11)
    >>> diagram.set_isolines("T", num=12)
    >>> renderer = MatplotlibRenderer()
    >>> renderer.sync(diagram.update_scene())   # first draw
    >>> diagram.units = "KSI"
    >>> renderer.sync(diagram.update_scene())   # no new property calls
    """

    def __init__(self, fluid, diagram_type="ph", units="EUR", tp_limits="DEF", theme=None,
                 settings=None, engine: Engine = None, cache: CurveCache = None):
        settings = get_settings(settings)
        if theme is not None:
            settings = settings.with_(look=theme)
        self.spec = DiagramSpec(fluid=fluid_spec(fluid), diagram=DiagramType.parse(diagram_type),
                                units=get_unit_system(units), limits=get_tp_limits(tp_limits),
                                settings=settings)
        self.engine = engine if engine is not None else Engine(cache)
        self.scene = Scene()
        self._default_renderer = None
        self._plot_size_pt = None

    # ------------------------------------------------------------------
    # Settings. Setters only replace the spec; update_scene does the work.
    # ------------------------------------------------------------------
    @property
    def cache(self) -> CurveCache:
        return self.engine.cache

    @property
    def fluid(self) -> Fluid:
        """The working Fluid of the engine, e.g. for :func:`coolplot.thermo.state_point`."""
        return self.engine.fluid(self.spec.fluid)

    @fluid.setter
    def fluid(self, value):
        new = fluid_spec(value)
        fixed = [c.name for c in self.spec.cycles if any(given.state is not None for _, given in c.states)]
        if fixed and new != self.spec.fluid:
            warnings.warn("Cycles {0} hold complete states of the previous fluid; they are drawn unchanged. "
                          "Add them again for the new fluid.".format(fixed), UserWarning, stacklevel=2)
        self.spec = self.spec.with_(fluid=new)

    @property
    def diagram_type(self) -> DiagramType:
        return self.spec.diagram

    @diagram_type.setter
    def diagram_type(self, value):
        diagram = DiagramType.parse(value)
        # Families that cannot be drawn in the new diagram are dropped
        kept = tuple(s for s in self.spec.isolines if diagram.supports(s.key))
        self.spec = self.spec.with_(diagram=diagram, isolines=kept, view_SI=(None, None))

    @property
    def units(self):
        return self.spec.units

    @units.setter
    def units(self, value):
        self.spec = self.spec.with_(units=get_unit_system(value))

    @property
    def tp_limits(self):
        return self.spec.limits

    @tp_limits.setter
    def tp_limits(self, value):
        self.spec = self.spec.with_(limits=get_tp_limits(value))

    @property
    def settings(self):
        return self.spec.settings

    @settings.setter
    def settings(self, value):
        self.spec = self.spec.with_(settings=get_settings(value))

    @property
    def theme(self) -> Theme:
        return self.spec.settings.look

    @theme.setter
    def theme(self, value):
        self.settings = self.spec.settings.with_(look=get_theme(value))

    @property
    def title(self) -> str:
        return self.spec.title

    @title.setter
    def title(self, value: str):
        self.spec = self.spec.with_(title=str(value))

    def set_isoline_style(self, key: str, **changes):
        """Override the theme for one isoline family in this diagram.

        Accepts any LineStyle field, e.g. set_isoline_style("T",
        color="blue", width_pt=1.0). Call without changes to go back to
        the theme. Only the affected lines are restyled; nothing is
        recalculated.
        """
        if changes:
            LineStyle().with_(**changes)   # validate now, not at the next update
        self.spec = self.spec.with_style_override(key, **changes)

    def set_view(self, x_limits=None, y_limits=None):
        """Show only part of the diagram (zoom), in display units. None resets.

        This does not change the calculation domain and needs no property
        calculations.
        """
        def to_SI(key, limits):
            if limits is None:
                return None
            values = [float(v) for v in self.spec.units[key].to_SI(limits).ravel()]
            if len(values) != 2 or not all(np.isfinite(values)):
                raise ValueError("A view needs two finite limits for '{0}', not {1}.".format(key, limits))
            return tuple(sorted(values))
        self.spec = self.spec.with_(view_SI=(to_SI(self.spec.diagram.x, x_limits),
                                             to_SI(self.spec.diagram.y, y_limits)))

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------
    def set_isolines(self, key: str, values=None, num: int = None, range=None,
                     rounding: bool = False, points: int = None, labels: bool = False):
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
            Use round values (such as 0, 10, 20 deg C or 1, 2, 5, 10 bar)
            instead of exactly ``num`` evenly spaced ones. The number of
            lines then comes as close to ``num`` as round values allow.
        points : int, optional
            Points per line; default from ``settings.calc``.
        labels : bool
            Put a value label on each line.
        """
        key = quantity_key(key)
        if not self.spec.diagram.supports(key):
            raise ValueError("Lines of constant '{0}' cannot be drawn in a {1} diagram.".format(
                key, self.spec.diagram.name))
        unit = self.spec.units[key]
        values_SI = None if values is None else tuple(float(v) for v in unit.to_SI(values).ravel())
        range_SI = None if range is None else tuple(float(v) for v in unit.to_SI(range))
        if key == "Q":
            for value in (values_SI or ()) + (range_SI or ()):
                if not 0.0 <= value <= 1.0:
                    raise ValueError("The vapour quality has to be between 0 and 1, not {0}.".format(value))
        if num is None:
            num = 11 if key == "Q" else 15
        self.spec = self.spec.with_isolines(IsolineSet(key, values_SI, num, range_SI, rounding, points, labels))
        return key

    def set_default_isolines(self, num: int = None, **kwargs):
        """Isolines of every common quantity that makes sense in this diagram.

        Internal energy is left out to keep the chart readable; add it with
        set_isolines("u") if needed.
        """
        for key in self.spec.diagram.supported_isolines():
            if key != "u":
                self.set_isolines(key, num=num, **kwargs)

    def remove_isolines(self, key: str):
        self.spec = self.spec.without_isolines(key)

    def isoline_sets(self):
        return {s.key: s for s in self.spec.isolines}

    def set_process(self, name: str, line_states: Sequence[StatePoint],
                    marker_states: Sequence[StatePoint] = (),
                    line_style: LineStyle = None, marker_style: MarkerStyle = None):
        """Add or replace a process or cycle, given as states in SI units.

        ``line_states`` are connected by a line, ``marker_states`` get a
        marker. Use :func:`coolplot.thermo.process_path` to fill in the
        states along a compression or heat exchange.
        """
        self.spec = self.spec.with_process(ProcessSpec(name, tuple(line_states), tuple(marker_states),
                                                       line_style, marker_style))

    def remove_process(self, name: str):
        self.spec = self.spec.without_process(name)

    def add_cycle(self, name, states=None, loops=None, paths=None, numbers: bool = True, units=None,
                  line_style: LineStyle = None, marker_style: MarkerStyle = None, steps: int = 20, **arrays):
        """Add or replace a cycle, drawn on top of the diagram.

        Parameters
        ----------
        name : str or Cycle
            Shown in the legend. A :class:`coolplot.core.cycle.Cycle` from
            one of the cycle models (:mod:`coolplot.thermo.cycles`) is drawn
            as it is, under its own name.
        states : list or dict
            The states, numbered from 1 in the order of a list, or by the
            keys of a dict. Each state is a StatePoint, or a dict with two
            properties in the diagram's units, e.g. ``{"p": 3.0, "T": 0.0}``,
            or one property and ``"via"``, e.g. ``{"p": 3.0, "via":
            "isenthalpic"}``, which takes the second property from the state
            before it in the cycle (see :data:`coolplot.core.cycle.VIA_KINDS`;
            "compression" and "expansion" also take ``"eta_is"``).
        loops : list of lists, optional
            Chains of state numbers, each drawn as one connected line, e.g.
            ``[[1, 2, 7, 8, 1], [3, 4, 5, 6, 3]]`` for two closed loops.
            Default: one closed loop through all states in order.
        paths : dict, optional
            ``{(from, to): kind}`` for connections that should not be drawn
            with "auto" (see :data:`coolplot.core.cycle.PATH_KINDS`).
        numbers : bool
            Show the state numbers.
        units : str or UnitSystem, optional
            Units of the given values; default the diagram's units.
        line_style, marker_style : optional
            Override the theme for this cycle.
        steps : int
            Segments per drawn path.
        **arrays
            Instead of ``states``: arrays of two properties, e.g.
            ``add_cycle("measured", p=[...], h=[...])``.

        Only this cycle is recalculated and redrawn when it changes.
        Returns the name.
        """
        cycle = name if isinstance(name, Cycle) else (states if isinstance(states, Cycle) else None)
        if cycle is not None:
            if cycle.fluid and Fluid(cycle.fluid).model_key != self.fluid.model_key:
                raise ValueError("Cycle '{0}' was computed for {1}, but this diagram shows {2}.".format(
                    cycle.name, cycle.fluid, self.spec.fluid))
            spec = CycleSpec.from_cycle(cycle, name=None if isinstance(name, Cycle) else name, loops=loops,
                                        paths=paths, numbers=numbers, line_style=line_style,
                                        marker_style=marker_style, steps=steps)
        else:
            unit_system = self.spec.units if units is None else get_unit_system(units)
            if arrays:
                if states is not None:
                    raise ValueError("Give the states either as 'states' or as arrays, not both.")
                if len(arrays) != 2:
                    raise ValueError("Give arrays of exactly two properties, not {0}.".format(sorted(arrays)))
                columns = {k: list(np.atleast_1d(v)) for k, v in arrays.items()}
                lengths = {len(v) for v in columns.values()}
                if len(lengths) != 1:
                    raise ValueError("The arrays {0} have different lengths.".format(sorted(arrays)))
                states = [dict(zip(columns, row)) for row in zip(*columns.values())]
            if states is None:
                raise ValueError("Give the states of cycle '{0}'.".format(name))
            items = states.items() if isinstance(states, dict) else enumerate(states, start=1)
            inputs = tuple((int(n), _state_input(entry, unit_system)) for n, entry in items)
            spec = CycleSpec(str(name), inputs, loops or (), paths or (), numbers, line_style, marker_style, steps)
        self.engine.cycle(self.spec, spec)   # compute now, so that errors show up here
        self.spec = self.spec.with_cycle(spec)
        return spec.name

    def remove_cycle(self, name: str):
        self.spec = self.spec.without_cycle(name)

    def cycle_states(self, name: str):
        """The states of a cycle in SI units, by state number."""
        cycle = next((c for c in self.spec.cycles if c.name == name), None)
        if cycle is None:
            raise KeyError("No cycle named {0!r}.".format(name))
        return dict(self.engine.cycle(self.spec, cycle)[0])

    # ------------------------------------------------------------------
    # Interaction helpers
    # ------------------------------------------------------------------
    def state_at(self, x: float, y: float) -> StatePoint:
        """The full state at a point given in display units, e.g. under the mouse."""
        diagram, units = self.spec.diagram, self.spec.units
        x_SI = float(units[diagram.x].to_SI(x))
        y_SI = float(units[diagram.y].to_SI(y))
        return state_point(self.fluid, diagram.x, x_SI, diagram.y, y_SI)

    def to_display(self, key: str, value_SI):
        return self.spec.units[key].from_SI(value_SI)

    # ------------------------------------------------------------------
    # Scene building
    # ------------------------------------------------------------------
    def update_scene(self, plot_size_pt=None) -> "Scene":
        """Bring :attr:`scene` up to date with the spec and return it.

        ``plot_size_pt`` is the (width, height) of the plot area in points,
        as ``renderer.plot_size_pt()`` reports it; labels are laid out for
        it. Without it the last reported size is used, or an estimate from
        ``settings.page``. Labels that are already placed keep their
        positions while those stay free.
        """
        if plot_size_pt is not None:
            self._plot_size_pt = tuple(float(v) for v in plot_size_pt)
        spec = self.spec
        domain = self.engine.domain(spec)
        curves = self.engine.curves(spec, domain, plan(spec, domain))
        previous = {item.id: item for item in self.scene if item.role == "isoline_label"}
        cycles = [self.engine.cycle(spec, c) for c in spec.cycles]
        items, axes = compose(spec, domain, curves, self._plot_size_pt, previous, cycles)
        self.scene.replace_all(items, axes=axes)
        return self.scene

    # ------------------------------------------------------------------
    # Convenience for scripts. Imports matplotlib only when called.
    # ------------------------------------------------------------------
    def draw(self, renderer=None):
        """Synchronise a renderer with the diagram; creates a MatplotlibRenderer if none is given.

        A renderer created here uses the canvas size of ``settings.page``.
        """
        if renderer is None:
            renderer = self._default_renderer
            if renderer is None:
                from .render.mpl import MatplotlibRenderer
                renderer = self._default_renderer = MatplotlibRenderer(figsize=self.spec.settings.page.size_in)
        renderer.sync(self.update_scene(renderer.plot_size_pt()))
        # The plot area can change once the scene is drawn (for example when
        # matplotlib fits the axis titles); lay out the labels again then.
        # Only labels change, nothing is recalculated.
        size = renderer.plot_size_pt()
        if size is not None and self._plot_size_pt is not None and any(
                abs(a - b) > 0.02 * b for a, b in zip(size, self._plot_size_pt)):
            renderer.sync(self.update_scene(size))
        return renderer

    def show(self):
        self.draw().show()

    def savefig(self, path, **kwargs):
        self.draw().save(path, **kwargs)
