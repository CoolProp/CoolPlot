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
from coolplot.compose.corners import corner_box
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
    assert [line.split(":")[0] for line in blend] == ["R407C", "R32", "R125", "R134a", "Mixture model"]
    assert blend[-1] == "Mixture model: Lemmon and Jacobsen (2004)"
    from coolplot import HumidAirSpec
    assert fluid_references(HumidAirSpec(), "full") == ("Humid air: Herrmann et al., ASHRAE RP-1485 (2009)",)
    # Other backends are named without asking CoolProp for a state (REFPROP is not installed here)
    assert fluid_references("REFPROP::R290") == ("R290: REFPROP",)
    with pytest.raises(ValueError, match="reference style"):
        fluid_references("R290", "long")


def test_references_name_a_mixture_and_its_composition():
    # A predefined blend by its name, shown by mass as its R number is defined
    assert fluid_references("R407C.mix")[0] == "R407C: R32 23 %, R125 25 %, R134a 52 % by mass"
    # Fractions that match a predefined blend carry its name, by mole or by mass
    assert fluid_references("HEOS::R32[0.697616]&R125[0.302384]")[0] == "R410A: R32 50 %, R125 50 % by mass"
    from coolplot.spec.fluid import FluidSpec
    by_mass = FluidSpec(components=("R32", "R125"), fractions=(0.5, 0.5), basis="mass")
    assert fluid_references(by_mass)[0] == "R410A: R32 50 %, R125 50 % by mass"
    # Within half a percent the name stays, with the composition as given
    assert fluid_references("HEOS::R32[0.7]&R125[0.3]")[0] == "R410A: R32 50.3 %, R125 49.7 % by mass"
    # No blend of these fractions: a mixture in the basis it was given in
    assert fluid_references("HEOS::R32[0.2]&R125[0.8]")[0] == "Mixture: R32 20 %, R125 80 % by mole"
    # A Fluid has lost the name of its blend; the composition finds it again
    from coolplot.thermo.fluid import Fluid
    assert fluid_references(Fluid("HEOS::R407C.mix"))[0] == "R407C: R32 23 %, R125 25 %, R134a 52 % by mass"
    # Other backends show the fractions next to the backend name, without asking CoolProp
    assert fluid_references("REFPROP::R32[0.7]&R125[0.3]") == ("R32 70 %, R125 30 % by mole: REFPROP",)
    assert fluid_references("INCOMP::MEG[0.3]") == ("MEG 30 % by mass: CoolProp incompressible fluid",)
    # Pure fluids, also the pseudo-pure R410A, have no composition line
    assert fluid_references("R410A") == ("R410A: Lemmon (2003)",)


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
    overlays = [(item.x, item.y) for item in scene if item.group and item.group.startswith(("cycle/", "process/"))
                and item.role in ("cycle", "process", "state_points")]
    width, height = badge.size_pt()

    def points_in(corner, drawn):
        box = corner_box(frame, corner, width, height, badge.inset_pt)
        total = 0
        for x, y in drawn:
            px, py = frame.to_pt(x, y)
            total += int(((abs(px - box.cx) <= box.half_w) & (abs(py - box.cy) <= box.half_h)).sum())
        return total

    # The legend sits inside and takes its corner first; the badge takes the
    # emptiest of the others, cycles counting before lines
    legend = scene.axes.style.legend.location
    assert badge.location != legend
    counts = {c: (points_in(c, overlays), points_in(c, lines)) for c in CORNERS if c != legend}
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


# Review fixes ------------------------------------------------------------------
def _grey_png(width: int, height: int) -> bytes:
    """An 8-bit greyscale PNG (colour type 0): left half black, right half light grey."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    row = b"\x00" + b"\x00" * (width // 2) + b"\xc8" * (width - width // 2)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


def test_a_greyscale_logo_stays_grey_in_matplotlib(tmp_path):
    pytest.importorskip("matplotlib")
    from PIL import Image
    logo = tmp_path / "grey.png"
    logo.write_bytes(_grey_png(200, 50))
    d = _diagram(dict(logo=str(logo), logo_width_pt=150, location="lower left"))
    d.set_lines("T", num=2)
    d.save(str(tmp_path / "grey_logo.png"), dpi=72)
    colours = {c for _, c in Image.open(tmp_path / "grey_logo.png").convert("RGB").getcolors(1 << 20)}
    assert (68, 1, 84) not in colours and (253, 231, 36) not in colours   # the ends of viridis
    assert (0, 0, 0) in colours and (200, 200, 200) in colours


def test_postscript_leaves_the_watermark_out(tmp_path, logo_files):
    pytest.importorskip("matplotlib")
    d = _diagram(dict(watermark=logo_files[1], lines=("x",)))
    with pytest.warns(UserWarning, match="watermark is left out of PS and EPS"):
        d.save(str(tmp_path / "chart.eps"))
    assert b"colorimage" not in (tmp_path / "chart.eps").read_bytes()   # no image at all
    d.save(str(tmp_path / "chart.pdf"))   # PDF keeps it, and the figure keeps it afterwards
    assert b"/ca 0.06" in (tmp_path / "chart.pdf").read_bytes()


def test_references_with_several_keys_escapes_and_name_particles():
    oxygen = fluid_references("Oxygen")[0]
    assert oxygen == "Oxygen: Schmidt and Wagner (1985); Stewart et al. (1991)"
    assert "\\" not in fluid_references("n-Dodecane", "full")[0] and "Energy & Fuels" in fluid_references(
        "n-Dodecane", "full")[0]
    assert fluid_references("R124")[0].startswith("R124: de Vries et al.")
    assert latex_to_text(r"CO$_2$ and HVAC\&R") == "CO2 and HVAC&R"
    from coolplot.thermo.references import _last_name
    assert [_last_name(a) for a in ("H. H. Rachford Jr.", "{Rachford Jr.}, H. H.", "{van der Waals}, J. D.")] == [
        "Rachford", "Rachford", "van der Waals"]


def test_badge_drawn_where_the_labels_keep_clear(logo_files):
    """The box the label layout keeps clear of is the box both writers draw, in every corner."""
    pytest.importorskip("matplotlib")
    from coolplot.render.mpl import MatplotlibRenderer
    from coolplot.render.svg import PX_PER_PT, SvgRenderer
    branding = dict(logo=logo_files, references="full", versions=True, lines=("example.com",))
    for corner in CORNERS:
        d = _diagram(dict(branding, location=corner))
        svg = d.draw(SvgRenderer(width=900, height=650))
        size = svg.plot_size_pt()
        badge = d.scene.axes.badge
        box = corner_box(_frame(d.scene, size), corner, *badge.size_pt(), badge.inset_pt)
        bx, by, bw, bh = svg._box
        x, y, w, h = svg.badge_box_px()
        # SVG pixels from the top of the plot area against points from its bottom
        assert (x - bx) / PX_PER_PT == pytest.approx(box.cx - box.half_w, abs=0.01)
        assert (by + bh - y - h) / PX_PER_PT == pytest.approx(box.cy - box.half_h, abs=0.01)
        assert (w / PX_PER_PT, h / PX_PER_PT) == pytest.approx((2 * box.half_w, 2 * box.half_h), abs=0.01)
        d2 = _diagram(dict(branding, location=corner))
        mpl = d2.draw(MatplotlibRenderer(use_pyplot=False, figsize=(9.0, 6.5)))
        size = mpl.plot_size_pt()
        box = corner_box(_frame(d2.scene, size), corner, *badge.size_pt(), badge.inset_pt)
        ex, ey, ew, eh = mpl.badge_extent_pt()
        assert (ex, ey, ew, eh) == pytest.approx(
            (box.cx - box.half_w, box.cy - box.half_h, 2 * box.half_w, 2 * box.half_h), abs=0.5)


def test_the_native_svg_writer_is_used_only_without_branding(monkeypatch, logo_files):
    from coolplot import corelib
    from coolplot.render.svg import SvgRenderer
    calls = []

    def native(axes, items, *args):
        calls.append(axes)
        return "<svg native/>"

    monkeypatch.setattr(corelib, "scene_to_svg", native)
    plain = _diagram()
    assert plain.draw(SvgRenderer(native=True)).to_svg() == "<svg native/>" and len(calls) == 1
    branded = _diagram(dict(logo=logo_files, lines=("x",)))
    text = branded.draw(SvgRenderer(native=True)).to_svg()
    assert "cp-badge" in text and len(calls) == 1
    assert "<svg native/>" != plain.draw(SvgRenderer(native=True, unit="pt")).to_svg() and len(calls) == 1
    assert "<svg native/>" != plain.draw(SvgRenderer(native=True, width=800.5)).to_svg() and len(calls) == 1


def test_scene_page_warns_that_it_leaves_the_branding_out(logo_files):
    from coolplot.render import base
    from coolplot.render.web import scene_page
    base._branding_warned.discard("scene_page (the JavaScript writer)")
    scene = _diagram(dict(lines=("x",))).update_scene()
    with pytest.warns(UserWarning, match="scene_page .the JavaScript writer. does not draw the badge"):
        scene_page(scene)


def test_clear_removes_the_branding_and_paths_and_wide_text_are_handled(tmp_path, logo_files):
    pytest.importorskip("matplotlib")
    from pathlib import Path
    from coolplot.core.textwidth import text_width_em
    from coolplot.render.mpl import MatplotlibRenderer
    d = _diagram(dict(logo=(Path(logo_files[1]),), lines=("x",), watermark=Path(logo_files[1])))
    assert d.settings.branding.logo == (logo_files[1],) and d.settings.branding.watermark == (logo_files[1],)
    renderer = d.draw(MatplotlibRenderer(use_pyplot=False))
    assert renderer.badge_extent_pt() is not None
    renderer.clear()
    assert renderer.badge_extent_pt() is None and renderer._branding == []
    assert text_width_em("\u4e2d\u6587") == 2.0 and text_width_em("\u00e9") == 0.6


def _rgba_png(width: int, height: int, pixel) -> bytes:
    """An RGBA PNG whose pixel (x, y) is ``pixel(x, y)``, a tuple of four bytes."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def _postscript_pixels(path) -> set:
    """The RGB pixels of every colorimage in a PostScript file matplotlib wrote."""
    pixels = set()
    for block in re.findall(rb"colorimage\s+([0-9a-fA-F\s]+)", path.read_bytes()):
        data = bytes.fromhex(re.sub(rb"\s", b"", block).decode())
        pixels.update(data[i:i + 3] for i in range(0, len(data) - 2, 3))
    return pixels


def test_postscript_fills_the_transparent_logo_pixels_and_restores_the_figure(tmp_path):
    """PostScript drops the alpha channel: the logo is blended onto the badge
    background for PS/EPS only, and the watermark comes back afterwards."""
    pytest.importorskip("matplotlib")
    from coolplot.render.mpl import MatplotlibRenderer
    logo = tmp_path / "margin.png"   # transparent black around a teal middle
    logo.write_bytes(_rgba_png(40, 20, lambda x, y: (2, 153, 138, 255) if 10 <= x < 30 else (0, 0, 0, 0)))
    d = _diagram(dict(logo=str(logo), logo_width_pt=40, lines=("x",), watermark=str(logo)))
    renderer = d.draw(MatplotlibRenderer(use_pyplot=False))
    with pytest.warns(UserWarning, match="watermark is left out"):
        renderer.save(str(tmp_path / "chart.eps"))
    background = bytes.fromhex(d.scene.axes.badge.background.lstrip("#"))
    assert _postscript_pixels(tmp_path / "chart.eps") == {background, bytes((2, 153, 138))}   # no black
    # The renderer is as before: the watermark visible, the logo with its alpha channel
    # (the PNGs of one renderer are not compared: a PDF or EPS save alone moves a few pixels)
    assert len(renderer._branding) == 2 and all(a.get_visible() for a in renderer._branding)
    image, pixels, _ = renderer._badge_logo
    assert image.get_data() is pixels and pixels.shape == (20, 40, 4)


def test_matplotlib_shrinks_the_badge_without_a_drawable_logo(logo_files):
    pytest.importorskip("matplotlib")
    from coolplot.render.mpl import MatplotlibRenderer
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        only_logo = _diagram(dict(logo=logo_files[0])).draw(MatplotlibRenderer(use_pyplot=False))
        with_lines = _diagram(dict(logo=logo_files[0], lines=("x", "y"))).draw(MatplotlibRenderer(use_pyplot=False))
    assert only_logo.badge_extent_pt() is None   # no empty frame
    _, _, w, h = with_lines.badge_extent_pt()
    full = with_lines._axes.badge
    assert full.logo   # the scene keeps the SVG logo for the SVG writer
    assert (w, h) == pytest.approx(type(full)(lines=full.lines, text=full.text).size_pt(), abs=0.5)
    assert h < full.size_pt()[1] - full.logo_height_pt() + 0.5


def test_badge_lines_are_split_at_newlines_and_drawn_inside_the_box(logo_files):
    pytest.importorskip("matplotlib")
    from matplotlib.offsetbox import AnchoredOffsetbox, DrawingArea
    from coolplot.render.mpl import MatplotlibRenderer
    from coolplot.scene import Badge
    assert Badge(lines=("a\nb", "c\r\nd")).lines == ("a", "b", "c", "d")
    for corner in CORNERS:
        d = _diagram(dict(logo=logo_files, lines=("example.com\n2026-10-19", "$x$ 50%"), location=corner))
        renderer = d.draw(MatplotlibRenderer(use_pyplot=False))
        assert d.scene.axes.badge.lines[-3:] == ("example.com", "2026-10-19", "$x$ 50%")
        renderer.badge_extent_pt()   # places the box
        box = next(a for a in renderer._branding if isinstance(a, AnchoredOffsetbox) and a.patch.get_visible())
        frame = box.patch.get_window_extent()
        area = next(c for c in box.get_child().get_children() if isinstance(c, DrawingArea))
        texts = area.get_children()
        assert len(texts) == len(d.scene.axes.badge.lines)
        pad = d.scene.axes.badge.padding_pt * renderer.figure.dpi / 72.0
        tops = []
        for text in texts:
            assert not text.get_parse_math() and text.get_text() != ""
            extent = text.get_window_extent()
            assert frame.x0 + 0.9 * pad <= extent.x0 and extent.x1 <= frame.x1, corner
            assert frame.y0 <= extent.y0 and extent.y1 <= frame.y1, corner
            tops.append(extent.y1)
        assert tops == sorted(tops, reverse=True)   # top to bottom, in order


def test_clear_takes_the_branding_off_the_axes(logo_files):
    pytest.importorskip("matplotlib")
    from matplotlib.offsetbox import AnchoredOffsetbox
    from coolplot.render.mpl import MatplotlibRenderer
    renderer = _diagram(dict(logo=logo_files, lines=("x",), watermark=logo_files[1])).draw(
        MatplotlibRenderer(use_pyplot=False))

    def boxes():
        return [a for a in renderer.ax.get_children() if isinstance(a, AnchoredOffsetbox)]

    assert len(boxes()) == 2
    renderer.clear()
    assert boxes() == []


def test_svg_size_ignores_stroke_width():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" stroke-width="3" width="120" height="40">'
           '<rect width="120" height="40"/></svg>').encode()
    picture = picture_from_bytes(svg)
    assert (picture.width_px, picture.height_px) == (120, 40)


def test_short_references_name_each_source_once():
    assert fluid_references("MM") == ("MM: Thol (2015)",)
    assert fluid_references("EthyleneOxide") == ("EthyleneOxide: Thol et al. (2015); Thol (2015)",)
    full = fluid_references("EthyleneOxide", "full")[0]
    assert full.count("Chem. Eng. Sci.") == 2   # the erratum is named in the full style
