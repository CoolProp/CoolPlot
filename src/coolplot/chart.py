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

For example, switching from engineering to SI units reuses every cached curve and
updates the coordinates of all items, whereas changing the colour of the
isotherms reuses every curve and only restyles the isotherms. Moving one
state of a cycle only touches the items of that cycle.

All values are stored in SI units. Values passed to the public methods are
in the current unit system of the chart, or in the system named by
``units=``, and converted on entry. Errors about states that cannot be
computed (:class:`coolplot.core.errors.PropertyError`) are written in
the chart's units too.

The verbs of a chart are ``set_lines``, ``remove_lines``,
``set_line_style``, ``add_cycle``, ``remove_cycle``, ``set_view``,
``update_scene``, ``draw`` and ``save``; the older names still work and
warn (see the CHANGELOG for 0.5).
"""
from __future__ import annotations

import inspect
import warnings
import weakref
from dataclasses import replace

import numpy as np

from .compose import compose
from .core.cycle import Cycle, StateInput
from .core.errors import PropertyError
from .core.quantities import quantity_key
from .core.state import StatePoint
from .core.units import get_unit_system
from .engine import BackgroundEngine, CurveCache, Engine, plan
from .scene import Scene
from .spec import CycleSpec, DiagramSpec, IsolineSet, SaturationAnchor, get_settings
from .spec.diagram import ANCHOR_KEYS
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
        return StateInput(state=check_state(entry, provider))
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


def check_fluid(engine: Engine, fluid_spec):
    """Build the property provider of ``fluid_spec`` on ``engine`` now, so
    that a fluid CoolProp does not know fails with a clear message."""
    try:
        return engine.fluid(fluid_spec)
    except ValueError as e:
        raise ValueError("CoolProp cannot make the fluid '{0}': {1}".format(fluid_spec, e)) from None


def _states_from_arrays(states, arrays: dict):
    """Rows of two property arrays as a list of dicts, one state each."""
    if states is not None:
        raise ValueError("Give the states either as 'states' or as arrays, not both.")
    if len(arrays) != 2:
        raise ValueError("Give arrays of exactly two properties, not {0}.".format(sorted(arrays)))
    columns = {k: list(np.atleast_1d(v)) for k, v in arrays.items()}
    if len({len(v) for v in columns.values()}) != 1:
        raise ValueError("The arrays {0} have different lengths.".format(sorted(arrays)))
    return [dict(zip(columns, row)) for row in zip(*columns.values())]


def _default_loops(inputs, closed: bool):
    """No loops (CycleSpec closes the chain itself), or one open chain through the states in order."""
    if closed or len(inputs) < 2:
        return ()
    return [sorted(n for n, _ in inputs)]


def _checked_range(family, label: str, range_SI):
    """A range for ``num`` lines; it may touch an excluded bound (0 to 100 % RH), the
    line without a value is simply left out."""
    if family.bounds is not None and any(not family.bounds[0] <= v <= family.bounds[1] for v in range_SI):
        raise ValueError("The range of {0} has to lie between {1:g} and {2:g} (as SI values), not {3}.".format(
            label, family.bounds[0], family.bounds[1], range_SI))
    return range_SI


def check_state(state: StatePoint, provider) -> StatePoint:
    """The complete state, or ValueError if it does not belong to ``provider``.

    A fluid state saved before 0.7 lacks the specific volume; it is
    filled in from the density.
    """
    if "v" not in state and "rho" in state and provider.kind == "fluid" and state.rho > 0.0:
        state = StatePoint(v=1.0 / state.rho, **state.to_dict())
    missing = [k for k in provider.quantities if k not in state]
    if missing:
        raise ValueError("The state {0} is not a state of {1}: it lacks {2}.".format(state, provider.name, missing))
    p_Pa = getattr(provider, "p_Pa", None)   # humid air lives at one total pressure
    if p_Pa is not None and abs(state.p - p_Pa) > 1e-6 * p_Pa:
        raise ValueError("The state {0} is at {1:.6g} Pa, but the chart shows {2}.".format(
            state, state.p, provider.name))
    return state


#: Methods of every chart removed in 1.0 (deprecated since 0.5), with what to use instead.
#: PropertyDiagram and PsychrometricChart add their own (``_removed_names``).
REMOVED_NAMES = {
    "set_isolines": "use set_lines",
    "set_default_isolines": "use set_default_lines",
    "remove_isolines": "use remove_lines",
    "isoline_sets": "use line_sets",
    "set_isoline_style": "use set_line_style",
    "savefig": "use save",
}


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
        owned = engine is None
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
        try:
            check_fluid(self.engine, spec.fluid)   # a misspelt fluid fails here, not at the first draw
        except ValueError:
            if owned:
                self.close()
            raise
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
        """The curve cache of the engine, shared by charts that share the engine."""
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
        """The :class:`~coolplot.core.diagram_type.DiagramType` of the chart (its two axes)."""
        return self.spec.diagram

    @property
    def units(self):
        """The unit system of the chart: a name ("SI", "KSI", "engineering", "IP") or a UnitSystem."""
        return self.spec.units

    @units.setter
    def units(self, value):
        self.spec = self.spec.with_(units=get_unit_system(value, stacklevel=3))

    @property
    def settings(self):
        """The :class:`~coolplot.spec.settings.Settings` of the chart, or a preset name to assign."""
        return self.spec.settings

    @settings.setter
    def settings(self, value):
        self.spec = self.spec.with_(settings=get_settings(value))

    @property
    def theme(self) -> Theme:
        """The :class:`~coolplot.style.theme.Theme` of the chart, or a theme name to assign."""
        return self.spec.settings.look

    @theme.setter
    def theme(self, value):
        self.settings = self.spec.settings.with_(look=get_theme(value))

    @property
    def title(self) -> str:
        """The title shown above the chart."""
        return self.spec.title

    @title.setter
    def title(self, value: str):
        self.spec = self.spec.with_(title=str(value))

    def set_line_style(self, key: str, **changes):
        """Override the theme for one family of lines in this chart.

        Accepts any LineStyle field, e.g. set_line_style("T",
        color="blue", width_pt=1.0). Call without changes to go back to
        the theme. Only the affected lines are restyled; nothing is
        recalculated.
        """
        if changes:
            LineStyle().with_(**changes)   # validate now, not at the next update
        self.spec = self.spec.with_style_override(key, **changes)

    def set_view(self, x_limits=None, y_limits=None, units=None):
        """Show only part of the chart (zoom). None resets.

        Limits are in the chart's units, or in ``units`` if given. This
        does not change the calculation domain and needs no property
        calculations.
        """
        unit_system = self._units(units)

        def to_SI(key, limits):
            if limits is None:
                return None
            values = [float(v) for v in unit_system[key].to_SI(limits).ravel()]
            if len(values) != 2 or not all(np.isfinite(values)):
                raise ValueError("A view needs two finite limits for '{0}', not {1}.".format(key, limits))
            return tuple(sorted(values))
        self.spec = self.spec.with_(view_SI=(to_SI(self.spec.diagram.x, x_limits),
                                             to_SI(self.spec.diagram.y, y_limits)))

    def _units(self, units):
        """The unit system of a call: the chart's, or the one named by ``units``."""
        return self.spec.units if units is None else get_unit_system(units, stacklevel=4)

    def _in_units(self, error: PropertyError):
        """A PropertyError of the thermo layer, written in the chart's units."""
        return error.with_units(self.spec.units)

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------
    def set_lines(self, key: str, values=None, num: int = None, range=None, rounding: bool = None,
                  labels: bool = None, points: int = None, units=None, at_saturation=None):
        """Add or replace the family of lines of constant ``key``.

        Parameters
        ----------
        key : str
            Quantity held constant: "T", "p", "h", "s", "rho", "u" or "Q"
            in a property diagram; "RH", "Twb", "h" or "v" in a
            psychrometric chart.
        values : sequence, optional
            Explicit constant values, in the chart's units or in ``units``.
        num : int, optional
            Number of lines if no values are given. Default: the family's
            usual number (11 for quality and relative humidity, 15 for the
            other families of a property diagram).
        range : (min, max), optional
            Span for the ``num`` lines, in the same units as ``values``.
            Default: the whole plotting region.
        rounding : bool, optional
            Use round values (such as 0, 10, 20 deg C or 1, 2, 5, 10 bar)
            instead of exactly ``num`` evenly spaced ones. The number of
            lines then comes as close to ``num`` as round values allow.
            Default: off in a property diagram, on in a psychrometric
            chart.
        labels : bool, optional
            Put a value label on each line. Default: off in a property
            diagram, on in a psychrometric chart.
        points : int, optional
            Points per line; default from ``settings.calc``.
        units : str or UnitSystem, optional
            Units of ``values``, ``range`` and ``at_saturation``; default the
            chart's units.
        at_saturation : dict, optional
            Place the lines through saturation states at even steps instead
            of giving values: ``{"T": 10}`` puts a line through the saturated
            vapour every 10 K of saturation temperature (in deg C charts at
            0, 10, 20 deg C), ``{"p": 2}`` every 2 bar of saturation
            pressure. ``"Q": 0`` uses the saturated liquid (the bubble point
            of a blend) instead of the vapour (the dew point), and
            ``"range": (lo, hi)`` limits the saturation temperatures or
            pressures. Steps and range are in ``units``. The labels show the
            saturation state ("T_sat=0 deg C"); ``"label": "value"`` shows
            the lines' own values instead. Charts of a fluid only.

        Examples
        --------
        Isentropes through the saturated vapour every 10 K, as compressor
        lines read off at round evaporating temperatures:

        >>> diagram.set_lines("s", at_saturation={"T": 10}, labels=True)   # doctest: +SKIP
        """
        key = quantity_key(key)
        family = self._family(key)
        defaults = self.spec.diagram.line_defaults
        rounding = defaults["rounding"] if rounding is None else bool(rounding)
        labels = defaults["labels"] if labels is None else bool(labels)
        unit = self._units(units)[key]
        label = self.spec.diagram.quantity_label(key)
        values_SI = None if values is None else tuple(float(v) for v in unit.to_SI(values).ravel())
        range_SI = None if range is None else tuple(float(v) for v in unit.to_SI(range))
        family.check_values(values_SI or (), label)
        if range_SI is not None:
            _checked_range(family, label, range_SI)
        if num is None:
            num = family.default_num
        anchor = None
        if at_saturation is not None:
            if values is not None or range is not None:
                raise ValueError("Give the lines either values or a range, or at_saturation, not both; a range "
                                 "of saturation states goes into at_saturation as 'range'.")
            anchor = self._saturation_anchor(at_saturation, units)
        spec = self.spec.with_isolines(IsolineSet(key, values_SI, num, range_SI, rounding, points, labels, anchor))
        if anchor is not None:
            # Place the lines now, so a step that is too small or a fluid
            # without a saturation curve is reported here, not at the next draw
            self.engine.domain(spec)
        self.spec = spec
        return key

    def _saturation_anchor(self, at_saturation, units) -> SaturationAnchor:
        """A SaturationAnchor from set_lines(at_saturation=...), converted from ``units`` to SI."""
        if isinstance(at_saturation, SaturationAnchor):
            return at_saturation
        given = dict(at_saturation)
        span = given.pop("range", None)
        label = given.pop("label", "saturation")
        Q = 1.0
        for name in list(given):   # the quality may be written Q or x, as the labels write it
            if name in ("Q", "x", "q"):
                Q = float(given.pop(name))
        if len(given) != 1:
            raise ValueError("at_saturation takes one step, by saturation temperature or pressure, e.g. "
                             "{{'T': 10}} or {{'p': 2, 'Q': 0}}, not {0}.".format(at_saturation))
        (by, step), = given.items()
        by = quantity_key(by)
        if by not in ANCHOR_KEYS:
            raise ValueError("Lines are placed by saturation temperature 'T' or pressure 'p', not '{0}'.".format(by))
        unit = self._units(units)[by]
        step_SI = float(step) / abs(unit.scale)   # a difference: the scale only, no offset
        span_SI = None if span is None else tuple(float(v) for v in unit.to_SI(span))
        return SaturationAnchor(by, step_SI, Q, span_SI, label)

    def _family(self, key: str):
        """The line family of a quantity in this chart, or ValueError."""
        family = self.spec.diagram.family(key)
        if family is None:
            raise ValueError("Lines of constant '{0}' cannot be drawn in a {1} diagram.".format(
                key, self.spec.diagram.name))
        return family

    def set_default_lines(self, num: int = None, **kwargs):
        """Lines of every family that makes sense in this chart.

        In a property diagram the internal energy is left out to keep the
        chart readable; add it with set_lines("u") if needed. ``kwargs``
        go to :meth:`set_lines`.
        """
        for key in self.spec.diagram.supported_isolines():
            if key != "u":
                self.set_lines(key, num=num, **kwargs)

    def remove_lines(self, key: str):
        """Remove the family of lines of constant ``key``; nothing happens if there is none."""
        self.spec = self.spec.without_isolines(key)

    def line_sets(self):
        """The families of lines by quantity key, as :class:`coolplot.spec.IsolineSet` values."""
        return {s.key: s for s in self.spec.isolines}

    # Names removed in 1.0 for this kind of chart, see REMOVED_NAMES
    _removed_names = REMOVED_NAMES

    def __getattr__(self, name):
        # Only called when normal lookup fails: a name removed in 1.0 gets a
        # message that says what to write instead (docs/upgrade.md).
        # Python also lands here when a property's getter raises
        # AttributeError itself; run the getter again so that its own error,
        # not a misleading "no attribute", reaches the user.
        found = inspect.getattr_static(type(self), name, None)
        if isinstance(found, property):
            return found.__get__(self, type(self))
        replacement = type(self)._removed_names.get(name)
        if replacement is not None:
            raise AttributeError("{0}.{1}() was removed in CoolPlot 1.0; {2} (see the upgrade guide).".format(
                type(self).__name__, name, replacement))
        raise AttributeError("'{0}' object has no attribute '{1}'".format(type(self).__name__, name))

    def add_cycle(self, name, states=None, loops=None, paths=None, numbers: bool = True, units=None,
                  line_style: LineStyle = None, marker_style: MarkerStyle = None, steps: int = 20,
                  closed: bool = True, **arrays):
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
            Default: one loop through all states in order, closed unless
            ``closed=False`` (an open process such as heating, cooling and
            reheating of air).
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
        closed : bool
            Whether the default loop returns to the first state.
        **arrays
            Instead of ``states``: arrays of two properties, e.g.
            ``add_cycle("measured", p=[...], h=[...])``.

        Only this cycle is recalculated and redrawn when it changes.
        Raises :class:`coolplot.core.errors.PropertyError`, in the chart's
        units, if a state cannot be computed. Returns the name.
        """
        cycle = name if isinstance(name, Cycle) else (states if isinstance(states, Cycle) else None)
        if cycle is not None:
            spec = self._spec_from_model(cycle, None if isinstance(name, Cycle) else name, loops, paths, numbers,
                                         line_style, marker_style, steps)
        else:
            unit_system = self._units(units)
            inputs = self._state_inputs(_states_from_arrays(states, arrays) if arrays else states, name, unit_system)
            spec = CycleSpec(str(name), inputs, loops or _default_loops(inputs, closed), paths or (), numbers,
                             line_style, marker_style, steps)
        self._compute_cycle(spec)   # compute now, so that errors show up here
        self.spec = self.spec.with_cycle(spec)
        return spec.name

    def _spec_from_model(self, cycle: Cycle, name, loops, paths, numbers, line_style, marker_style, steps):
        """A CycleSpec for a computed Cycle, after checking that it belongs to this chart's fluid."""
        if cycle.fluid and self._other_fluid(cycle.fluid):
            raise ValueError("Cycle '{0}' was computed for {1}, but this chart shows {2}.".format(
                cycle.name, cycle.fluid, self.spec.fluid))
        states = tuple((n, check_state(state, self.fluid)) for n, state in cycle.states)
        cycle = replace(cycle, states=states)   # with v filled in for a cycle computed before 0.7
        return CycleSpec.from_cycle(cycle, name=name, loops=loops, paths=paths, numbers=numbers,
                                    line_style=line_style, marker_style=marker_style, steps=steps)

    def _state_inputs(self, states, name, unit_system):
        """(number, StateInput) pairs from a list (numbered from 1) or a dict of given states."""
        if states is None:
            raise ValueError("Give the states of cycle '{0}'.".format(name))
        items = states.items() if isinstance(states, dict) else enumerate(states, start=1)
        provider = self.fluid
        return tuple((int(n), state_input(entry, unit_system, provider)) for n, entry in items)

    def _compute_cycle(self, cycle: CycleSpec):
        try:
            return self.engine.cycle(self.spec, cycle)
        except PropertyError as e:
            where = "{0} '{1}'".format(e.where, cycle.name) if e.where else "Cycle '{0}'".format(cycle.name)
            raise self._in_units(e).with_where(where) from None

    def _other_fluid(self, fluid_name: str) -> bool:
        """Whether a cycle computed for ``fluid_name`` belongs to another fluid."""
        from .thermo.fluid import Fluid
        if self.spec.fluid.kind != "fluid":
            return True
        return Fluid(fluid_name).model_key != self.fluid.model_key

    def move_cycle_state(self, name: str, number: int, x: float, y: float, units=None):
        """Put state ``number`` of a cycle at (x, y), in the chart's units or in ``units``.

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
        diagram, units = self.spec.diagram, self._units(units)
        moved = StateInput(((diagram.x, float(units[diagram.x].to_SI(x))),
                            (diagram.y, float(units[diagram.y].to_SI(y)))))
        states = tuple((n, moved if n == int(number) else given) for n, given in cycle.states)
        if all(n != int(number) for n, _ in cycle.states):
            raise KeyError("Cycle {0!r} has no state {1}.".format(name, number))
        new = replace(cycle, states=states)
        self._compute_cycle(new)   # raises if it cannot be computed; spec unchanged
        self.spec = self.spec.with_cycle(new)

    def remove_cycle(self, name: str):
        """Remove the cycle called ``name``; nothing happens if there is none."""
        self.spec = self.spec.without_cycle(name)

    def cycle_states(self, name: str, units=None):
        """The states of a cycle by state number in ascending order.

        StatePoints in SI units, or with ``units`` dicts of values in that
        unit system (``cycle_states("hp", units="engineering")[2]["T"]``
        is in deg C).
        """
        cycle = next((c for c in self.spec.cycles if c.name == name), None)
        if cycle is None:
            raise KeyError("No cycle named {0!r}.".format(name))
        states = self._compute_cycle(cycle)[0]
        if units is not None:
            return {n: states[n].in_units(units) for n in sorted(states)}
        return {n: states[n] for n in sorted(states)}

    # ------------------------------------------------------------------
    # Interaction helpers
    # ------------------------------------------------------------------
    def state_at(self, x: float, y: float, units=None) -> StatePoint:
        """The full state (SI units) at a point given in the chart's units or
        in ``units``, e.g. under the mouse."""
        diagram, unit_system = self.spec.diagram, self._units(units)
        x_SI = float(unit_system[diagram.x].to_SI(x))
        y_SI = float(unit_system[diagram.y].to_SI(y))
        try:
            return self.fluid.state_point(diagram.x, x_SI, diagram.y, y_SI)
        except PropertyError as e:
            raise self._in_units(e) from None

    def to_display(self, key: str, value_SI):
        """Convert an SI value of quantity ``key`` to the chart's units."""
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
        if isinstance(self.engine, BackgroundEngine):
            self._finish_background_work()
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

    def _finish_background_work(self):
        """Let background work finish before a script draws: previews first,
        then the final curves they make room for. Warns, instead of waiting
        for ever, when nothing finishes any more."""
        last = None
        for _ in range(10):
            self.update_scene()
            ready, needed = self.engine.progress
            if not self.engine.busy and ready >= needed:   # a failed line may still be due a retry
                return
            if self.engine.finished_jobs == last:   # the last wait finished no job at all
                warnings.warn("Background work makes no progress, the drawing may be incomplete.",
                              UserWarning, stacklevel=3)
                return
            last = self.engine.finished_jobs
            self.wait()
        warnings.warn("Background work did not finish, the drawing may be incomplete (is the cache "
                      "smaller than the number of lines?).", UserWarning, stacklevel=3)

    def show(self):
        """Draw the chart with matplotlib and show the window."""
        self.draw().show()

    def save(self, path, **kwargs):
        """Draw and write the chart to a file, choosing the writer by the extension.

        ``.svg`` is written by the SVG writer and ``.html`` by the web
        renderer (a static page), neither of which needs matplotlib;
        every other extension (PNG, PDF, EPS, ...) goes through matplotlib,
        with ``kwargs`` such as ``dpi`` or ``pdf_fonts`` passed on.
        """
        extension = str(path).rsplit(".", 1)[-1].lower() if "." in str(path) else ""
        if extension == "svg":
            from .render.svg import SvgRenderer
            self.draw(SvgRenderer(**kwargs)).save(path)
        elif extension in ("html", "htm"):
            from .render.web import WebRenderer
            self.draw(WebRenderer(**kwargs)).save(path)
        else:
            self.draw().save(path, **kwargs)
