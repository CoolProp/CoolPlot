# -*- coding: utf-8 -*-
"""Lines placed through saturation states at even steps (set_lines(at_saturation=...))."""
import json

import numpy as np
import pytest

pytest.importorskip("CoolProp")

from coolplot import DiagramSpec, PropertyDiagram, PsychrometricChart  # noqa: E402
from coolplot.core.floats import is_zero, same_numbers  # noqa: E402
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
    assert same_numbers(T_sat_C, [-40.0, -30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    for r in requests:
        dew = chart.fluid.state_point("T", r.anchor_SI, "Q", 1.0)
        assert r.value_SI == pytest.approx(dew.s, rel=1e-10)
    # The labels show the lines' own entropy, like the labels of any other line
    # (the layout leaves out labels where these lines crowd)
    from coolplot.compose import label_text
    zero = next(r for r in requests if abs(r.anchor_SI - 273.15) < 1e-9)
    s_zero = label_text(chart.spec, "s", zero.value_SI, zero.anchor_SI)
    assert s_zero == label_text(chart.spec, "s", zero.value_SI) == "s=%.4g kJ/kg/K" % (zero.value_SI / 1e3)
    labels = _labels(chart, "s")
    assert labels and all(text.startswith("s=") and text.endswith(" kJ/kg/K") for text in labels)
    # Asked for, they name the saturation state instead
    chart.set_lines("s", at_saturation={"T": 10, "range": (-40, 60), "label": "saturation"}, labels=True)
    assert label_text(chart.spec, "s", zero.value_SI, zero.anchor_SI) == "T_sat=0 deg C"
    labels = _labels(chart, "s")
    assert labels and all(text.startswith("T_sat=") and text.endswith(" deg C") for text in labels)


def test_the_liquid_side_and_the_saturation_labels():
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    chart.set_lines("rho", at_saturation={"T": 20, "Q": 0, "range": (-20, 40)}, labels=True)
    requests = _requests(chart, "rho")
    assert len(requests) == 4
    for r in requests:
        assert r.value_SI == pytest.approx(chart.fluid.state_point("T", r.anchor_SI, "Q", 0.0).rho, rel=1e-10)
    assert all(text.startswith("rho=") for text in _labels(chart, "rho"))
    assert chart.line_sets()["rho"].anchor.label == "value"
    chart.set_lines("rho", at_saturation={"T": 20, "Q": 0, "range": (-20, 40), "label": "saturation"}, labels=True)
    assert "T_sat,liq=0 deg C" in _labels(chart, "rho")
    chart.set_lines("rho", at_saturation={"T": 20, "Q": 0.5, "range": (-20, 40), "label": "saturation"},
                    labels=True)
    assert "T(x=0.5)=20 deg C" in _labels(chart, "rho")


def test_a_blend_uses_its_dew_or_bubble_point():
    chart = PropertyDiagram("HEOS::R407C.mix", "ph", units="engineering", tp_limits="ACHP")
    chart.set_lines("s", at_saturation={"T": 20, "Q": 1, "range": (-20, 20)})
    dew = {round(r.anchor_SI, 6): r.value_SI for r in _requests(chart, "s")}
    chart.set_lines("s", at_saturation={"T": 20, "Q": 0, "range": (-20, 20)})
    bubble = {round(r.anchor_SI, 6): r.value_SI for r in _requests(chart, "s")}
    assert same_numbers(sorted(dew), [253.15, 273.15, 293.15])
    assert same_numbers(sorted(bubble), [253.15, 273.15, 293.15])
    for T in dew:   # dew point and bubble point of the blend at the same temperature
        assert dew[T] == pytest.approx(chart.fluid.state_point("T", T, "Q", 1.0).s, rel=1e-9)
        assert bubble[T] == pytest.approx(chart.fluid.state_point("T", T, "Q", 0.0).s, rel=1e-9)
        assert dew[T] - bubble[T] > 500.0


def test_steps_are_round_in_the_units_shown():
    ip = PropertyDiagram("HEOS::R290", "ph", units="IP", tp_limits="ACHP")
    ip.set_lines("s", at_saturation={"T": 20, "range": (0, 100)})
    T_F = sorted(r.anchor_SI * 1.8 - 459.67 for r in _requests(ip, "s"))
    assert T_F == pytest.approx([0.0, 20.0, 40.0, 60.0, 80.0, 100.0], abs=1e-11)   # no drift of the step
    bar = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    bar.set_lines("T", at_saturation={"p": 5, "range": (1, 22), "label": "saturation"}, labels=True)
    requests = _requests(bar, "T")
    assert same_numbers(sorted(round(r.anchor_SI / 1e5, 9) for r in requests), [5.0, 10.0, 15.0, 20.0])
    for r in requests:   # an isotherm through a saturation pressure is at the saturation temperature
        assert r.value_SI == pytest.approx(bar.fluid.state_point("p", r.anchor_SI, "Q", 1.0).T, rel=1e-10)
    assert "p_sat=10 bar" in _labels(bar, "T")


def test_the_steps_stop_below_the_critical_point_and_inside_the_chart():
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    chart.set_lines("s", at_saturation={"T": 10})
    T_sat = [r.anchor_SI for r in _requests(chart, "s")]
    T_crit = chart.fluid.critical["T"]
    box = chart.engine.domain(chart.spec).tp_box
    assert max(T_sat) < T_crit and T_crit - max(T_sat) < 10.0 + 1e-9   # up to the last step below the critical point
    assert min(T_sat) >= box[0] and min(T_sat) - box[0] < 10.0 + 1e-9 and len(T_sat) >= 15


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
    with pytest.raises(ValueError, match="larger step"):   # reported by set_lines, not at the next draw
        chart.set_lines("s", at_saturation={"T": 0.1})
    assert "s" not in chart.line_sets()
    # the quality may be written x, as the labels write it
    chart.set_lines("s", at_saturation={"T": 20, "x": 0, "range": (0, 20)})
    assert is_zero(chart.line_sets()["s"].anchor.Q)
    with pytest.raises(ValueError, match="not both"):
        IsolineSet("s", range_SI=(1.0, 2.0), anchor=SaturationAnchor())
    air = PsychrometricChart(T_range=(0, 40), W_range=(0, 20))
    with pytest.raises(ValueError, match="charts of a fluid"):
        air.set_lines("h", at_saturation={"T": 10})


def test_the_spec_record_round_trips_and_reads_1_0_records():
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
    chart.set_lines("s", at_saturation={"T": 10, "Q": 0, "range": (-40, 60), "label": "saturation"})
    text = json.dumps(chart.spec.to_dict(), sort_keys=True)
    again = DiagramSpec.from_dict(json.loads(text))
    assert again == chart.spec and json.dumps(again.to_dict(), sort_keys=True) == text
    anchor = again.isolines[0].anchor
    assert anchor == SaturationAnchor("T", 10.0, 0.0, (233.15, 333.15), "saturation")
    record = IsolineSet("T").to_dict()
    del record["anchor"]   # as written by 1.0
    assert IsolineSet.from_dict(record) == IsolineSet("T")


def test_anchored_lines_share_the_cache_with_the_same_values_given_explicitly():
    chart = PropertyDiagram("HEOS::R290", "ph", units="SI", tp_limits="ACHP")
    chart.set_lines("s", at_saturation={"T": 10, "range": (253.15, 293.15)})   # SI units: kelvin
    chart.update_scene()
    values = [r.value_SI for r in _requests(chart, "s")]
    # round in the chart's units, here kelvin
    assert same_numbers(sorted(round(r.anchor_SI, 9) for r in _requests(chart, "s")), [260.0, 270.0, 280.0, 290.0])
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


def test_states_that_cannot_be_computed_are_left_out_with_a_warning():
    from coolplot.thermo.fluid import Fluid
    from coolplot.thermo.provider import saturation_anchor_values
    from coolplot.core.units import ENGINEERING
    fluid = Fluid("HEOS::R290")
    real = fluid.state_point

    def refuse_zero(k1, v1, k2, v2):
        if k1 == "T" and abs(v1 - 273.15) < 1e-9:
            raise ValueError("no state")
        return real(k1, v1, k2, v2)
    fluid.state_point = refuse_zero
    with pytest.warns(UserWarning, match="1 of 3 saturation states"):
        pairs = saturation_anchor_values(fluid, "s", "T", 10.0, 1.0, (263.15, 283.15), (100.0, 400.0, 1.0, 1e8),
                                         1e-7, ENGINEERING["T"])
    assert same_numbers([round(t, 2) for t, _ in pairs], [263.15, 283.15])


def test_a_fluid_without_a_saturation_curve_is_refused_when_the_lines_are_set():
    chart = PropertyDiagram("INCOMP::MEG[0.3]", "Ts", units="engineering", tp_limits=[260.0, 360.0, 1e5, 1e6])
    with pytest.raises(ValueError, match="no saturation curve|has none"):
        chart.set_lines("h", at_saturation={"T": 10})
