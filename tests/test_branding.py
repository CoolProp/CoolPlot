# -*- coding: utf-8 -*-
"""Branding (badge and watermark), SVG page size, save() without pyplot,
uncached_curves() and the warning for pseudo-pure blends (1.2)."""
import base64
import re
import struct
import warnings
import zlib

import pytest

from coolplot import BrandingSettings, PropertyDiagram, Settings
from coolplot.compose.branding import corner_box
from coolplot.compose.layout import Frame
from coolplot.core.images import PNG, SVG, load_picture, picture_from_bytes
from coolplot.scene import CORNERS, Scene, axes_to_dict
from coolplot.thermo.references import fluid_references, latex_to_text

A4_LANDSCAPE = {"width_pt": 297 * 72 / 25.4, "height_pt": 210 * 72 / 25.4}
SVG_LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 50">'
            '<rect width="200" height="50" fill="#02998a"/></svg>')


def _png(width: int, height: int, rgba=(2, 153, 138, 255)) -> bytes:
    """A PNG of one colour, written without any imaging library."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    row = b"\x00" + bytes(rgba) * width
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


@pytest.fixture
def logo_files(tmp_path):
    png, svg = tmp_path / "logo.png", tmp_path / "logo.svg"
    png.write_bytes(_png(400, 100))
    svg.write_text(SVG_LOGO)
    return str(svg), str(png)


def _diagram(branding=None, fluid="R290", page=A4_LANDSCAPE):
    d = PropertyDiagram(fluid, "ph", units="engineering", tp_limits="ACHP")
    d.settings = d.settings.with_(page=page, branding=branding)
    d.set_default_lines(labels=True)
    return d


# Pictures ------------------------------------------------------------------
def test_pictures_are_read_from_png_svg_files_and_data_uris(logo_files):
    svg, png = (load_picture(p) for p in logo_files)
    assert (svg.mime, svg.width_px, svg.height_px) == (SVG, 200.0, 50.0)
    assert (png.mime, png.width_px, png.height_px) == (PNG, 400.0, 100.0)
    assert load_picture(png.data_uri()) == png
    assert picture_from_bytes(_png(3, 7)).aspect == pytest.approx(7 / 3)


def test_other_files_are_refused(tmp_path):
    jpeg = tmp_path / "logo.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)
    with pytest.raises(ValueError, match="neither a PNG nor an SVG"):
        load_picture(str(jpeg))
    with pytest.raises(ValueError, match="cannot read"):
        load_picture(str(tmp_path / "missing.png"))
    with pytest.raises(ValueError, match="viewBox"):
        picture_from_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')


# Settings ------------------------------------------------------------------
def test_branding_settings_validate_and_round_trip(logo_files):
    assert not BrandingSettings().has_badge
    with pytest.raises(ValueError, match="badge location"):
        BrandingSettings(location="middle")
    with pytest.raises(ValueError, match="references style"):
        BrandingSettings(references="long")
    with pytest.raises(ValueError, match="watermark_opacity"):
        BrandingSettings(watermark_opacity=2.0)
    settings = Settings().with_(branding=dict(logo=logo_files, references="full", lines="example.com"))
    assert settings.branding.lines == ("example.com",)
    assert Settings.from_dict(settings.to_dict()) == settings
    # A record from before 1.2 has no branding part
    old = settings.to_dict()
    del old["branding"]
    assert Settings.from_dict(old).branding == BrandingSettings()


def test_an_unbranded_chart_has_no_badge_and_an_unchanged_record():
    d = _diagram()
    axes = d.update_scene().axes
    assert axes.badge is None and axes.watermark is None
    record = axes_to_dict(axes)
    assert "badge" not in record and "watermark" not in record


# References ----------------------------------------------------------------
def test_references_name_the_equation_of_state():
    assert fluid_references("R290") == ("R290: Lemmon et al. (2009)",)
    assert fluid_references("R290", "full") == ("R290: Lemmon et al., J. Chem. Eng. Data 54 (2009) 3141-3180",)
    blend = fluid_references("R407C.mix")
    assert [line.split(":")[0] for line in blend] == ["R32", "R125", "R134a", "Mixture model"]
    assert blend[-1] == "Mixture model: Lemmon and Jacobsen (2004)"
    from coolplot import HumidAirSpec
    assert fluid_references(HumidAirSpec(), "full") == ("Humid air: Herrmann et al., ASHRAE RP-1485 (2009)",)
    # Other backends are named without asking CoolProp for a state (REFPROP is not installed here)
    assert fluid_references("REFPROP::R290") == ("R290: REFPROP",)
    with pytest.raises(ValueError, match="reference style"):
        fluid_references("R290", "long")


def test_latex_of_the_bibliography_becomes_plain_text():
    assert latex_to_text(r"W. Wagner and A. Pru\ss") == "W. Wagner and A. Pru\u00df"
    assert latex_to_text(r'{\"U}ber {\v s}e \r{A} {\o} 387--535') == "\u00dcber \u0161e \u00c5 \u00f8 387-535"


# Composition ---------------------------------------------------------------
def _label_centres(scene, frame):
    out = []
    for item in scene:
        if item.role == "isoline_label":
            px, py = frame.to_pt([item.x], [item.y])
            out.append((float(px[0]), float(py[0])))
    return out


def _frame(scene, size):
    a = scene.axes
    return Frame(a.x_limits, a.y_limits, a.x_log, a.y_log, *size)


def test_labels_keep_clear_of_the_badge(logo_files):
    size = (600.0, 420.0)
    plain = _diagram().update_scene(size)
    frame = _frame(plain, size)
    branding = dict(logo=logo_files, logo_width_pt=90, references="full", versions=True, lines=("example.com",))
    width, height = None, None
    # The corner where the unbranded chart has the most labels, so the test has something to move
    counts = {}
    for corner in CORNERS:
        d = _diagram(dict(branding, location=corner))
        badge = d.update_scene(size).axes.badge
        width, height = badge.size_pt()
        box = corner_box(frame, corner, width, height, badge.inset_pt)
        counts[corner] = (sum(abs(x - box.cx) <= box.half_w and abs(y - box.cy) <= box.half_h
                              for x, y in _label_centres(plain, frame)), d, box)
    corner = max(counts, key=lambda c: counts[c][0])
    n_before, d, box = counts[corner]
    assert n_before > 0
    scene = d.update_scene(size)
    assert scene.axes.badge.location == corner
    inside = [(x, y) for x, y in _label_centres(scene, _frame(scene, size))
              if abs(x - box.cx) <= box.half_w and abs(y - box.cy) <= box.half_h]
    assert inside == []


def test_badge_lines_come_in_order_and_auto_takes_the_emptiest_corner(logo_files):
    size = (600.0, 420.0)
    d = _diagram(dict(logo=logo_files, references="short", versions=True, lines=("example.com | 2026-10-19",)))
    scene = d.update_scene(size)
    badge = scene.axes.badge
    assert badge.lines[0] == "R290: Lemmon et al. (2009)"
    assert badge.lines[1].startswith("CoolProp ") and ", CoolPlot " in badge.lines[1]
    assert badge.lines[2:] == ("example.com | 2026-10-19",)
    assert [p.mime for p in badge.logo] == [SVG, PNG]
    frame = _frame(scene, size)
    lines = [(item.x, item.y) for item in scene if item.role in ("isoline", "saturation", "quality")]
    width, height = badge.size_pt()

    def points_in(corner):
        box = corner_box(frame, corner, width, height, badge.inset_pt)
        total = 0
        for x, y in lines:
            px, py = frame.to_pt(x, y)
            total += int(((abs(px - box.cx) <= box.half_w) & (abs(py - box.cy) <= box.half_h)).sum())
        return total

    counts = {c: points_in(c) for c in CORNERS}
    assert counts[badge.location] == min(counts.values())
    assert max(counts.values()) > min(counts.values())   # the choice mattered


def test_the_watermark_fits_the_plot_area(logo_files):
    size = (600.0, 420.0)
    d = _diagram(dict(watermark=logo_files[1], watermark_width=1.0, watermark_opacity=0.1))
    mark = d.update_scene(size).axes.watermark
    assert mark.opacity == 0.1 and mark.width_pt == pytest.approx(600.0)
    assert d.update_scene(size).axes.badge is None
    tall = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    tall.settings = tall.settings.with_(branding=dict(watermark=SVG_LOGO_URI(), watermark_width=1.0))
    mark = tall.update_scene((100.0, 20.0)).axes.watermark
    assert mark.height_pt() == pytest.approx(0.8 * 20.0)


def SVG_LOGO_URI():
    return "data:image/svg+xml;base64," + base64.b64encode(SVG_LOGO.encode()).decode()


def test_branded_charts_are_composed_in_python(monkeypatch, logo_files):
    from coolplot import corelib

    def refuse(*args, **kwargs):
        raise AssertionError("coolplot-core cannot compose branding")

    monkeypatch.setattr(corelib, "enabled", lambda: True)
    monkeypatch.setattr(corelib, "compose", refuse)
    d = _diagram(dict(logo=logo_files, lines=("x",)))
    assert d.update_scene().axes.badge is not None


def test_scene_records_carry_the_branding(logo_files):
    d = _diagram(dict(logo=logo_files, lines=("example.com",), watermark=logo_files[1]))
    scene = d.update_scene()
    again = Scene.from_dict(scene.to_dict())
    assert again.axes == scene.axes
    assert axes_to_dict(scene.axes)["badge"]["logo"][1].startswith("data:image/png;base64,")


# Backends ------------------------------------------------------------------
def test_svg_draws_the_badge_and_the_watermark(tmp_path, logo_files):
    d = _diagram(dict(logo=logo_files, references="short", lines=("example.com",), watermark=logo_files[1],
                      location="upper left"))
    d.save(str(tmp_path / "branded.svg"))
    text = (tmp_path / "branded.svg").read_text()
    assert 'xmlns:xlink="http://www.w3.org/1999/xlink"' in text
    badge = re.search(r'<g class="cp-badge">(.*?)</g>', text, re.S).group(1)
    assert 'class="cp-badge-box"' in badge
    assert 'class="cp-badge-logo"' in badge and "data:image/svg+xml;base64," in badge   # the first variant
    assert re.findall(r'<text class="cp-badge-text"[^>]*>([^<]*)</text>', badge) == [
        "R290: Lemmon et al. (2009)", "example.com"]
    watermark = re.search(r'<image class="cp-watermark"[^>]*>', text).group(0)
    assert 'opacity="0.06"' in watermark and "data:image/png;base64," in watermark
    # Below the grid and the items: the watermark comes before the first grid line and item
    assert text.index("cp-watermark") < text.index('class="cp-grid-major"') < text.index('class="cp-items"')
    plain = _diagram()
    plain.save(str(tmp_path / "plain.svg"))
    plain_text = (tmp_path / "plain.svg").read_text()
    assert "cp-badge" not in plain_text and "cp-watermark" not in plain_text and "xlink" not in plain_text


def test_svg_files_have_the_page_size_in_points(tmp_path):
    d = _diagram()
    d.save(str(tmp_path / "a4.svg"))
    head = (tmp_path / "a4.svg").read_text()[:300]
    assert 'width="841.89pt" height="595.276pt" viewBox="0 0 1122.52 793.701"' in head
    d.save(str(tmp_path / "px.svg"), width=400, height=300, unit="px")
    assert 'width="400" height="300" viewBox="0 0 400 300"' in (tmp_path / "px.svg").read_text()[:300]


def test_matplotlib_draws_the_branding_with_the_logo_at_full_resolution(tmp_path, logo_files):
    pytest.importorskip("matplotlib")
    d = _diagram(dict(logo=logo_files, lines=("example.com",), watermark=logo_files[1]))
    d.save(str(tmp_path / "branded.pdf"))
    data = (tmp_path / "branded.pdf").read_bytes()
    sizes = {(int(w), int(h)) for w, h in re.findall(rb"/Width (\d+).{0,80}?/Height (\d+)", data, re.S)}
    assert (400, 100) in sizes   # the PNG's own pixels, not resampled to the figure dpi
    from PIL import Image
    d.save(str(tmp_path / "branded.png"), dpi=100)
    _diagram().save(str(tmp_path / "plain.png"), dpi=100)
    branded, plain = (Image.open(tmp_path / n).convert("RGB") for n in ("branded.png", "plain.png"))
    assert branded.size == plain.size == (1169, 826)   # matplotlib rounds 826.8 px down
    assert branded.tobytes() != plain.tobytes()


def test_matplotlib_warns_for_a_logo_given_only_as_svg(tmp_path, logo_files):
    pytest.importorskip("matplotlib")
    d = _diagram(dict(logo=logo_files[0], lines=("x",)))
    with pytest.warns(UserWarning, match="PNG pictures only; the logo is left out"):
        d.save(str(tmp_path / "x.png"), dpi=50)


def test_plotly_warns_that_it_leaves_the_branding_out(logo_files):
    pytest.importorskip("plotly")
    from coolplot.render import base
    from coolplot.render.plotly import PlotlyRenderer
    base._branding_warned.discard("PlotlyRenderer")
    d = _diagram(dict(lines=("x",)))
    with pytest.warns(UserWarning, match="PlotlyRenderer does not draw the badge"):
        d.draw(PlotlyRenderer())


# save(), uncached_curves(), pseudo-pure blends -------------------------------
def test_save_does_not_create_pyplot_figures(tmp_path):
    pytest.importorskip("matplotlib")
    import matplotlib.pyplot as plt
    before = set(plt.get_fignums())
    for i in range(2):
        _diagram().save(str(tmp_path / "chart{0}.png".format(i)), dpi=30)
    assert set(plt.get_fignums()) == before


def test_uncached_curves_counts_the_lines_to_calculate():
    from coolplot.engine import CurveCache
    d = PropertyDiagram("R290", "ph", tp_limits="ACHP", cache=CurveCache())
    d.set_default_lines()
    before = d.uncached_curves()
    assert before == sum(s.num for s in d.spec.isolines) > 0
    d.update_scene()
    assert d.uncached_curves() == 0
    other = PropertyDiagram("R290", "ph", tp_limits="ACHP", cache=d.cache)
    other.set_default_lines()
    assert other.uncached_curves() == 0
    ts = PropertyDiagram("R290", "Ts", tp_limits="ACHP", cache=d.cache)
    ts.set_default_lines()
    assert ts.uncached_curves() > 0


def test_a_pseudo_pure_blend_gets_one_warning_naming_the_mixture():
    d = PropertyDiagram("R407C", "ph", tp_limits="ACHP")
    d.set_default_lines()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        d.update_scene()
        d.update_scene()
    messages = [str(w.message) for w in caught]
    assert sum("pseudo-pure" in m for m in messages) == 1
    assert any("'R407C.mix'" in m for m in messages)
    assert not any(m.startswith("Skipping the line Q=") for m in messages)
    mixture = PropertyDiagram("R407C.mix", "ph", tp_limits="ACHP")
    mixture.set_lines("Q", num=3)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mixture.update_scene()
    assert not any("pseudo-pure" in str(w.message) for w in caught)
