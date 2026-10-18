# -*- coding: utf-8 -*-
"""Lines placed through saturation states at even steps (set_lines(at_saturation=...))."""
import json

import numpy as np
import pytest

pytest.importorskip("CoolProp")

from coolplot import DiagramSpec, PropertyDiagram, PsychrometricChart  # noqa: E402
from coolplot.engine import plan  # noqa: E402
from coolplot.spec import IsolineSet, SaturationAnchor  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _requests(chart, key):
    domain = chart.engine.domain(chart.spec)
    return [r for r in plan(chart.spec, domain) if r.key == key]


def _labels(chart, key):
    return sorted(item.text for item in chart.update_scene() if item.id.startswith("iso/" + key + "/")
                  and item.id.endswith("/label"))


def test_isentropes_through_the_saturated_vapour_every_10_K():
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    chart.set_lines("s", at_saturation={"T": 10, "range": (-40, 60)}, labels=True)
    requests = _requests(chart, "s")
    T_sat_C = sorted(round(r.anchor_SI - 273.15, 9) for r in requests)
    assert T_sat_C == [-40.0, -30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    for r in requests:
        dew = chart.fluid.state_point("T", r.anchor_SI, "Q", 1.0)
        assert r.value_SI == pytest.approx(dew.s, rel=1e-10)
    # The layout leaves out labels where these lines crowd; every label placed names its saturation state
    labels = _labels(chart, "s")
    assert labels and all(text.startswith("T_sat=") and text.endswith(" deg C") for text in labels)
    from coolplot.compose import label_text
    zero = next(r for r in requests if abs(r.anchor_SI - 273.15) < 1e-9)
    assert label_text(chart.spec, "s", zero.value_SI, zero.anchor_SI) == "T_sat=0 deg C"


def test_the_liquid_side_and_the_lines_own_values():
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    chart.set_lines("rho", at_saturation={"T": 20, "Q": 0, "range": (-20, 40), "label": "value"}, labels=True)
    requests = _requests(chart, "rho")
    assert len(requests) == 4
    for r in requests:
        assert r.value_SI == pytest.approx(chart.fluid.state_point("T", r.anchor_SI, "Q", 0.0).rho, rel=1e-10)
    assert all(text.startswith("rho=") for text in _labels(chart, "rho"))
    chart.set_lines("rho", at_saturation={"T": 20, "Q": 0, "range": (-20, 40)}, labels=True)
    assert "T_sat,liq=0 deg C" in _labels(chart, "rho")
    chart.set_lines("rho", at_saturation={"T": 20, "Q": 0.5, "range": (-20, 40)}, labels=True)
    assert "T(x=0.5)=20 deg C" in _labels(chart, "rho")


def test_a_blend_uses_its_dew_or_bubble_point():
    chart = PropertyDiagram("HEOS::R407C.mix", "ph", units="engineering", tp_limits="ACHP")
    chart.set_lines("s", at_saturation={"T": 20, "Q": 1, "range": (-20, 20)})
    dew = {round(r.anchor_SI, 6): r.value_SI for r in _requests(chart, "s")}
    chart.set_lines("s", at_saturation={"T": 20, "Q": 0, "range": (-20, 20)})
    bubble = {round(r.anchor_SI, 6): r.value_SI for r in _requests(chart, "s")}
    assert sorted(dew) == sorted(bubble) == [253.15, 273.15, 293.15]
    for T in dew:   # dew point and bubble point of the blend at the same temperature
        assert dew[T] == pytest.approx(chart.fluid.state_point("T", T, "Q", 1.0).s, rel=1e-9)
        assert bubble[T] == pytest.approx(chart.fluid.state_point("T", T, "Q", 0.0).s, rel=1e-9)
        assert dew[T] - bubble[T] > 500.0


def test_steps_are_round_in_the_units_shown():
    ip = PropertyDiagram("HEOS::R290", "ph", units="IP", tp_limits="ACHP")
    ip.set_lines("s", at_saturation={"T": 20, "range": (0, 100)})
    T_F = sorted(r.anchor_SI * 1.8 - 459.67 for r in _requests(ip, "s"))
    assert T_F == pytest.approx([0.0, 20.0, 40.0, 60.0, 80.0, 100.0], abs=1e-9)
    bar = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    bar.set_lines("T", at_saturation={"p": 5, "range": (1, 22)}, labels=True)
    requests = _requests(bar, "T")
    assert sorted(round(r.anchor_SI / 1e5, 9) for r in requests) == [5.0, 10.0, 15.0, 20.0]
    for r in requests:   # an isotherm through a saturation pressure is at the saturation temperature
        assert r.value_SI == pytest.approx(bar.fluid.state_point("p", r.anchor_SI, "Q", 1.0).T, rel=1e-10)
    assert "p_sat=10 bar" in _labels(bar, "T")


def test_the_steps_stop_below_the_critical_point_and_inside_the_chart():
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    chart.set_lines("s", at_saturation={"T": 10})
    T_sat = [r.anchor_SI for r in _requests(chart, "s")]
    T_crit = chart.fluid.critical["T"]
    box = chart.engine.domain(chart.spec).tp_box
    assert max(T_sat) < T_crit and min(T_sat) >= box[0] and len(T_sat) == 20


def test_wrong_requests_are_refused_with_a_reason():
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    with pytest.raises(ValueError, match="not both"):
        chart.set_lines("s", values=[1.5], at_saturation={"T": 10})
    with pytest.raises(ValueError, match="not both"):
        chart.set_lines("s", range=(1, 2), at_saturation={"T": 10})
    with pytest.raises(ValueError, match="saturation temperature 'T' or pressure 'p'"):
        chart.set_lines("s", at_saturation={"h": 10})
    with pytest.raises(ValueError, match="one step"):
        chart.set_lines("s", at_saturation={"T": 10, "p": 1})
    with pytest.raises(ValueError, match="positive"):
        chart.set_lines("s", at_saturation={"T": 0})
    with pytest.raises(ValueError, match="between 0 and 1"):
        chart.set_lines("s", at_saturation={"T": 10, "Q": 2})
    with pytest.raises(ValueError, match="label"):
        chart.set_lines("s", at_saturation={"T": 10, "label": "both"})
    with pytest.raises(ValueError, match="vapour quality"):
        chart.set_lines("Q", at_saturation={"T": 10})
    chart.set_lines("s", at_saturation={"T": 0.1})
    with pytest.raises(ValueError, match="larger step"):
        chart.update_scene()
    air = PsychrometricChart(T_range=(0, 40), W_range=(0, 20))
    with pytest.raises(ValueError, match="charts of a fluid"):
        air.set_lines("h", at_saturation={"T": 10})


def test_the_spec_record_round_trips_and_reads_1_0_records():
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    chart.set_lines("s", at_saturation={"T": 10, "Q": 0, "range": (-40, 60), "label": "value"})
    text = json.dumps(chart.spec.to_dict(), sort_keys=True)
    again = DiagramSpec.from_dict(json.loads(text))
    assert again == chart.spec and json.dumps(again.to_dict(), sort_keys=True) == text
    anchor = again.isolines[0].anchor
    assert anchor == SaturationAnchor("T", 10.0, 0.0, (233.15, 333.15), "value")
    record = IsolineSet("T").to_dict()
    del record["anchor"]   # as written by 1.0
    assert IsolineSet.from_dict(record) == IsolineSet("T")


def test_anchored_lines_share_the_cache_with_the_same_values_given_explicitly():
    chart = PropertyDiagram("HEOS::R290", "ph", units="SI", tp_limits="ACHP")
    chart.set_lines("s", at_saturation={"T": 10, "range": (-20, 20)})
    chart.update_scene()
    values = [r.value_SI for r in _requests(chart, "s")]
    misses = chart.cache.misses
    chart.set_lines("s", values=values)
    chart.update_scene()
    assert chart.cache.misses == misses
    assert all(r.anchor_SI is None for r in _requests(chart, "s"))


def test_a_domain_of_another_spec_is_refused():
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    domain = chart.engine.domain(chart.spec)   # made before the anchored family exists
    chart.set_lines("s", at_saturation={"T": 10})
    with pytest.raises(ValueError, match="another spec"):
        plan(chart.spec, domain)


def test_the_drawn_lines_pass_through_their_saturation_states():
    chart = PropertyDiagram("HEOS::R290", "ph", units="SI", tp_limits="ACHP")
    chart.set_lines("s", at_saturation={"T": 20, "range": (-20, 40)})
    scene = chart.update_scene()
    for r in _requests(chart, "s"):
        dew = chart.fluid.state_point("T", r.anchor_SI, "Q", 1.0)
        line = scene[r.item_id]
        x, y = np.asarray(line.x), np.asarray(line.y)
        ok = np.isfinite(x) & np.isfinite(y)
        # the p-h line at constant s reaches the dew pressure at the dew enthalpy
        h_at_p = np.interp(np.log(dew.p), np.log(y[ok])[::-1] if y[ok][0] > y[ok][-1] else np.log(y[ok]),
                           x[ok][::-1] if y[ok][0] > y[ok][-1] else x[ok])
        assert h_at_p == pytest.approx(dew.h, rel=2e-3)
