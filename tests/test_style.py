# -*- coding: utf-8 -*-
"""Style values and themes; no property calculations except at the end."""
import json

import pytest

from CoolPlot.style import (CSS_COLORS, AxesStyle, Font, LineStyle, MarkerStyle, TextStyle,
                            dash_pattern_pt, parse_color)
from CoolPlot.theme import CLASSIC, DARK, DEFAULT, PRINT, THEMES, Theme, get_theme


def test_parse_color():
    assert parse_color("Red") == ("#ff0000", 1.0)
    assert parse_color("#ABC") == ("#aabbcc", 1.0)
    assert parse_color("#00ff0080") == ("#00ff00", 128 / 255)
    assert parse_color("#0f08")[1] == pytest.approx(0x88 / 255)
    assert parse_color("none") == (None, 0.0)
    for bad in ("reddish", "#12345", "rgb(1,2,3)", ""):
        with pytest.raises(ValueError):
            parse_color(bad)


def test_css_names_match_matplotlib():
    colors = pytest.importorskip("matplotlib.colors")
    assert CSS_COLORS == {k: v.lower() for k, v in colors.CSS4_COLORS.items()}


def test_styles_normalise_and_validate():
    line = LineStyle(color="#ff000080", alpha=0.5)
    assert line.color == "#ff0000" and line.alpha == pytest.approx(0.5 * 128 / 255)
    assert LineStyle(dash=[2, 1]).dash == (2.0, 1.0)
    for kwargs in ({"dash": "wavy"}, {"dash": (1.0,)}, {"width_pt": -1}, {"alpha": 2},
                   {"cap": "pointy"}, {"color": "blurple"}):
        with pytest.raises(ValueError):
            LineStyle(**kwargs)
    with pytest.raises(ValueError):
        MarkerStyle(shape="*")
    with pytest.raises(ValueError):
        TextStyle(h_align="middle")
    with pytest.raises(ValueError):
        Font(weight="heavy")
    assert Font(family="serif").family == ("serif",)


def test_dash_patterns_scale_with_width_but_not_below_one_point():
    assert dash_pattern_pt("solid", 2.0) == ()
    assert dash_pattern_pt("dashed", 2.0) == (7.4, 3.2)
    assert dash_pattern_pt("dashed", 0.5) == (3.7, 1.6)
    assert dash_pattern_pt((4.0, 1.0), 3.0) == (4.0, 1.0)  # explicit lengths are not scaled


def test_theme_round_trip_through_json():
    for theme in THEMES.values():
        data = json.loads(json.dumps(theme.to_dict()))
        assert Theme.from_dict(data) == theme
    with pytest.raises(TypeError):
        Theme.from_dict({"colour": "red"})


def test_presets():
    assert get_theme("Dark") is DARK and get_theme(None) is DEFAULT
    assert get_theme(PRINT) is PRINT
    with pytest.raises(ValueError):
        get_theme("neon")
    assert CLASSIC.axes.legend.visible is False and CLASSIC.axes.grid_major is None


def test_isoline_colours_follow_the_quantity_not_the_rank():
    ph = ["T", "s", "rho"]          # what a ph chart offers, in fixed order
    hs = ["T", "p", "rho"]
    ts = ["p", "h", "rho"]
    slot = DEFAULT.categorical
    assert DEFAULT.isoline_style("T", ph).color == DEFAULT.isoline_style("T", hs).color == slot[0]
    assert DEFAULT.isoline_style("rho", ph).color == DEFAULT.isoline_style("rho", ts).color == slot[2]
    assert DEFAULT.isoline_style("p", ts).color == slot[0]
    # The print theme separates families by dash pattern instead
    assert [PRINT.isoline_style(k, ph).dash for k in ph] == ["solid", "dashed", "dotted"]
    assert len({PRINT.isoline_style(k, ph).color for k in ph}) == 1
    # Pinned colours win over slots
    assert CLASSIC.isoline_style("T", ph).color == "#8b0000"
    assert DEFAULT.with_isoline_color("T", "purple").isoline_style("T", ph).color == "#800080"


def test_theme_validation():
    with pytest.raises(ValueError):
        Theme(categorical=("nope",))
    with pytest.raises(ValueError):
        Theme(slot_dashes=("wavy",))
    with pytest.raises(ValueError):
        AxesStyle(tick_direction="sideways")


def test_switching_theme_recomputes_nothing():
    pytest.importorskip("CoolProp")
    from CoolPlot import PropertyDiagram
    from CoolPlot.render.svg import SvgRenderer
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    d.set_isolines("Q", num=3)
    d.set_isolines("T", values=[0.0, 20.0], points=40)
    r = SvgRenderer()
    r.sync(d.update_scene())
    misses = d.cache.misses
    d.theme = "dark"
    report = r.sync(d.update_scene())
    assert d.cache.misses == misses
    # The quality line uses the same muted ink in both themes, so it stays untouched
    assert report.axes_changed and len(report.updated) == 4 and report.unchanged == 1
    scene = d.scene
    assert scene["iso/T/273.15"].role == "isoline"
    assert scene["iso/Q/0"].role == "saturation" and scene["iso/Q/0.5"].role == "quality"
    assert [text for text, _ in scene.legend_entries()] == ["Saturation", "Vapour quality", "Temperature"]
    d.set_isoline_style("T", width_pt=2.0)
    assert d.update_scene()["iso/T/273.15"].style.width_pt == 2.0
    d.set_isoline_style("T")
    assert d.update_scene()["iso/T/273.15"].style.width_pt == DARK.isoline.width_pt
