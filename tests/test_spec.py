# -*- coding: utf-8 -*-
"""Specs and settings: plain data that round-trips through JSON."""
import json

import pytest

from coolplot.core.limits import Relative, TpLimits
from coolplot.core.state import StatePoint
from coolplot.core.units import EUR, Unit
from coolplot.spec import (CalcSettings, DiagramSpec, FluidSpec, IsolineSet, LabelSettings, PageSettings,
                           ProcessSpec, Settings, get_settings)
from coolplot.style.values import LineStyle


def _json(data):
    return json.loads(json.dumps(data))


@pytest.mark.parametrize("text, expected", [
    ("R290", FluidSpec("HEOS", ("R290",))),
    ("HEOS::R290", FluidSpec("HEOS", ("R290",))),
    ("REFPROP::R32[0.7]&R125[0.3]", FluidSpec("REFPROP", ("R32", "R125"), (0.7, 0.3))),
    ("INCOMP::MEG[0.3]", FluidSpec("INCOMP", ("MEG",), (0.3,), "mass")),
    ("INCOMP::MEG-30%", FluidSpec("INCOMP", ("MEG-30%",), (), "mass")),
])
def test_fluid_strings(text, expected):
    spec = FluidSpec.parse(text)
    assert spec == expected
    assert FluidSpec.parse(str(spec)) == spec
    assert FluidSpec.from_dict(_json(spec.to_dict())) == spec


@pytest.mark.parametrize("text", ["R32[0.7]&R125", "R32[0.7]&R125[0.4]", "R32&R125", "R290[x]", "R290[1.5]", ""])
def test_bad_fluid_strings(text):
    with pytest.raises(ValueError):
        FluidSpec.parse(text)


def test_fluid_interactions_are_validated():
    spec = FluidSpec("HEOS", ("R32", "R125"), (0.5, 0.5), interactions=[[0, 1, "betaT", "1.02"]])
    assert spec.interactions == ((0, 1, "betaT", 1.02),)
    hash(spec)
    with pytest.raises(ValueError):
        FluidSpec("HEOS", ("R32", "R125"), (0.5, 0.5), interactions=[(0, 2, "betaT", 1.0)])
    with pytest.raises(ValueError):
        FluidSpec("HEOS", ("R32",), basis="weight")


def test_settings_presets_and_derivation():
    assert get_settings(None) == get_settings("screen") == Settings()
    fast = get_settings("interactive")
    assert fast.calc.points < Settings().calc.points
    assert get_settings("print").look.name == "print"
    changed = Settings().with_(calc={"points": 80}, look="dark", labels={"digits": 3}, page={"font_scale": 1.5})
    assert (changed.calc.points, changed.look.name, changed.labels.digits, changed.page.font_scale) == \
        (80, "dark", 3, 1.5)
    assert changed.calc.saturation_points == Settings().calc.saturation_points
    with pytest.raises(ValueError):
        get_settings("fancy")


@pytest.mark.parametrize("make", [
    lambda: CalcSettings(points=1),
    lambda: CalcSettings(saturation_spacing="cubic"),
    lambda: CalcSettings(critical_margin=0.0),
    lambda: CalcSettings(warn_failed_fraction=2.0),
    lambda: LabelSettings(position=1.5),
    lambda: LabelSettings(digits=0),
    lambda: PageSettings(width_pt=0.0),
])
def test_invalid_settings(make):
    with pytest.raises(ValueError):
        make()


def test_settings_json_round_trip():
    for name in ("screen", "print", "publication", "interactive"):
        settings = get_settings(name)
        assert Settings.from_dict(_json(settings.to_dict())) == settings
    with pytest.raises(ValueError):
        Settings.from_dict({"calc": {"pionts": 10}})


def test_label_number_format():
    assert LabelSettings(digits=3).format_value(12.345) == "12.3"
    assert LabelSettings().format_value(0.0) == "0"


def _state(T):
    return StatePoint(T=T, p=1e5, h=4e5, s=1.7e3, rho=2.0, u=3.5e5, Q=-1.0)


def test_diagram_spec_json_round_trip():
    units = EUR.with_unit("p", Unit("MPa", 1e-6), name="EUR-MPa")
    spec = DiagramSpec(
        fluid="HEOS::R32[0.7]&R125[0.3]", diagram="Ts", units=units,
        limits=TpLimits(250.0, Relative(1.1), None, 5e6), settings="publication",
        isolines=(IsolineSet("p", num=5, rounding=True, labels=True),
                  IsolineSet("Q", values_SI=(0.0, 0.5, 1.0), points=80)),
        processes=(ProcessSpec("cycle", (_state(280.0), _state(300.0)), (_state(280.0),),
                               line_style=LineStyle(color="red", dash=(4.0, 2.0))),),
        style_overrides=(("h", (("color", "#123456"), ("dash", (2.0, 1.0)))),),
        view_SI=((1000.0, 2000.0), None), title="R410A-like")
    hash(spec)
    again = DiagramSpec.from_dict(_json(spec.to_dict()))
    assert again == spec
    assert again.style_override("h") == {"color": "#123456", "dash": (2.0, 1.0)}


def test_diagram_spec_derivation_keeps_order():
    spec = DiagramSpec("R290", isolines=(IsolineSet("T"), IsolineSet("s")))
    spec2 = spec.with_isolines(IsolineSet("T", num=3))
    assert [s.key for s in spec2.isolines] == ["T", "s"] and spec2.isoline_set("T").num == 3
    assert spec.isoline_set("T").num == 15   # the original is unchanged
    assert [s.key for s in spec2.without_isolines("T").isolines] == ["s"]
    spec3 = spec.with_style_override("T", color="red").with_style_override("T", width_pt=2.0)
    assert spec3.style_override("T") == {"color": "red", "width_pt": 2.0}
    assert spec3.with_style_override("T").style_override("T") == {}


def test_diagram_spec_rejects_bad_content():
    with pytest.raises(ValueError):
        DiagramSpec("R290", diagram="ph", isolines=(IsolineSet("h"),))   # vertical lines in ph
    with pytest.raises(ValueError):
        DiagramSpec("R290", isolines=(IsolineSet("T"), IsolineSet("T", num=3)))
    with pytest.raises(ValueError):
        DiagramSpec("R290", processes=(ProcessSpec("a"), ProcessSpec("a")))
    with pytest.raises(TypeError):
        ProcessSpec("a", line_states=({"T": 300.0},))
