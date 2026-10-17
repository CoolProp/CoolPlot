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
    assert methods == CHART_METHODS | {"from_spec"}
    assert properties == CHART_PROPERTIES
    assert {n for n in names if getattr(getattr(Chart, n), "deprecated", False)} == OLD_NAMES
    from coolplot import PropertyDiagram
    chart = PropertyDiagram.__new__(PropertyDiagram)
    assert CHART_ATTRIBUTES <= set(Chart.__init__.__code__.co_names) and not hasattr(chart, "spec")


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
