# -*- coding: utf-8 -*-
"""Psychrometric charts: humid-air lines, air processes and the chart facade."""
import json

import numpy as np
import pytest

pytest.importorskip("CoolProp")
from CoolProp.HumidAirProp import HAPropsSI  # noqa: E402

from coolplot.psychrometric import PsychrometricChart  # noqa: E402
from coolplot.render.svg import SvgRenderer  # noqa: E402
from coolplot.spec.psychro import PsychroSpec  # noqa: E402
from coolplot.thermo.humid_air import (air_state, chart_ranges, default_values, psychro_line,  # noqa: E402
                                       saturation_W)

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


@pytest.mark.parametrize("key, value", [("Twb", 288.15), ("h", 50e3), ("v", 0.86)])
def test_lines_start_on_the_saturation_curve(key, value):
    curve = psychro_line(key, value, P, T_RANGE, points=40)
    assert curve.y[0] == pytest.approx(saturation_W(curve.x[0], P), rel=1e-6)
    if key == "Twb":
        assert curve.x[0] == pytest.approx(value)   # on saturation, wet bulb equals dry bulb


def test_default_values_are_round():
    ranges = chart_ranges(P, T_RANGE, (0.0, 0.025))
    assert default_values("RH", ranges) == pytest.approx([0.1 * i for i in range(1, 11)])
    twb_C = np.array(default_values("Twb", ranges)) - 273.15
    assert np.allclose(twb_C % 5.0, 0.0, atol=1e-6) or np.allclose(twb_C % 5.0, 5.0, atol=1e-6)
    assert np.allclose(np.array(default_values("h", ranges)) % 10e3, 0.0, atol=1e-3)


@pytest.fixture
def chart():
    c = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))
    c.set_default_lines()
    c.add_process("Air conditioning", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}, {"T": 20, "W": 8.9}])
    return c


def test_chart_scene(chart):
    scene = chart.update_scene()
    groups = {i.group for i in scene}
    assert {"psy/RH", "psy/Twb", "psy/h", "psy/v", "air/Air conditioning"} <= groups
    assert scene["psy/RH/1"].role == "saturation"
    assert scene.axes.x_label == "Dry-bulb temperature T / deg C"
    assert scene.axes.y_label == "Humidity ratio W / g/kg"
    assert scene.axes.x_limits == (-10.0, 45.0)
    labels = [i for i in scene if i.role == "isoline_label"]
    assert len(labels) > 10 and any(t.text == "RH=50 %" for t in labels)
    states = chart.process_states("Air conditioning")
    assert states[2].W == pytest.approx(8.9e-3) and states[1].RH == pytest.approx(0.95)


def test_processes_fail_early_and_leave_the_chart_unchanged(chart):
    before = chart.spec
    with pytest.raises(ValueError, match="State 1"):
        chart.add_process("bad", [{"T": 20, "RH": 150}, {"T": 25, "RH": 50}])
    with pytest.raises(ValueError):
        chart.add_process("bad", [{"T": 20}])
    assert chart.spec == before


def test_lines_are_computed_once(chart):
    chart.update_scene()
    misses = chart.cache.misses
    chart.theme = "dark"
    chart.add_process("Heating", [{"T": 5, "RH": 80}, {"T": 25, "W": 4.3}])
    chart.update_scene()
    assert chart.cache.misses == misses


def test_spec_round_trips_through_json(chart):
    data = json.loads(json.dumps(chart.spec.to_dict()))
    assert PsychroSpec.from_dict(data) == chart.spec


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
    assert high.spec.p_Pa == pytest.approx(0.8e5)
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
