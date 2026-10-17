# -*- coding: utf-8 -*-
"""The chart: the object applications work with.

:class:`Chart` is a thin facade over one :class:`coolplot.spec.DiagramSpec`
with every choice the user made, and replaces it with a new spec on each
change. :class:`coolplot.PropertyDiagram` and
:class:`coolplot.PsychrometricChart` are the two ways to make one: a
property diagram of a CoolProp fluid, or a psychrometric chart of humid
air. Everything after the constructor is the same for both.

:meth:`Chart.update_scene` runs the pipeline:

1. the :class:`coolplot.engine.Engine` resolves the calculation domain,
2. :func:`coolplot.engine.plan` lists the isolines the spec needs,
3. the engine returns their curves, computing only those it has not seen,
4. :func:`coolplot.compose.compose` turns the curves into scene items, and
5. the scene compares the items with the previous ones, so a renderer only
   redraws what really changed.

For example, switching from EUR to SI units reuses every cached curve and
updates the coordinates of all items, whereas changing the colour of the
isotherms reuses every curve and only restyles the isotherms. Moving one
state of a cycle only touches the items of that cycle.

All values are stored in SI units. Values passed to the public methods are
in the current unit system of the chart and converted on entry.
"""
from __future__ import annotations

import warnings
import weakref
from dataclasses import replace

import numpy as np

from .compose import compose
from .core.cycle import Cycle, StateInput
from .core.quantities import quantity_key
from .core.state import StatePoint
from .core.units import get_unit_system
from .engine import BackgroundEngine, CurveCache, Engine, plan
from .scene import Scene
from .spec import CycleSpec, DiagramSpec, IsolineSet, get_settings
from .style.theme import Theme, get_theme
from .style.values import LineStyle, MarkerStyle


def _known_key(name, inputs):
    """The quantity key for a name a state may be given by, else None."""
    try:
        key = quantity_key(name)
    except (KeyError, AttributeError, TypeError):   # unknown, or not even a string
        return None
    return key if key in inputs else None


def state_input(entry, units, provider) -> StateInput:
    """A StateInput from a StatePoint, a StateInput or a dict in ``units``.

    ``provider`` says which quantities a state may be given by
    (``provider.inputs``) and which a complete state has to hold
    (``provider.quantities``), so that a state of another kind of chart
    is refused here and not while drawing.
    """
    if isinstance(entry, StateInput):
        return entry
    if isinstance(entry, StatePoint):
        check_state(entry, provider)
        return StateInput(state=entry)
    if not isinstance(entry, dict):
        raise TypeError("A state is a StatePoint or a dict of properties, not {0}.".format(type(entry).__name__))
    entry = dict(entry)
    via = entry.pop("via", None)
    eta_is = float(entry.pop("eta_is", 1.0))
    keys = {name: _known_key(name, provider.inputs) for name in entry}
    unknown = [name for name, key in keys.items() if key is None]
    if unknown:
        raise ValueError("A state has unknown properties {0}, expected two of {1}.".format(
            unknown, list(provider.inputs)))
    props = tuple((keys[name], float(units[keys[name]].to_SI(v))) for name, v in entry.items())
    return StateInput(props, via, eta_is)


def check_state(state: StatePoint, provider):
    """Raise ValueError if a complete state lacks quantities of ``provider``."""
    missing = [k for k in provider.quantities if k not in state]
    if missing:
        raise ValueError("The state {0} is not a state of {1}: it lacks {2}.".format(state, provider.name, missing))


class Chart:
    """A chart built from a spec; see :class:`PropertyDiagram` and :class:`PsychrometricChart`

    Parameters
    ----------
    spec : DiagramSpec
        What the chart shows.
    engine : Engine, optional
        Share one engine (and its caches) between several charts.
    cache : CurveCache, optional
        Curve store for a new engine; ignored when ``engine`` is given.
    background : str, optional
        "threads" or "processes": compute curves in the background, see
        :mod:`coolplot.engine.background`. :meth:`update_scene` then never
        waits; it draws what is ready (coarse previews first) and
        ``on_ready(chart)`` is called when more is ready.
    on_ready : callable, optional
        With ``background``: called from a worker when curves are ready.
    workers : int, optional
        With ``background``: number of workers.
    """

    def __init__(self, spec: DiagramSpec, engine: Engine = None, cache: CurveCache = None, background: str = None,
                 on_ready=None, workers: int = None):
        self.spec = spec
        if engine is not None:
            if isinstance(engine, BackgroundEngine) and engine.claimed:
                raise ValueError("A BackgroundEngine works for one chart, it keeps only the latest plan. "
                                 "To share curves, share the cache: PropertyDiagram(..., background=..., "
                                 "cache=other.cache).")
            self.engine = engine
        elif background is not None:
            callback = (lambda _engine: on_ready(self)) if on_ready is not None else None
            self.engine = BackgroundEngine(background, workers, callback, cache)
        else:
            self.engine = Engine(cache)
        self.scene = Scene()
        self._default_renderer = None
        self._plot_size_pt = None
        if isinstance(self.engine, BackgroundEngine):
            # Claimed last, so a failing constructor leaves the engine free,
            # and released when this chart is garbage collected
            self.engine.claimed = True
            weakref.finalize(self, setattr, self.engine, "claimed", False)

    #: The chart kind a subclass is made for; None accepts every kind.
    kind = None

    @classmethod
    def from_spec(cls, spec: DiagramSpec, **engine_options) -> "Chart":
        """A chart for a saved spec, e.g. DiagramSpec.from_dict(json.load(f))."""
        if cls.kind is not None and spec.diagram.kind != cls.kind:
            raise ValueError("{0} shows {1} charts, not a {2} spec.".format(cls.__name__, cls.kind, spec.diagram.name))
        chart = cls.__new__(cls)
        Chart.__init__(chart, spec, **engine_options)
        return chart

    # ------------------------------------------------------------------
    # Settings. Setters only replace the spec; update_scene does the work.
    # ------------------------------------------------------------------
    @property
    def cache(self) -> CurveCache:
        return self.engine.cache

    # Background work -------------------------------------------------------
    @property
    def progress(self):
        """(curves ready, curves needed) after the last update_scene; always
        complete without a background engine."""
        if isinstance(self.engine, BackgroundEngine):
            return self.engine.progress
        n = sum(len(s.values_SI or ()) or s.num for s in self.spec.isolines)
        return n, n

    def wait(self, timeout: float = None) -> bool:
        """Block until background work is done (True), or until the timeout (False)."""
        if isinstance(self.engine, BackgroundEngine):
            return self.engine.wait(timeout)
        return True

    def refresh(self):
        """Make the engine forget its CoolProp states, after a change CoolProp does not report.

        Call it after ``CoolProp.CoolProp.set_reference_state``; changes made
        with ``set_config_*`` are noticed by themselves. The next update
        computes every line again."""
        self.engine.refresh()

    def close(self):
        """Stop background workers, if any."""
        if isinstance(self.engine, BackgroundEngine):
            self.engine.close()

    @property
    def fluid(self):
        """The property provider of the engine: a :class:`coolplot.thermo.Fluid`
        or a :class:`coolplot.thermo.humid_air.HumidAir`, e.g. for
        :func:`coolplot.thermo.state_point`."""
        return self.engine.fluid(self.spec.fluid)

    @property
    def diagram_type(self):
        return self.spec.diagram

    @property
    def units(self):
        return self.spec.units

    @units.setter
    def units(self, value):
        self.spec = self.spec.with_(units=get_unit_system(value))

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
        """Override the theme for one isoline family in this chart.

        Accepts any LineStyle field, e.g. set_isoline_style("T",
        color="blue", width_pt=1.0). Call without changes to go back to
        the theme. Only the affected lines are restyled; nothing is
        recalculated.
        """
        if changes:
            LineStyle().with_(**changes)   # validate now, not at the next update
        self.spec = self.spec.with_style_override(key, **changes)

    def set_view(self, x_limits=None, y_limits=None):
        """Show only part of the chart (zoom), in display units. None resets.

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
            Quantity held constant: "T", "p", "h", "s", "rho", "u" or "Q"
            in a property diagram; "RH", "Twb", "h" or "v" in a
            psychrometric chart.
        values : sequence, optional
            Explicit constant values in display units.
        num : int, optional
            Number of lines if no values are given. Default: the family's
            usual number (11 for quality and relative humidity, 15 for the
            other families of a property diagram).
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
        family = self.spec.diagram.family(key)
        if family is None:
            raise ValueError("Lines of constant '{0}' cannot be drawn in a {1} diagram.".format(
                key, self.spec.diagram.name))
        unit = self.spec.units[key]
        label = self.spec.diagram.quantity_label(key)
        values_SI = None if values is None else tuple(float(v) for v in unit.to_SI(values).ravel())
        range_SI = None if range is None else tuple(float(v) for v in unit.to_SI(range))
        family.check_values(values_SI or (), label)
        if range_SI is not None and family.bounds is not None:
            # A range may touch an excluded bound (0 to 100 % RH): the line without a value is left out
            if any(not family.bounds[0] <= v <= family.bounds[1] for v in range_SI):
                raise ValueError("The range of {0} has to lie between {1:g} and {2:g} (as SI values), not {3}.".format(
                    label, family.bounds[0], family.bounds[1], range_SI))
        if num is None:
            num = family.default_num
        self.spec = self.spec.with_isolines(IsolineSet(key, values_SI, num, range_SI, rounding, points, labels))
        return key

    def remove_isolines(self, key: str):
        self.spec = self.spec.without_isolines(key)

    def isoline_sets(self):
        return {s.key: s for s in self.spec.isolines}

    def add_cycle(self, name, states=None, loops=None, paths=None, numbers: bool = True, units=None,
                  line_style: LineStyle = None, marker_style: MarkerStyle = None, steps: int = 20, **arrays):
        """Add or replace a cycle, drawn on top of the chart.

        Parameters
        ----------
        name : str or Cycle
            Shown in the legend. A :class:`coolplot.core.cycle.Cycle` from
            one of the cycle models (:mod:`coolplot.thermo.cycles`) is drawn
            as it is, under its own name.
        states : list or dict
            The states, numbered from 1 in the order of a list, or by the
            keys of a dict. Each state is a StatePoint, or a dict with two
            properties in the chart's units, e.g. ``{"p": 3.0, "T": 0.0}``
            (or ``{"T": 30, "RH": 50}`` for humid air), or one property and
            ``"via"``, e.g. ``{"p": 3.0, "via": "isenthalpic"}``, which takes
            the second property from the state before it in the cycle (see
            :data:`coolplot.core.cycle.VIA_KINDS`; "compression" and
            "expansion" also take ``"eta_is"``).
        loops : list of lists, optional
            Chains of state numbers, each drawn as one connected line, e.g.
            ``[[1, 2, 7, 8, 1], [3, 4, 5, 6, 3]]`` for two closed loops.
            Default: one closed loop through all states in order.
        paths : dict, optional
            ``{(from, to): kind}`` for connections that should not be drawn
            with "auto" (see :data:`coolplot.core.cycle.PATH_KINDS`). Humid
            air draws every path straight.
        numbers : bool
            Show the state numbers.
        units : str or UnitSystem, optional
            Units of the given values; default the chart's units.
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
            if cycle.fluid and self._other_fluid(cycle.fluid):
                raise ValueError("Cycle '{0}' was computed for {1}, but this chart shows {2}.".format(
                    cycle.name, cycle.fluid, self.spec.fluid))
            for _, state in cycle.states:
                check_state(state, self.fluid)
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
            provider = self.fluid
            inputs = tuple((int(n), state_input(entry, unit_system, provider)) for n, entry in items)
            spec = CycleSpec(str(name), inputs, loops or (), paths or (), numbers, line_style, marker_style, steps)
        self.engine.cycle(self.spec, spec)   # compute now, so that errors show up here
        self.spec = self.spec.with_cycle(spec)
        return spec.name

    def _other_fluid(self, fluid_name: str) -> bool:
        """Whether a cycle computed for ``fluid_name`` belongs to another fluid."""
        from .thermo.fluid import Fluid
        if self.spec.fluid.kind != "fluid":
            return True
        return Fluid(fluid_name).model_key != self.fluid.model_key

    def move_cycle_state(self, name: str, number: int, x: float, y: float):
        """Put state ``number`` of a cycle at (x, y) in display units.

        The state is then given by the two axis quantities, for example
        h and p in a ph chart; states that follow it with "via" move along.
        A state that was itself given with "via" (say a compression with
        eta_is) becomes a fixed point and loses that relation. This is what
        dragging a state marker does. Raises ValueError, and leaves the
        cycle unchanged, if the cycle cannot be computed there.
        """
        if isinstance(number, bool) or int(number) != number:
            raise ValueError("State numbers are whole numbers, not {0!r}.".format(number))
        cycle = next((c for c in self.spec.cycles if c.name == name), None)
        if cycle is None:
            raise KeyError("No cycle named {0!r}.".format(name))
        diagram, units = self.spec.diagram, self.spec.units
        moved = StateInput(((diagram.x, float(units[diagram.x].to_SI(x))),
                            (diagram.y, float(units[diagram.y].to_SI(y)))))
        states = tuple((n, moved if n == int(number) else given) for n, given in cycle.states)
        if all(n != int(number) for n, _ in cycle.states):
            raise KeyError("Cycle {0!r} has no state {1}.".format(name, number))
        new = replace(cycle, states=states)
        self.engine.cycle(self.spec, new)   # raises if it cannot be computed; spec unchanged
        self.spec = self.spec.with_cycle(new)

    def remove_cycle(self, name: str):
        self.spec = self.spec.without_cycle(name)

    def cycle_states(self, name: str):
        """The states of a cycle in SI units, by state number in ascending order."""
        cycle = next((c for c in self.spec.cycles if c.name == name), None)
        if cycle is None:
            raise KeyError("No cycle named {0!r}.".format(name))
        states = self.engine.cycle(self.spec, cycle)[0]
        return {n: states[n] for n in sorted(states)}

    # ------------------------------------------------------------------
    # Interaction helpers
    # ------------------------------------------------------------------
    def state_at(self, x: float, y: float) -> StatePoint:
        """The full state at a point given in display units, e.g. under the mouse."""
        diagram, units = self.spec.diagram, self.spec.units
        x_SI = float(units[diagram.x].to_SI(x))
        y_SI = float(units[diagram.y].to_SI(y))
        return self.fluid.state_point(diagram.x, x_SI, diagram.y, y_SI)

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
        """Synchronise a renderer with the chart; creates a MatplotlibRenderer if none is given.

        A renderer created here uses the canvas size of ``settings.page``.
        """
        # Scripts want the complete picture: let background work finish,
        # previews first, then the final curves they make room for.
        if isinstance(self.engine, BackgroundEngine):
            last = None
            for _ in range(10):
                self.update_scene()
                ready, needed = self.engine.progress
                if not self.engine.busy and ready >= needed:   # a failed line may still be due a retry
                    break
                if self.engine.finished_jobs == last:   # the last wait finished no job at all
                    warnings.warn("Background work makes no progress, the drawing may be incomplete.",
                                  UserWarning, stacklevel=2)
                    break
                last = self.engine.finished_jobs
                self.wait()
            else:
                warnings.warn("Background work did not finish, the drawing may be incomplete (is the cache "
                              "smaller than the number of lines?).", UserWarning, stacklevel=2)
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
