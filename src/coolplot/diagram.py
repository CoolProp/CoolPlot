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

from CoolProp import AbstractState

from .chart import Chart, check_fluid
from .core.diagram_type import DiagramType
from .core.limits import get_tp_limits
from .core.units import get_unit_system
from .engine import CurveCache, Engine
from .spec import DiagramSpec, FluidSpec, get_settings
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
        "SI", "KSI", "engineering" (deg C, bar, kJ), "IP" or a custom
        UnitSystem.
    tp_limits : str, TpLimits or sequence
        The temperature and pressure region to cover, see
        :mod:`coolplot.core.limits`.
    theme : str or Theme, optional
        "default", "dark", "print", "classic" or a Theme; see docs/how_to/themes.md.
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
    >>> diagram = PropertyDiagram("HEOS::R290", "ph", units="engineering")
    >>> diagram.set_lines("Q", num=11)
    >>> diagram.set_lines("T", num=12)
    >>> renderer = MatplotlibRenderer()
    >>> renderer.sync(diagram.update_scene())   # first draw
    >>> diagram.units = "KSI"
    >>> renderer.sync(diagram.update_scene())   # no new property calls
    """

    kind = "fluid"

    def __init__(self, fluid, diagram_type="ph", units="engineering", tp_limits="DEF", theme=None,
                 settings=None, engine: Engine = None, cache: CurveCache = None, background: str = None,
                 on_ready=None, workers: int = None):
        settings = get_settings(settings)
        if theme is not None:
            settings = settings.with_(look=theme)
        spec = DiagramSpec(fluid=fluid_spec(fluid), diagram=DiagramType.parse(diagram_type),
                           units=get_unit_system(units, stacklevel=3), limits=get_tp_limits(tp_limits),
                           settings=settings)
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
        check_fluid(self.engine, new)   # before anything changes: a bad name leaves the diagram as it was
        fixed = [c.name for c in self.spec.cycles if any(given.state is not None for _, given in c.states)]
        if fixed and new != self.spec.fluid:
            warnings.warn("Cycles {0} hold complete states of the previous fluid; they are drawn unchanged. "
                          "Add them again for the new fluid.".format(fixed), UserWarning, stacklevel=2)
        self.spec = self.spec.with_(fluid=new)

    @property
    def diagram_type(self) -> DiagramType:
        """The :class:`~coolplot.core.diagram_type.DiagramType` of the diagram, or a name such as "ph" to assign."""
        return self.spec.diagram

    @diagram_type.setter
    def diagram_type(self, value):
        diagram = DiagramType.parse(value)
        # Families that cannot be drawn in the new diagram are dropped
        kept = tuple(s for s in self.spec.isolines if diagram.supports(s.key))
        self.spec = self.spec.with_(diagram=diagram, isolines=kept, view_SI=(None, None))

    @property
    def tp_limits(self):
        """The temperature and pressure region the isolines cover.

        A preset name, a list of four SI values or a TpLimits.
        """
        return self.spec.limits

    @tp_limits.setter
    def tp_limits(self, value):
        self.spec = self.spec.with_(limits=get_tp_limits(value))
