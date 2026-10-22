# -*- coding: utf-8 -*-
"""The public API as a type checker sees it from an application.

tests/test_typing.py runs mypy in strict mode over this file, the way a
project that installed CoolPlot would check its own code. The package is
found as an installed package, so this also checks that it carries its
``py.typed`` marker: without it mypy would see no types at all.

``assert_type(value, T)`` fails the check unless mypy infers exactly T.
The lines at the end are mistakes that mypy has to find: each carries a
``# type: ignore[code]`` comment, and a comment that suppresses nothing
fails the check (``warn_unused_ignores``).

The file is only read by mypy, never run; it needs no CoolProp states.
"""
from typing import Dict, Tuple, assert_type

import numpy as np

import coolplot
from coolplot import (Chart, Cycle, PropertyDiagram, PsychrometricChart, Settings, StatePoint, Theme, UnitSystem,
                      save_pdf)
from coolplot.render.mpl import MatplotlibRenderer
from coolplot.render.svg import SvgRenderer
from coolplot.thermo.cycles import simple_compression


def property_diagram() -> None:
    diagram = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP", theme="print")
    assert_type(diagram, PropertyDiagram)
    assert_type(PropertyDiagram("R290", "Ts", tp_limits=[200.0, 400.0, 1e5, 4e6]), PropertyDiagram)

    # Lines: values as a list, a tuple or a numpy array; the key comes back
    assert_type(diagram.set_lines("T", values=[-20.0, 0.0, 20.0], labels=True), str)
    assert_type(diagram.set_lines("p", values=np.array([1.0, 5.0, 20.0])), str)
    assert_type(diagram.set_lines("s", at_saturation={"T": 10}, range=None), str)
    diagram.set_default_lines(num=7)
    diagram.set_line_style("T", color="blue", width_pt=1.0)
    diagram.set_line_style("saturation", casing_width_pt=0)
    diagram.set_view(x_limits=(200.0, 700.0), y_limits=None)
    diagram.remove_lines("u")

    # States and cycles
    state = diagram.state({"T": 0.0, "Q": 1.0})
    assert_type(state, StatePoint)
    assert_type(state.h, float)
    assert_type(state["T"], float)
    assert_type(diagram.state_at(400.0, 5.0, units="engineering"), StatePoint)
    cycle = simple_compression(diagram.fluid, T_evap_C=0.0, T_cond_C=40.0)
    assert_type(cycle, Cycle)
    assert_type(diagram.add_cycle(cycle), str)
    assert_type(diagram.add_cycle("Heat pump", [{"p": 3.0, "T": 5.0},
                                                {"p": 15.0, "via": "compression", "eta_is": 0.7}],
                                  paths={(1, 2): "polytropic"}, labels={2: "discharge"}), str)
    assert_type(diagram.add_cycle("Measured", p=[3.0, 15.0], h=np.array([400.0, 450.0])), str)
    assert_type(diagram.cycle_states("Heat pump"), Dict[int, StatePoint])
    assert_type(diagram.cycle_states("Heat pump", units="SI"), Dict[int, Dict[str, float]])
    diagram.move_cycle_state("Heat pump", 2, 450.0, 15.0)
    diagram.remove_cycle("Measured")

    # Settings and properties
    diagram.units = "SI"
    assert_type(diagram.units, UnitSystem)
    diagram.settings = "paper"
    assert_type(diagram.settings, Settings)
    diagram.theme = "dark"
    assert_type(diagram.theme, Theme)
    diagram.title = "R290"
    diagram.diagram_type = "Ts"
    assert_type(diagram.progress, Tuple[int, int])
    assert_type(diagram.wait(timeout=1.0), bool)
    assert_type(diagram.uncached_curves(), int)

    # Drawing: draw() returns the renderer it was given, with its type
    assert_type(diagram.draw(), MatplotlibRenderer)
    assert_type(diagram.draw(SvgRenderer()), SvgRenderer)
    diagram.save("R290.svg")
    assert_type(save_pdf("both.pdf", [diagram, PsychrometricChart()]), list[MatplotlibRenderer])


def psychrometric_chart() -> None:
    chart = PsychrometricChart(T_range=(0.0, 40.0), W_range=[0.0, 25.0], style="mollier")
    assert_type(chart, PsychrometricChart)
    assert_type(chart.mix({"T": 32, "RH": 40}, {"T": 24, "RH": 50}, m_dot_a_kg_s=0.3), StatePoint)
    assert_type(chart.add_zone("Comfort", T_range=(20, 26), RH_range=(30, 60), label="comfort"), str)
    assert_type(chart.p_Pa, float)
    generic: Chart = chart   # both kinds of chart are a Chart
    assert_type(generic.state({"T": 20.0, "RH": 50.0}), StatePoint)


def mistakes(diagram: PropertyDiagram) -> None:
    # Each line has to give exactly the error named in its comment
    diagram.set_lines(15)  # type: ignore[arg-type]
    diagram.set_lines("T", num="7")  # type: ignore[arg-type]
    diagram.set_line("T")  # type: ignore[attr-defined]
    diagram.add_cycle("Heat pump", [{"p": 3.0, "T": 5.0}], loops="1-2")  # type: ignore[arg-type]
    diagram.title = 5  # type: ignore[assignment]
    PropertyDiagram("R290", units=2)  # type: ignore[arg-type]
    coolplot.PropertyDiagrams  # type: ignore[attr-defined]
    coolplot.EUR  # type: ignore[attr-defined]
