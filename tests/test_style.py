# -*- coding: utf-8 -*-
"""Style values and themes; no property calculations except at the end."""
import json

import pytest

from coolplot.style import (CSS_COLORS, AxesStyle, Font, LineStyle, MarkerStyle, TextStyle,
                            dash_pattern_pt, parse_color)
from coolplot.style.theme import CLASSIC, DARK, DEFAULT, PRINT, THEMES, Theme, get_theme


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
    from coolplot import PropertyDiagram
    from coolplot.render.svg import SvgRenderer
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    d.set_lines("Q", num=3)
    d.set_lines("T", values=[0.0, 20.0], points=40)
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
    d.set_line_style("T", width_pt=2.0)
    assert d.update_scene()["iso/T/273.15"].style.width_pt == 2.0
    d.set_line_style("T")
    assert d.update_scene()["iso/T/273.15"].style.width_pt == DARK.isoline.width_pt


def test_theme_loading_is_strict():
    for bad in ({"axes": {"grid_major": {"colour": "red"}}},
                {"axes": {"grid_major": {"color": "blurple"}}},
                {"processes": [{"width_pt": -1.0}]}):
        with pytest.raises((TypeError, ValueError)):
            Theme.from_dict(bad)


def test_presets_cannot_be_changed_by_accident():
    with pytest.raises(TypeError):
        CLASSIC.isoline_colors["T"] = "red"
    custom = DEFAULT.with_(slot_dashes=((4, 2), "dashed"))
    again = Theme.from_dict(json.loads(json.dumps(custom.to_dict())))
    assert again == custom and hash(again) == hash(custom)


def test_colour_fields_without_alpha_refuse_partial_transparency():
    assert AxesStyle(background="#ffffff00").background is None     # fully transparent = no paint
    with pytest.raises(ValueError):
        AxesStyle(background="#ffffff80")
    with pytest.raises(ValueError):
        MarkerStyle(edge_color="#00000080")
    with pytest.raises(ValueError):
        Theme(categorical=("#2a78d680",))
    with pytest.raises(ValueError):
        LineStyle(width_pt=float("inf"))
    with pytest.raises(ValueError):
        LineStyle(dash=(float("nan"), 1.0))


@pytest.mark.parametrize("path, value", [
    (("axes", "grid_major"), "red"),            # a colour where a line style belongs
    (("axes", "frame_width_pt"), "3"),          # a number written as text
    (("axes", "legend", "visible"), "no"),      # a switch written as text
    (("isoline", "width_pt"), True),            # a switch where a number belongs
    (("categorical",), "#ff0000"),              # a string where a list belongs
])
def test_theme_loading_is_strict(path, value):
    import json
    from coolplot.style.theme import Theme, get_theme
    data = json.loads(json.dumps(get_theme("default").to_dict()))
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises((TypeError, ValueError)):
        Theme.from_dict(data)


# ---------------------------------------------------------------------------
# Fonts in the matplotlib backend
# ---------------------------------------------------------------------------
def _mpl_renderer(**kwargs):
    pytest.importorskip("matplotlib")
    from coolplot.render.mpl import MatplotlibRenderer
    return MatplotlibRenderer(use_pyplot=False, **kwargs)


def _text_scene(font, text="T = 25 deg C"):
    from coolplot.scene import AxesSpec, Scene, Text
    from coolplot.style.values import TextStyle
    return Scene(AxesSpec(x_limits=(0.0, 1.0), y_limits=(0.0, 1.0), title="Price $5 and $6"),
                 [Text(id="t", x=0.5, y=0.5, text=text, style=TextStyle(font=font))])


def test_texts_are_plain_text_not_math():
    from coolplot.style.values import Font
    renderer = _mpl_renderer()
    renderer.sync(_text_scene(Font(), text="costs $5 or $6"))
    for artist in (renderer.backend_object("t"), renderer.ax.title):
        assert artist.get_parse_math() is False and artist.get_usetex() is False


def test_font_files_strict_fonts_and_fonts_used(tmp_path):
    import matplotlib
    from coolplot.style.values import Font
    # A font that is not installed: DejaVu Sans Mono under a family name of its own
    from fontTools.ttLib import TTFont
    font = TTFont(matplotlib.get_data_path() + "/fonts/ttf/DejaVuSansMono.ttf")
    for record in font["name"].names:
        if record.nameID in (1, 4, 16):
            record.string = "CoolPlot Test Mono"
        elif record.nameID == 6:
            record.string = "CoolPlotTestMono"
    copy = tmp_path / "CoolPlotTestMono.ttf"
    font.save(str(copy))
    brand = Font(family=("CoolPlot Test Mono", "sans-serif"), files=(str(copy),))
    renderer = _mpl_renderer(strict_fonts=True)   # strict: the file must really be used
    renderer.sync(_text_scene(brand))
    assert renderer.describe_item("t")["font_used"] == "CoolPlot Test Mono"
    assert renderer.fonts_used()[str(copy)] == "CoolPlot Test Mono"
    assert Font(family=("Brand",), files=copy).files == (str(copy),)   # one pathlib.Path
    # A missing first family falls back, unless strict_fonts is on
    missing = Font(family=("No Such Font", "DejaVu Sans", "sans-serif"))
    renderer = _mpl_renderer()
    renderer.sync(_text_scene(missing))
    assert renderer.describe_item("t")["font_used"] == "DejaVu Sans"
    with pytest.raises(ValueError, match="No Such Font"):
        _mpl_renderer(strict_fonts=True).sync(_text_scene(missing))
    with pytest.warns(UserWarning, match="does not exist"):
        _mpl_renderer().sync(_text_scene(Font(family=("DejaVu Sans",), files=(str(tmp_path / "gone.ttf"),))))


def test_font_files_survive_json():
    from coolplot.style.values import Font, TextStyle, style_from_dict, style_to_dict
    style = TextStyle(font=Font(family=("Brand", "sans-serif"), files=("fonts/Brand.ttf",)))
    assert style_from_dict(TextStyle, style_to_dict(style)) == style


def test_a_unit_system_keeps_its_own_copy_of_the_units():
    from coolplot.core.units import Unit, UnitSystem
    units = {"p": Unit("bar", 1e-5)}
    system = UnitSystem("mine", units)
    units["p"] = Unit("Pa")
    assert system["p"].label == "bar"


def test_the_kit_treats_a_grid_without_colour_as_no_grid():
    from coolplot.render.testing import expected_axes
    from coolplot.scene import AxesSpec, Scene
    from coolplot.style.values import AxesStyle, LineStyle
    scene = Scene(AxesSpec(x_label="x", y_label="y", style=AxesStyle(grid_major=LineStyle(color=None))), [])
    assert "grid_width_pt" not in expected_axes(scene, True)
