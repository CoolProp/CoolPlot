# -*- coding: utf-8 -*-
"""The public vocabulary is frozen (docs/v1_plan.md, 0.5).

A name added here is a promise kept until 2.0; a name removed here needs
a deprecation period. The old names of 0.4 and before still work and
warn once per call.
"""
import warnings

import pytest

import coolplot

#: Names importable from the package.
PACKAGE_NAMES = {
    "__version__", "Chart", "PropertyDiagram", "PsychrometricChart", "save_pdf",
    "Cycle", "CycleSpec", "StateInput", "DiagramSpec", "FluidSpec", "HumidAirSpec", "IsolineSet", "ProcessSpec",
    "Settings", "CalcSettings", "LabelSettings", "PageSettings", "Engine", "Fluid", "DiagramType",
    "TpLimits", "Relative", "Region", "StatePoint", "state_point", "process_path", "PropertyError",
    "Theme", "get_theme", "LineStyle", "MarkerStyle", "TextStyle", "Font", "AxesStyle", "LegendStyle",
    "Scene", "UnitSystem", "Unit", "SI", "KSI", "ENGINEERING", "IP", "EUR",
    "native_mode", "set_native_mode",
}

#: The verbs and properties of every chart.
CHART_METHODS = {
    "set_lines", "set_default_lines", "remove_lines", "line_sets", "set_line_style",
    "add_cycle", "remove_cycle", "move_cycle_state", "cycle_states",
    "set_view", "state_at", "to_display", "update_scene", "draw", "show", "save",
    "refresh", "close", "wait", "from_spec",
}
#: Properties; spec, engine and scene are plain attributes set by the constructor.
CHART_PROPERTIES = {"cache", "progress", "fluid", "diagram_type", "units", "settings", "theme", "title", "kind"}
CHART_ATTRIBUTES = {"spec", "engine", "scene"}

#: Old names: they warn and call the new one.
OLD_NAMES = {
    "set_isolines", "set_default_isolines", "remove_isolines", "isoline_sets", "set_isoline_style", "savefig",
}
OLD_DIAGRAM_NAMES = {"set_process", "remove_process"}
OLD_PSYCHRO_NAMES = {"add_process", "move_process_state", "remove_process", "process_states"}


def _public(cls):
    return {name for name in vars(cls) if not name.startswith("_")}


def test_package_names_are_frozen():
    assert set(coolplot.__all__) == PACKAGE_NAMES
    for name in PACKAGE_NAMES:
        getattr(coolplot, name)


def test_chart_vocabulary_is_frozen():
    from coolplot.chart import Chart
    names = _public(Chart)
    methods = {n for n in names if callable(getattr(Chart, n)) and not getattr(getattr(Chart, n), "deprecated", False)}
    properties = {n for n in names if isinstance(getattr(Chart, n), property)} | {"kind"}
    assert methods == CHART_METHODS
    assert properties == CHART_PROPERTIES
    assert {n for n in names if getattr(getattr(Chart, n), "deprecated", False)} == OLD_NAMES
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram
    chart = PropertyDiagram("R290", "ph")
    assert {n for n in vars(chart) if not n.startswith("_")} == CHART_ATTRIBUTES


def test_constructors_add_only_their_own_names():
    from coolplot.diagram import PropertyDiagram
    from coolplot.psychrometric import PsychrometricChart
    own = {n for n in _public(PropertyDiagram) if not getattr(getattr(PropertyDiagram, n), "deprecated", False)}
    assert own == {"kind", "fluid", "diagram_type", "tp_limits"}
    assert {n for n in _public(PropertyDiagram) if getattr(getattr(PropertyDiagram, n), "deprecated", False)} \
        == OLD_DIAGRAM_NAMES
    own = {n for n in _public(PsychrometricChart) if not getattr(getattr(PsychrometricChart, n), "deprecated", False)}
    assert own == {"kind", "p_Pa", "points"}
    assert {n for n in _public(PsychrometricChart) if getattr(getattr(PsychrometricChart, n), "deprecated", False)} \
        == OLD_PSYCHRO_NAMES


def test_old_names_warn_and_work(tmp_path):
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram, PsychrometricChart
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    with pytest.warns(DeprecationWarning, match="set_lines"):
        diagram.set_isolines("T", num=3)
    with pytest.warns(DeprecationWarning, match="line_sets"):
        assert set(diagram.isoline_sets()) == {"T"}
    with pytest.warns(DeprecationWarning, match="set_line_style"):
        diagram.set_isoline_style("T", color="red")
    with pytest.warns(DeprecationWarning, match="remove_lines"):
        diagram.remove_isolines("T")
    with pytest.warns(DeprecationWarning, match="set_default_lines"):
        diagram.set_default_isolines(num=3)
    assert set(diagram.line_sets()) == {"T", "s", "rho", "Q"}
    with pytest.warns(DeprecationWarning, match="'EUR' is called 'engineering'"):
        assert PropertyDiagram("R290", "ph", units="EUR").units.name == "engineering"
    chart = PsychrometricChart(T_range=(0, 40), W_range=(0, 20))
    with pytest.warns(DeprecationWarning, match="closed=False"):
        chart.add_process("Heating", [{"T": 5, "RH": 80}, {"T": 25, "W": 4.3}])
    with pytest.warns(DeprecationWarning, match="cycle_states"):
        states = chart.process_states("Heating")
    assert states[1].T == pytest.approx(298.15)
    with pytest.warns(DeprecationWarning, match="move_cycle_state"):
        chart.move_process_state("Heating", 2, 30.0, 4.3)
    with pytest.warns(DeprecationWarning, match="remove_cycle"):
        chart.remove_process("Heating")
    assert chart.spec.cycles == ()
    pytest.importorskip("matplotlib")
    with pytest.warns(DeprecationWarning, match="use save"):
        diagram.savefig(str(tmp_path / "old.svg"))
    assert (tmp_path / "old.svg").stat().st_size > 1000


def test_new_names_do_not_warn():
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram, PsychrometricChart
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        diagram = PropertyDiagram("R290", "ph", units="engineering", tp_limits="ACHP")
        diagram.set_default_lines(num=3)
        diagram.set_line_style("T", color="red")
        diagram.add_cycle("hp", [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
                                 {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}])
        chart = PsychrometricChart(T_range=(0, 40), W_range=(0, 20))
        chart.set_default_lines()
        chart.add_cycle("Heating", [{"T": 5, "RH": 80}, {"T": 25, "W": 4.3}], closed=False)
        assert [i.id for i in chart.update_scene() if i.role == "cycle"] == ["cycle/Heating/loop/0"]
        assert chart.spec.cycles[0].loops == ((1, 2),)


def test_vocabulary_covers_every_public_name():
    """Nothing public on Chart escapes the frozen sets: no stray class attributes."""
    from coolplot.chart import Chart
    names = _public(Chart)
    deprecated = {n for n in names if getattr(getattr(Chart, n), "deprecated", False)}
    properties = {n for n in names if isinstance(getattr(Chart, n), property)}
    methods = {n for n in names if callable(getattr(Chart, n))} - deprecated
    assert names == methods | properties | deprecated | {"kind"}
    import inspect
    assert set(inspect.signature(Chart.set_lines).parameters) == {
        "self", "key", "values", "num", "range", "rounding", "labels", "points", "units"}
    assert "closed" in inspect.signature(Chart.add_cycle).parameters
    for name in ("set_view", "state_at", "move_cycle_state", "cycle_states"):
        assert "units" in inspect.signature(getattr(Chart, name)).parameters, name


def test_units_and_errors():
    import pickle
    from coolplot import ENGINEERING, IP, KSI, SI, PropertyError, StatePoint, Unit, UnitSystem
    assert float(IP["p"].from_SI(1e5)) == pytest.approx(14.50377, rel=1e-6)
    assert float(IP["T"].from_SI(373.15)) == pytest.approx(212.0)
    assert float(IP["h"].from_SI(1e3)) == pytest.approx(0.429923, rel=1e-5)
    assert float(IP["s"].from_SI(1e3)) == pytest.approx(0.238846, rel=1e-5)
    assert float(IP["rho"].from_SI(1.0)) == pytest.approx(0.062428, rel=1e-5)
    assert float(IP["v"].from_SI(1.0)) == pytest.approx(16.0185, rel=1e-5)
    assert float(IP["W"].from_SI(0.01)) == pytest.approx(70.0)
    assert set(IP.units) == set(SI.units) == set(KSI.units) == set(ENGINEERING.units)
    assert hash(UnitSystem("x", SI.units)) == hash(UnitSystem("x", dict(SI.units)))
    assert hash(UnitSystem("SI", dict(SI.units, p=Unit("bar", 1e-5)))) != hash(SI)
    assert pickle.loads(pickle.dumps(ENGINEERING)) == ENGINEERING
    state = StatePoint(T=298.15, p=3e5, h=4e5)
    assert state.in_units("engineering") == pytest.approx({"T": 25.0, "p": 3.0, "h": 400.0})
    assert state.describe("engineering") == "T = 25 deg C, p = 3 bar, h = 400 kJ/kg"
    error = PropertyError("R290", (("p", 3e10), ("T", 293.15)), "too high", "State 2 of the cycle 'hp'")
    assert str(error.with_units("engineering")) == \
        "State 2 of the cycle 'hp': no state of R290 at p = 300000 bar, T = 20 deg C (too high)."
    assert str(pickle.loads(pickle.dumps(error.with_units(IP)))) == str(error.with_units(IP))
    small = UnitSystem("small", {"T": Unit("deg C", 1.0, -273.15)})
    assert "p = 3e10 Pa" in str(error.with_units(small)) and "20 deg C" in str(error.with_units(small))
    assert isinstance(error, ValueError)


def test_fluid_is_checked_before_anything_changes():
    pytest.importorskip("CoolProp")
    from coolplot import DiagramSpec, PropertyDiagram
    from coolplot.engine import BackgroundEngine
    with pytest.raises(ValueError, match="cannot make the fluid"):
        PropertyDiagram("R29O", "ph")
    engine = BackgroundEngine("threads")
    try:
        with pytest.raises(ValueError, match="cannot make the fluid"):
            PropertyDiagram("R29O", "ph", engine=engine)
        assert not engine.claimed
    finally:
        engine.close()
    with pytest.raises(ValueError, match="cannot make the fluid"):
        PropertyDiagram.from_spec(DiagramSpec("R29O"))
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    with pytest.raises(ValueError, match="cannot make the fluid"):
        diagram.fluid = "R29O"
    assert diagram.spec.fluid.components == ("R290",)
    assert diagram.update_scene().axes.x_label.startswith("Specific enthalpy")


def test_set_lines_defaults_and_units_per_call():
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram, PsychrometricChart
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    diagram.set_lines("T", values=[32.0, 212.0], units="IP")
    assert diagram.line_sets()["T"].values_SI == pytest.approx((273.15, 373.15))
    assert diagram.line_sets()["T"].labels is False and diagram.line_sets()["T"].rounding is False
    diagram.set_view((100.0, 300.0), None, units="IP")
    assert diagram.spec.view_SI[0] == pytest.approx((232.6e3, 697.8e3), rel=1e-3)
    state = diagram.state_at(200.0, 50.0, units="IP")
    assert state.p == pytest.approx(344737.9, rel=1e-5)
    diagram.add_cycle("hp", [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
                             {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}])
    assert diagram.cycle_states("hp", units="engineering")[1]["T"] == pytest.approx(0.0)
    diagram.move_cycle_state("hp", 1, 450e3, 3e5, units="SI")   # SI values, where the display units are kJ and bar
    assert diagram.cycle_states("hp")[1].h == pytest.approx(450e3) and diagram.cycle_states("hp")[1].p == 3e5
    chart = PsychrometricChart(T_range=(0, 40), W_range=(0, 20))
    chart.set_lines("RH")
    assert chart.line_sets()["RH"].labels is True and chart.line_sets()["RH"].rounding is True


def test_every_old_name_is_in_the_upgrade_guide():
    """0.9 is the deprecation release: whatever warns is listed with its replacement."""
    import importlib
    import inspect
    import os
    guide = open(os.path.join(os.path.dirname(__file__), "..", "docs", "upgrade.md"), encoding="utf-8").read()
    found = set()
    for module_name in ("coolplot.chart", "coolplot.diagram", "coolplot.psychrometric"):
        module = importlib.import_module(module_name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            for name, member in vars(cls).items():
                if getattr(member, "deprecated", False):
                    found.add(name)
    assert found >= OLD_NAMES | OLD_DIAGRAM_NAMES | OLD_PSYCHRO_NAMES
    import re
    # The whole name in code quotes, "`name`" or "`name(", not a longer name starting with it
    missing = sorted(name for name in found if not re.search(r"`{0}[`(]".format(re.escape(name)), guide))
    assert not missing, missing
