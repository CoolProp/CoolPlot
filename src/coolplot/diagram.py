# -*- coding: utf-8 -*-
"""Property diagrams of a CoolProp fluid.

:class:`PropertyDiagram` is a :class:`coolplot.Chart` made for a fluid:
the constructor takes the fluid, the diagram type (ph, Ts, ...) and the
temperature and pressure region; everything else (isolines, cycles,
units, styling, drawing) is what every chart offers. See
:mod:`coolplot.chart` for the pipeline behind :meth:`Chart.update_scene`.
"""
from __future__ import annotations

import warnings
from typing import Sequence

from CoolProp import AbstractState

from .chart import Chart
from .core.diagram_type import DiagramType
from .core.limits import get_tp_limits
from .core.state import StatePoint
from .core.units import get_unit_system
from .engine import CurveCache, Engine
from .spec import DiagramSpec, FluidSpec, ProcessSpec, get_settings
from .style.values import LineStyle, MarkerStyle
from .thermo.fluid import Fluid


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


class PropertyDiagram(Chart):
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
    engine, cache, background, on_ready, workers
        See :class:`coolplot.Chart`.

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

    kind = "fluid"

    def __init__(self, fluid, diagram_type="ph", units="EUR", tp_limits="DEF", theme=None,
                 settings=None, engine: Engine = None, cache: CurveCache = None, background: str = None,
                 on_ready=None, workers: int = None):
        settings = get_settings(settings)
        if theme is not None:
            settings = settings.with_(look=theme)
        spec = DiagramSpec(fluid=fluid_spec(fluid), diagram=DiagramType.parse(diagram_type),
                           units=get_unit_system(units), limits=get_tp_limits(tp_limits), settings=settings)
        Chart.__init__(self, spec, engine, cache, background, on_ready, workers)

    # ------------------------------------------------------------------
    # What only a fluid diagram has
    # ------------------------------------------------------------------
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
    def tp_limits(self):
        return self.spec.limits

    @tp_limits.setter
    def tp_limits(self, value):
        self.spec = self.spec.with_(limits=get_tp_limits(value))

    def set_default_isolines(self, num: int = None, **kwargs):
        """Isolines of every common quantity that makes sense in this diagram.

        Internal energy is left out to keep the chart readable; add it with
        set_isolines("u") if needed.
        """
        for key in self.spec.diagram.supported_isolines():
            if key != "u":
                self.set_isolines(key, num=num, **kwargs)

    def set_process(self, name: str, line_states: Sequence[StatePoint],
                    marker_states: Sequence[StatePoint] = (),
                    line_style: LineStyle = None, marker_style: MarkerStyle = None):
        """Add or replace a process or cycle, given as states in SI units.

        ``line_states`` are connected by a line, ``marker_states`` get a
        marker. Use :func:`coolplot.thermo.process_path` to fill in the
        states along a compression or heat exchange. :meth:`add_cycle`
        does the same from two properties per state and computes the
        paths itself.
        """
        self.spec = self.spec.with_process(ProcessSpec(name, tuple(line_states), tuple(marker_states),
                                                       line_style, marker_style))

    def remove_process(self, name: str):
        self.spec = self.spec.without_process(name)
