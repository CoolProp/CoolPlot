# -*- coding: utf-8 -*-
"""Psychrometric charts: humid-air lines, air processes and the chart facade."""
import json

import numpy as np
import pytest

pytest.importorskip("CoolProp")
from CoolProp.HumidAirProp import HAPropsSI  # noqa: E402

from coolplot.core.floats import is_zero, same_number, same_numbers  # noqa: E402
from coolplot.psychrometric import PsychrometricChart  # noqa: E402
from coolplot.render.svg import SvgRenderer  # noqa: E402
from coolplot.spec import DiagramSpec  # noqa: E402
from coolplot.thermo.humid_air import (air_state, chart_ranges, enthalpy_from_mollier,  # noqa: E402
                                       mollier_temperature, psychro_line, saturation_W)

P = 101325.0
T_RANGE = (263.15, 318.15)


def test_air_state_matches_hapropssi():
    s = air_state("T", 298.15, "RH", 0.5, P)
    assert s.W == pytest.approx(HAPropsSI("W", "T", 298.15, "P", P, "R", 0.5))
    assert s.Twb == pytest.approx(HAPropsSI("B", "T", 298.15, "P", P, "R", 0.5))
    assert s.h == pytest.approx(HAPropsSI("H", "T", 298.15, "P", P, "R", 0.5))
    assert s.Tdp < s.Twb < s.T and s["RH"] == pytest.approx(0.5)
    with pytest.raises(ValueError):
        air_state("T", 300.0, "T", 300.0, P)


@pytest.mark.parametrize("key, value", [("RH", 0.4), ("Twb", 288.15), ("h", 50e3), ("v", 0.86)])
def test_lines_stay_below_saturation_and_hold_their_value(key, value):
    curve = psychro_line(key, value, P, T_RANGE, points=40)
    assert curve.n_valid >= 5
    w_sat = saturation_W(curve.x, P)
    assert np.all(curve.y <= w_sat * (1 + 1e-6)) and np.all(curve.y >= 0.0)
    name = {"RH": "R", "Twb": "B", "h": "H", "v": "V"}[key]
    for T, W in zip(curve.x[::7], curve.y[::7]):
        assert HAPropsSI(name, "T", T, "P", P, "W", W) == pytest.approx(value, rel=1e-4)


@pytest.mark.parametrize("key, value", [("Twb", 288.15), ("h", 50e3), ("v", 0.86), ("Twb", 273.15),
                                        ("Twb", 268.15), ("h", 10e3), ("v", 0.78)])
def test_lines_start_on_the_saturation_curve(key, value):
    curve = psychro_line(key, value, P, T_RANGE, points=40)
    assert curve.y[0] == pytest.approx(saturation_W(curve.x[0], P), rel=1e-6)
    if key == "Twb":
        assert curve.x[0] == pytest.approx(value)   # on saturation, wet bulb equals dry bulb


def default_values(key, T_range, W_range, units="SI"):
    """The values a chart draws for a family without explicit values."""
    from coolplot.engine import plan
    chart = PsychrometricChart(T_range=T_range, W_range=W_range, units=units)
    chart.set_lines(key)
    # Only the family's own lines: the plan also holds the saturation curve
    return [r.value_SI for r in plan(chart.spec, chart.engine.domain(chart.spec)) if r.key == key]


def test_default_values_are_round():
    assert default_values("RH", T_RANGE, (0.0, 0.025)) == pytest.approx([0.1 * i for i in range(1, 11)])
    twb_C = np.array(default_values("Twb", (-10.0, 45.0), (0.0, 25.0), "engineering")) - 273.15
    h = np.array(default_values("h", (-10.0, 45.0), (0.0, 25.0), "engineering"))
    assert len(twb_C) >= 5 and len(h) >= 5   # allclose on an empty array would pass anything
    assert np.allclose(np.round(twb_C / 5.0) * 5.0, twb_C, atol=1e-6)
    assert np.allclose(np.round(h / 10e3) * 10e3, h, atol=1e-3)


@pytest.mark.parametrize("T_range, W_range", [((273.15, 373.15), (0.0, 0.2)), ((273.15, 473.15), (0.0, 1.0)),
                                              ((293.15, 295.15), (0.008, 0.009))])
def test_default_line_counts_stay_reasonable(T_range, W_range):
    for key in ("Twb", "h", "v"):
        assert 3 <= len(default_values(key, T_range, W_range)) <= 20, key


def test_lines_reach_their_ends():
    # Above the boiling point there is no saturation: lines go on
    curve = psychro_line("RH", 0.1, P, (293.15, 423.15), points=60)
    assert curve.x[-1] > 400.0
    # A falling line ends exactly at W = 0, for v where the ideal-gas law
    # nearly holds for dry air (T = p v / R_air)
    curve = psychro_line("v", 0.80, P, T_RANGE, points=100)
    assert is_zero(curve.y[-1])
    assert curve.x[-1] == pytest.approx(P * 0.80 / 287.055, abs=0.5)
    # The 0 deg C wet-bulb line runs all the way down to dry air, through
    # the temperatures where HAPropsSI cannot give W from Twb directly
    curve = psychro_line("Twb", 273.15, P, T_RANGE, points=100)
    assert is_zero(curve.y[-1]) and curve.x[-1] > 283.0
    assert np.all(np.diff(curve.y) <= 1e-12)   # W falls along the line, no jumps back


@pytest.fixture
def chart():
    c = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))
    c.set_default_lines()
    c.add_cycle("Air conditioning", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}, {"T": 20, "W": 8.9}], closed=False)
    return c


def test_chart_scene(chart):
    scene = chart.update_scene()
    groups = {i.group for i in scene}
    assert {"iso/RH", "iso/Twb", "iso/h", "iso/v", "cycle/Air conditioning"} <= groups
    assert scene["iso/RH/1"].role == "saturation"
    assert scene.axes.x_label == "Dry-bulb temperature T / \u00b0C"
    assert scene.axes.y_label == "Humidity ratio W / g/kg"
    assert same_numbers(scene.axes.x_limits, (-10.0, 45.0))
    labels = [i for i in scene if i.role == "isoline_label"]
    assert len(labels) > 10 and any(t.id == "iso/RH/0.5/label" and t.text == "50" for t in labels)
    assert "Relative humidity \u03c6 / %" in {i.legend for i in scene if i.legend}
    states = list(chart.cycle_states("Air conditioning").values())
    assert states[2].W == pytest.approx(8.9e-3) and states[1].RH == pytest.approx(0.95)


def test_processes_fail_early_and_leave_the_chart_unchanged(chart):
    before = chart.spec
    with pytest.raises(ValueError, match="State 1"):
        chart.add_cycle("bad", [{"T": 20, "RH": 150}, {"T": 25, "RH": 50}], closed=False)
    with pytest.raises(ValueError):
        chart.add_cycle("bad", [{"T": 20}], closed=False)
    assert chart.spec == before


def test_lines_are_computed_once(chart):
    chart.update_scene()
    misses = chart.cache.misses
    chart.theme = "dark"
    chart.add_cycle("Heating", [{"T": 5, "RH": 80}, {"T": 25, "W": 4.3}], closed=False)
    chart.update_scene()
    assert chart.cache.misses == misses


def test_spec_round_trips_through_json(chart):
    from coolplot.style.values import LineStyle, MarkerStyle
    chart.set_lines("h", [20.0, 40.0], labels=False)
    chart.add_cycle("Styled", [{"T": 20, "RH": 50}, {"T": 30, "W": 8}], closed=True,
                      line_style=LineStyle(color="#ff0000", width_pt=2.0), marker_style=MarkerStyle(shape="s"))
    chart.set_view((0, 30), (0, 15))
    chart.points = 60
    data = json.loads(json.dumps(chart.spec.to_dict()))
    assert DiagramSpec.from_dict(data) == chart.spec
    again = PsychrometricChart.from_spec(DiagramSpec.from_dict(data))
    assert again.points == 60 and again.update_scene().axes.x_limits == pytest.approx((0.0, 30.0))


def test_state_at_cursor(chart):
    state = chart.state_at(25.0, 10.0)
    assert state.T == pytest.approx(298.15) and state.W == pytest.approx(0.010)


def test_chart_draws_with_every_backend(chart, tmp_path):
    chart.draw(SvgRenderer()).save(str(tmp_path / "psy.svg"))
    assert (tmp_path / "psy.svg").stat().st_size > 10000
    pytest.importorskip("plotly")
    from coolplot.render.plotly import PlotlyRenderer
    chart.draw(PlotlyRenderer()).save(str(tmp_path / "psy.html"))
    from coolplot.render.web import WebRenderer
    chart.draw(WebRenderer()).save(str(tmp_path / "psy_web.html"))


def test_other_pressures_and_units():
    high = PsychrometricChart(p=0.8, T_range=(0, 40), W_range=(0, 30))    # about 2000 m above sea level
    assert high.p_Pa == pytest.approx(0.8e5)
    high.set_default_lines()
    lines = [i for i in high.update_scene() if i.id.startswith("iso/") and not i.id.endswith("/label")]
    assert len(lines) > 20
    for item in lines:   # every line stays below saturation at 0.8 bar
        assert np.all(item.y <= saturation_W(item.x + 273.15, 0.8e5) * 1e3 * (1 + 1e-6))
    for wrong in (dict(p=101325.0), dict(p=1e-3), dict(T_range=(263, 400))):   # Pa as bar, K as deg C
        with pytest.raises(ValueError):
            PsychrometricChart(**wrong)
    s = air_state("T", 298.15, "RH", 0.5, 0.8e5)
    assert s.W > air_state("T", 298.15, "RH", 0.5, P).W   # thinner air holds more water per kg
    si = PsychrometricChart(units="SI", T_range=(270, 310), W_range=(0, 0.02))
    si.set_lines("RH", [0.5])
    assert si.update_scene().axes.y_label == "Humidity ratio W / kg/kg"
    with pytest.raises(ValueError):
        si.set_lines("RH", [50])          # SI relative humidity is a fraction
    chart = PsychrometricChart()
    with pytest.raises(ValueError):
        chart.set_lines("RH", [0, 50])    # 0 % has no line
    with pytest.raises(ValueError):
        PsychrometricChart(units="imperial")


def test_bad_process_input(chart):
    with pytest.raises(ValueError, match="unknown properties"):
        chart.add_cycle("Not of air", [{"T": 20, "rho": 1.2}], closed=False)
    elsewhere = air_state("T", 298.15, "RH", 0.5, 0.8e5)
    with pytest.raises(ValueError, match="Pa"):
        chart.add_cycle("Other pressure", [elsewhere], closed=False)


def test_a_via_that_keeps_the_pressure_is_refused_for_humid_air(chart):
    # CoolProp returns saturated air for T and the total pressure; heating
    # at the same humidity ratio is given by W instead.
    with pytest.raises(ValueError, match="total pressure"):
        air_state("T", 293.15, "p", 101325.0)
    with pytest.raises(ValueError, match="total pressure"):
        chart.add_cycle("Winter", [{"T": -5.0, "RH": 80.0}, {"T": 20.0, "via": "isobaric"}], closed=False)
        chart.cycle_states("Winter")
    chart.add_cycle("Heating", [{"T": -5.0, "W": 2.0}, {"T": 20.0, "W": 2.0}], closed=False)
    states = chart.cycle_states("Heating", units="engineering")
    assert states[2]["W"] == pytest.approx(states[1]["W"])
    assert states[2]["RH"] < 20.0


def test_via_sensible_keeps_the_humidity_ratio(chart):
    chart.add_cycle("Preheat", [{"T": -5.0, "RH": 80.0}, {"T": 20.0, "via": "sensible"}], closed=False)
    states = chart.cycle_states("Preheat")
    assert states[2].W == pytest.approx(states[1].W, rel=1e-12)   # HAPropsSI gives back the W it was given
    assert states[2].T == pytest.approx(293.15) and states[2].RH < 0.2
    # The state that follows moves along when the state before it moves
    chart.move_cycle_state("Preheat", 1, 0.0, 3.0)         # T in deg C, W in g/kg
    moved = chart.cycle_states("Preheat")
    assert moved[2].W == pytest.approx(moved[1].W, rel=1e-12) and moved[2].W == pytest.approx(3e-3)


def test_via_sensible_below_the_dew_point_says_so(chart):
    with pytest.raises(ValueError, match="below the dew point"):
        chart.add_cycle("Too cold", [{"T": 24.0, "RH": 50.0}, {"T": 5.0, "via": "sensible"}], closed=False)


def test_via_sensible_is_refused_for_a_fluid():
    from coolplot import PropertyDiagram
    diagram = PropertyDiagram("HEOS::R290", "ph", units="engineering")
    with pytest.raises(ValueError, match="only humid air"):
        diagram.add_cycle("x", [{"p": 3.0, "T": 0.0}, {"T": 20.0, "via": "sensible"}], closed=False)


def test_mixing_conserves_dry_air_water_and_energy(chart):
    outdoor, room = {"T": 32.0, "RH": 40.0}, {"T": 24.0, "RH": 50.0}
    a, b = chart.state(outdoor), chart.state(room)
    m_dot_a_kg_s, m_dot_b_kg_s = 0.3, 0.7
    mixed = chart.mix(outdoor, room, m_dot_a_kg_s, m_dot_b_kg_s)
    m_dot_kg_s = m_dot_a_kg_s + m_dot_b_kg_s
    assert mixed.W * m_dot_kg_s == pytest.approx(a.W * m_dot_a_kg_s + b.W * m_dot_b_kg_s, rel=1e-9)   # water
    assert mixed.h * m_dot_kg_s == pytest.approx(a.h * m_dot_a_kg_s + b.h * m_dot_b_kg_s, rel=1e-9)   # energy
    assert b.T < mixed.T < a.T and mixed.T - b.T < a.T - mixed.T   # closer to the larger stream
    # Only the ratio of the flows matters, and a stream without flow leaves the other as it is
    assert chart.mix(outdoor, room, 3.0, 7.0).T == pytest.approx(mixed.T, rel=1e-12)
    assert chart.mix(outdoor, room, 1.0, 0.0).T == pytest.approx(a.T, rel=1e-9)
    # A mixed state goes into a cycle as it is
    chart.add_cycle("Mixing", {1: outdoor, 2: room, 3: mixed}, loops=[[1, 3, 2]])
    assert same_number(chart.cycle_states("Mixing")[3].W, mixed.W)


@pytest.mark.parametrize("T_C", [-20.0, 0.0, 20.0, 35.0, 49.0])
def test_saturated_streams_mix_to_saturated_air_not_fog(chart, T_C):
    saturated = {"T": T_C, "RH": 100.0}
    for flows in ((1.0, 0.0), (0.5, 0.5), (0.3, 0.7)):
        mixed = chart.mix(saturated, saturated, *flows)
        assert mixed.T == pytest.approx(T_C + 273.15, abs=1e-6) and mixed.RH == pytest.approx(1.0, abs=1e-6)


def test_extreme_flows_keep_their_ratio(chart):
    a, b = {"T": 32.0, "RH": 40.0}, {"T": 24.0, "RH": 50.0}
    assert chart.mix(a, b, 1e308, 1e308).T == pytest.approx(chart.mix(a, b).T, rel=1e-12)
    assert chart.mix(a, b, 5e-324, 0.0).T == pytest.approx(chart.state(a).T, rel=1e-9)   # no underflow to W = 0


def test_mixing_refuses_fog_bad_flows_and_two_pressures(chart):
    with pytest.raises(ValueError, match="fog"):
        chart.mix({"T": -5.0, "RH": 100.0}, {"T": 30.0, "RH": 95.0})
    for flows in ((-1.0, 1.0), (0.0, 0.0), (float("nan"), 1.0), (float("inf"), 1.0)):
        with pytest.raises(ValueError, match="mass flows"):
            chart.mix({"T": 20.0, "RH": 50.0}, {"T": 25.0, "RH": 50.0}, *flows)
    from coolplot.thermo.humid_air import mixed_air
    with pytest.raises(ValueError, match="one total pressure"):
        mixed_air(air_state("T", 293.15, "RH", 0.5, P), air_state("T", 293.15, "RH", 0.5, 0.9 * P), 1.0, 1.0)


def test_a_zone_follows_its_humidity_lines_without_markers_or_numbers(chart):
    assert chart.add_zone("Comfort", T_range=(26, 20), RH_range=(60, 30), label="comfort", segments=6) == "Comfort"
    states = chart.cycle_states("Comfort", units="engineering")
    assert len(states) == 14 and chart.spec.cycles[-1].loops == (tuple(range(1, 15)) + (1,),)
    assert [states[n]["RH"] for n in range(1, 8)] == pytest.approx([30.0] * 7)   # the dry edge, given in %
    assert [states[n]["RH"] for n in range(8, 15)] == pytest.approx([60.0] * 7)
    assert states[1]["T"] == pytest.approx(20.0) and states[7]["T"] == pytest.approx(26.0)
    scene = chart.update_scene()
    assert [t.text for t in scene.group("cycle/Comfort/numbers")] == ["comfort"]   # at (20 deg C, 60 %)
    assert scene["cycle/Comfort/number/14"].x == pytest.approx(20.0)
    assert is_zero(scene["cycle/Comfort/states"].style.size_pt)
    chart.remove_cycle("Comfort")
    assert all(c.name != "Comfort" for c in chart.spec.cycles)


@pytest.mark.parametrize("T_range, RH_range, segments, match", [
    ((20, 20), (30, 60), 12, "two different"), ((20, 26), (60, 60), 12, "two different"),
    ((20, 26), (30, 60), 0, "whole number"), ((20, 26), (30, 60), 2.7, "whole number"),
    ((20, 26), (30, 60), True, "whole number")])
def test_a_zone_needs_an_area_and_a_segment(chart, T_range, RH_range, segments, match):
    with pytest.raises(ValueError, match=match):
        chart.add_zone("bad", T_range, RH_range, segments=segments)


def test_a_state_from_two_properties_in_the_chart_units(chart):
    state = chart.state({"T": 13.0, "RH": 95.0})
    assert state.T == pytest.approx(286.15) and state.RH == pytest.approx(0.95)
    assert chart.state(state) is state
    with pytest.raises(ValueError, match="needs a state before it"):
        chart.state({"T": 20.0, "via": "sensible"})


def test_interaction_zooms_and_drags_air_states(chart):
    pytest.importorskip("matplotlib")
    from coolplot.core.events import DragEnd, ViewChanged
    from coolplot.interaction import Interaction
    from coolplot.render.mpl import MatplotlibRenderer
    renderer = MatplotlibRenderer(use_pyplot=False)
    interaction = Interaction(chart, renderer)
    interaction.redraw()
    misses = chart.cache.misses
    interaction.handle(ViewChanged((10.0, 30.0), (0.0, 15.0)))
    assert renderer.ax.get_xlim() == pytest.approx((10.0, 30.0))
    assert chart.cache.misses == misses   # zooming computes nothing new
    assert interaction.cycle_state("cycle/Air conditioning/states", 1) == ("Air conditioning", 2)
    interaction.handle(DragEnd("cycle/Air conditioning/states", 1, 15.0, 8.0))
    moved = list(chart.cycle_states("Air conditioning").values())[1]
    assert moved.T == pytest.approx(288.15) and moved.W == pytest.approx(0.008)
    interaction.handle(DragEnd("cycle/Air conditioning/states", 1, 15.0, 80.0))   # in the fog: refused
    assert list(chart.cycle_states("Air conditioning").values())[1].W == pytest.approx(0.008)


def test_charts_with_a_foggy_edge_get_all_visible_lines():
    # T 0 to 50 deg C, W 10 to 30 g/kg: the left edge is fog, the visible
    # region starts on saturation at about 14 deg C
    ranges = dict(chart_ranges(P, (273.15, 323.15), (0.010, 0.030)))
    assert ranges["Twb"][0] - 273.15 <= 15.0 + 1e-6 and ranges["h"][0] <= 40e3 + 1e-6
    twb_C = np.array(default_values("Twb", (0.0, 50.0), (10.0, 30.0), "engineering")) - 273.15
    assert twb_C.min() <= 15.0 + 1e-6
    assert min(default_values("h", (0.0, 50.0), (10.0, 30.0), "engineering")) <= 40e3 + 1e-6


def test_the_limits_of_hapropssi_are_allowed():
    assert PsychrometricChart(T_range=(-100, 50)).spec.limits.range_SI("T")[0] == pytest.approx(173.15)
    PsychrometricChart().set_lines("Twb", [-100.0])


def test_the_wet_bulb_search_reports_no_convergence(monkeypatch):
    from coolplot.thermo import humid_air
    monkeypatch.setattr(humid_air, "_SEARCH_ITERATIONS", 1)
    assert humid_air._W_by_search("h", 50e3, 300.0, 101325.0, 0.03)[1] == "failed"


# The Mollier h,x chart (1.2): x horizontal, the temperature scale Thx up

@pytest.fixture
def mollier():
    c = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25), style="mollier")
    c.set_default_lines()
    c.add_cycle("Air conditioning", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}, {"T": 20, "via": "sensible"}],
                closed=False)
    return c


def test_the_mollier_temperature_scale_is_linear_in_enthalpy():
    s = air_state("T", 298.15, "RH", 0.5, P)
    assert s.Thx == pytest.approx(mollier_temperature(s.h, s.W))
    assert s.Thx == pytest.approx(273.15 + (s.h - 2500e3 * s.W) / 1006.0)
    assert enthalpy_from_mollier(s.Thx, s.W) == pytest.approx(s.h)
    # dry air: the scale is the dry-bulb temperature, to the reference of h
    assert air_state("T", 293.15, "W", 0.0, P).Thx == pytest.approx(293.15, abs=0.05)
    back = air_state("Thx", s.Thx, "W", s.W, P)
    assert back.T == pytest.approx(298.15) and back.RH == pytest.approx(0.5)
    with pytest.raises(ValueError, match="humidity ratio"):
        air_state("Thx", 300.0, "RH", 0.5, P)


def test_the_mollier_chart_has_x_across_and_temperature_up(mollier):
    assert mollier.style == "mollier" and mollier.spec.diagram.is_mollier
    scene = mollier.update_scene()
    assert scene.axes.x_label == "Humidity ratio x / g/kg"
    assert scene.axes.y_label == "Temperature T / \u00b0C"
    assert same_numbers(scene.axes.x_limits, (0.0, 25.0)) and same_numbers(scene.axes.y_limits, (-10.0, 45.0))
    groups = {i.group for i in scene}
    assert {"iso/T", "iso/RH", "iso/h", "iso/Twb", "iso/v", "cycle/Air conditioning"} <= groups
    assert scene["iso/RH/1"].role == "saturation"
    legends = {i.legend for i in scene if i.legend}
    assert "Relative humidity \u03c6 / %" in legends and not any("RH" in t for t in legends)
    assert scene["iso/RH/0.5/label"].text == "50"
    chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25), style="mollier", settings="interactive")
    chart.settings = chart.settings.with_(labels={"mode": "edge"})
    chart.set_lines("RH", [50.0])
    assert chart.update_scene()["iso/RH/0.5/label"].text == "\u03c6=50 %"
    with pytest.raises(ValueError, match="style"):
        PsychrometricChart(style="din")


def test_the_psychrometric_chart_keeps_its_axes_and_symbols(chart):
    assert chart.style == "psychrometric" and not chart.spec.diagram.is_mollier
    assert "T" not in {iso.key for iso in chart.spec.isolines}
    assert chart.spec.diagram.symbol("W") == "W" and chart.spec.diagram.symbol("RH") == "RH"


def test_mollier_isotherms_hold_their_temperature_and_rise(mollier):
    scene = mollier.update_scene()
    line = scene["iso/T/293.15"]
    x, y = np.asarray(line.x), np.asarray(line.y)
    ok = np.isfinite(x) & np.isfinite(y)
    assert ok.sum() > 5 and np.all(np.diff(y[ok]) / np.diff(x[ok]) > 0.0)   # the isotherms rise with x
    for xi, yi in zip(x[ok][::5], y[ok][::5]):
        W = xi * 1e-3
        T = HAPropsSI("T", "H", enthalpy_from_mollier(yi + 273.15, W), "W", W, "P", P)
        assert T == pytest.approx(293.15, abs=1e-6)
    # lines of constant enthalpy fall to the right
    h = scene["iso/h/40000"]
    hx, hy = np.asarray(h.x), np.asarray(h.y)
    ok = np.isfinite(hx) & np.isfinite(hy)
    assert np.all(np.diff(hy[ok]) / np.diff(hx[ok]) < 0.0)


def test_mollier_states_cursor_and_drag(mollier):
    states = list(mollier.cycle_states("Air conditioning").values())
    assert states[2].W == pytest.approx(states[1].W)
    for s in states:
        assert s.Thx == pytest.approx(mollier_temperature(s.h, s.W))
    cursor = mollier.state_at(10.0, 25.0)
    assert cursor.W == pytest.approx(0.010) and cursor.Thx == pytest.approx(298.15)
    assert cursor.T < cursor.Thx   # moist air is cooler than its point on the scale
    data = json.loads(json.dumps(mollier.spec.to_dict()))
    assert DiagramSpec.from_dict(data) == mollier.spec
    assert PsychrometricChart.from_spec(DiagramSpec.from_dict(data)).style == "mollier"


def test_states_of_older_charts_get_the_mollier_temperature(chart):
    # a full air state written before 1.2 has no Thx; reading it fills it in
    s = air_state("T", 298.15, "RH", 0.5, P)
    from coolplot.core.state import StatePoint
    old = StatePoint(**{k: s[k] for k in ("T", "W", "RH", "Twb", "Tdp", "h", "v", "p")})
    chart.add_cycle("Old", [old, {"T": 30, "via": "sensible"}], closed=False)
    first = list(chart.cycle_states("Old").values())[0]
    assert first.Thx == pytest.approx(s.Thx)


def test_unit_records_leave_the_mollier_scale_out_unless_it_differs():
    from coolplot.core.units import ENGINEERING, UnitSystem
    assert ENGINEERING.units["Thx"] == ENGINEERING.units["T"]
    own = UnitSystem("mine", dict(ENGINEERING.units))
    assert own.units["Thx"] == ENGINEERING.units["T"]
    assert PsychrometricChart(style="mollier").spec.to_dict()["units"] == "engineering"


def test_mollier_isotherms_are_cached_per_humidity_range():
    # The isotherms end a little beyond the top of W; a chart with a taller
    # W axis must not be served the shorter isotherms of another
    low = PsychrometricChart(T_range=(-10, 45), W_range=(0, 10), style="mollier")
    low.set_lines("T", [30.0])
    low.update_scene()
    high = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25), style="mollier", cache=low.cache)
    high.set_lines("T", [30.0])
    x = np.asarray(high.update_scene()["iso/T/303.15"].x)
    assert np.nanmax(x) > 25.0


def test_the_mollier_scale_follows_a_changed_temperature_unit():
    from coolplot.core.units import ENGINEERING, Unit
    fahrenheit = ENGINEERING.with_unit("T", Unit("deg F", 1.8, -459.67, "R"))
    assert fahrenheit["Thx"] == fahrenheit["T"]
    chart = PsychrometricChart(T_range=(32, 104), W_range=(0, 20), units=fahrenheit, style="mollier")
    assert chart.spec.limits.range_SI("Thx") == pytest.approx((273.15, 313.15))
    chart.set_lines("T", [50.0])
    scene = chart.update_scene()
    assert scene.axes.y_label.endswith("\u00b0F") and scene["iso/T/283.15/label"].text == "50"
    assert "Dry-bulb temperature T / \u00b0F" in {i.legend for i in scene if i.legend}
    kelvin = ENGINEERING.with_unit("Thx", Unit("K")).with_unit("T", Unit("deg F", 1.8, -459.67, "R"))
    assert kelvin["Thx"].label == "K"   # set on its own, it stays


def test_records_of_older_charts_get_the_mollier_temperature_when_read(chart):
    s = air_state("T", 298.15, "RH", 0.5, P)
    old = {k: s[k] for k in ("T", "W", "RH", "Twb", "Tdp", "h", "v", "p")}
    chart.set_lines("RH", [50.0])
    data = json.loads(json.dumps(chart.spec.to_dict()))
    data["cycles"] = [{"name": "Old", "states": [[1, {"state": old}], [2, {"props": [["T", 303.15]], "via": "sensible"}]],
                       "loops": [[1, 2]]}]
    data["diagram"] = "mollier"
    data["limits"] = {"bounds": {"Thx": [263.15, 318.15], "W": [0.0, 0.025]}}
    again = PsychrometricChart.from_spec(DiagramSpec.from_dict(data))
    first = again.cycle_states("Old")[1]
    assert first.Thx == pytest.approx(s.Thx)
    assert "cycle/Old" in {i.group for i in again.update_scene()}


def test_mollier_bounds_outside_hapropssi_are_refused():
    from coolplot.core.limits import Region
    from coolplot.thermo.humid_air import HumidAir
    with pytest.raises(ValueError, match="Temperatures have to lie between"):
        HumidAir().domain(Region((("Thx", (100.0, 700.0)), ("W", (0.0, 0.02)))))


def test_inputs_of_the_mollier_scale_are_named_in_errors(mollier):
    from coolplot.core.errors import PropertyError
    with pytest.raises(PropertyError) as info:
        air_state("Thx", 330.0, "W", 0.2, P)   # deep in the fog
    assert [k for k, _ in info.value.inputs] == ["Thx", "W"]
    with pytest.raises(ValueError, match="dew point"):
        mollier.add_cycle("Too cold", [{"T": 25, "RH": 50}, {"Thx": 5, "via": "sensible"}], closed=False)
    with pytest.raises(ValueError, match="not offered"):
        psychro_line("T", 300.0, P, T_RANGE)
