# -*- coding: utf-8 -*-
"""The legacy API (CoolPlot.Plot) has to keep working with current CoolProp.

CoolProp 8 moved its Python bindings to pybind11 and NumPy 2 removed
np.NaN; both broke this code before. These tests run the main entry points
with few points per line to stay fast.
"""
import warnings

import pytest

CoolProp = pytest.importorskip("CoolProp")
pytest.importorskip("matplotlib")

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from CoolPlot.Plot import PropertyPlot, SimpleCompressionCycle  # noqa: E402
from CoolPlot.Util.EnhancedState import EnhancedState, process_fluid_state  # noqa: E402


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield
    plt.close("all")


def test_enhanced_state_works_with_current_coolprop():
    state = process_fluid_state("HEOS::R290")
    assert isinstance(state, EnhancedState)
    state.update(CoolProp.PT_INPUTS, 1e5, 300.0)
    assert state.hmass() == pytest.approx(CoolProp.CoolProp.PropsSI("H", "P", 1e5, "T", 300.0, "R290"))
    assert state.T_critical() == pytest.approx(CoolProp.CoolProp.PropsSI("Tcrit", "R290"), rel=1e-6)


@pytest.mark.parametrize("fluid, kind", [("HEOS::R290", "PH"), ("HEOS::Water", "PT"), ("HEOS::Water", "HS")])
def test_property_plot(tmp_path, fluid, kind):
    plot = PropertyPlot(fluid, kind, unit_system="EUR", tp_limits="ACHP" if kind == "PH" else "DEF")
    plot.calc_isolines(CoolProp.iQ, num=5, points=40)
    plot.calc_isolines(num=4, points=40)
    plot.savefig(str(tmp_path / "plot.png"))
    assert (tmp_path / "plot.png").stat().st_size > 1000
    assert sum(len(lines) for lines in plot.isolines.values()) > 5


def test_own_axes_are_used_without_adding_subplots():
    fig, ax = plt.subplots()
    plot = PropertyPlot("R290", "PH", axes=ax)
    assert plot.axes is ax and plot.figure is fig and len(fig.axes) == 1


def test_compression_cycle():
    cycle = SimpleCompressionCycle("HEOS::R134a", "PH", unit_system="EUR")
    state = CoolProp.AbstractState("HEOS", "R134a")
    state.update(CoolProp.QT_INPUTS, 0.0, 265.0)
    p_evap_Pa = state.p()
    state.update(CoolProp.QT_INPUTS, 1.0, 320.0)
    p_cond_Pa = state.p()
    cycle.simple_solve(280.0, p_evap_Pa, 310.0, p_cond_Pa, 0.7, SI=True)
    assert cycle.COP_heating() == pytest.approx(cycle.COP_cooling() + 1.0)
    assert 1.0 < cycle.COP_cooling() < 10.0
    cycle.steps = 10
    plot = PropertyPlot("HEOS::R134a", "PH", unit_system="EUR")
    plot.draw_process(cycle.get_state_changes())
