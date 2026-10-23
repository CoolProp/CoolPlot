# -*- coding: utf-8 -*-
"""PDF output: embedded fonts, metadata, reproducible files, several pages."""
import re

import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("CoolProp")

from coolplot import PropertyDiagram, PsychrometricChart, save_pdf  # noqa: E402
from coolplot.render import mpl as mpl_backend  # noqa: E402
from coolplot.render.mpl import MatplotlibRenderer  # noqa: E402
from coolplot.scene import AxesSpec, Scene, Text  # noqa: E402
from coolplot.style.values import Font, TextStyle  # noqa: E402


def _diagram(title="R290, costs $5"):
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    d.set_lines("Q", num=5, labels=True)
    d.set_lines("T", values=[0.0, 50.0], labels=True)
    d.title = title
    return d


def _fonts(data: bytes):
    """(subtype, base font name without the subset tag) of every font in a PDF."""
    out = []
    for body in re.findall(rb"<<(.*?)>>", data, re.S):
        if b"/Type /Font" in body:
            subtype = re.search(rb"/Subtype /(\w+)", body)
            name = re.search(rb"/BaseFont /(?:[A-Z]{6}\+)?([\w-]+)", body)
            out.append((subtype.group(1).decode() if subtype else None, name.group(1).decode() if name else None))
    return out


def test_pdf_embeds_truetype_fonts_and_the_title(tmp_path):
    path = tmp_path / "ph.pdf"
    _diagram().draw(MatplotlibRenderer(use_pyplot=False)).save(str(path))
    data = path.read_bytes()
    subtypes = {s for s, _ in _fonts(data)}
    assert "Type3" not in subtypes and "CIDFontType2" in subtypes
    assert b"/FontFile2" in data
    assert b"(R290, costs $5)" in data          # the title, also in the metadata
    assert b"CreationDate" not in data and b"Matplotlib" not in data


def test_pdf_files_are_reproducible(tmp_path):
    for name in ("a.pdf", "b.pdf"):
        _diagram().draw(MatplotlibRenderer(use_pyplot=False)).save(str(tmp_path / name))
    assert (tmp_path / "a.pdf").read_bytes() == (tmp_path / "b.pdf").read_bytes()
    for name in ("a.svg", "b.svg"):
        _diagram().draw(MatplotlibRenderer(use_pyplot=False)).save(str(tmp_path / name))
    assert (tmp_path / "a.svg").read_bytes() == (tmp_path / "b.svg").read_bytes()


def test_type3_on_request(tmp_path):
    path = tmp_path / "t3.pdf"
    _diagram().draw(MatplotlibRenderer(use_pyplot=False)).save(str(path), pdf_fonts="type3")
    assert "Type3" in {s for s, _ in _fonts(path.read_bytes())}
    with pytest.raises(ValueError):
        _diagram().draw(MatplotlibRenderer(use_pyplot=False)).save(str(path), pdf_fonts="type1")


def test_fonts_without_truetype_outlines_are_replaced_in_the_file(tmp_path, monkeypatch):
    # Pretend DejaVu Sans were installed only as CFF OpenType, as Inter often is
    real = mpl_backend._has_truetype_outlines
    monkeypatch.setattr(mpl_backend, "_has_truetype_outlines",
                        lambda path, face=0: False if path.endswith("DejaVuSans.ttf") else real(path, face))
    font = Font(family=("DejaVu Sans", "DejaVu Serif", "serif"))
    scene = Scene(AxesSpec(x_limits=(0.0, 1.0), y_limits=(0.0, 1.0), title="Title"),
                  [Text(id="t", x=0.5, y=0.5, text="label", style=TextStyle(font=font))])
    renderer = MatplotlibRenderer(use_pyplot=False)
    renderer.sync(scene)
    path = tmp_path / "fallback.pdf"
    with pytest.warns(UserWarning, match="DejaVu Sans is installed here only as CFF OpenType.*DejaVu Serif"):
        renderer.save(str(path))
    names = {n for _, n in _fonts(path.read_bytes())}
    assert "DejaVuSerif" in names
    assert renderer.describe_item("t")["font_used"] == "DejaVu Sans"   # the screen is unchanged


def test_several_charts_in_one_pdf(tmp_path):
    chart = PsychrometricChart(T_range=(0, 40), W_range=(0, 20))
    chart.set_lines("RH", [50.0, 100.0])
    path = tmp_path / "report.pdf"
    renderers = save_pdf(str(path), [_diagram(), chart], metadata={"Author": "Heat pump team"})
    data = path.read_bytes()
    assert len(renderers) == 2 and data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 2
    assert b"(Heat pump team)" in data and b"(R290, costs $5)" in data
    assert "Type3" not in {s for s, _ in _fonts(data)}
    with pytest.raises(ValueError):
        save_pdf(str(path), [])


def test_eps_embeds_truetype_fonts(tmp_path):
    path = tmp_path / "ph.eps"
    _diagram().draw(MatplotlibRenderer(use_pyplot=False)).save(str(path))
    text = path.read_bytes()
    assert b"/FontType 42" in text and b"/FontType 3" not in text


# ---------------------------------------------------------------------------
# The conformance check for PDF output, and backends that should fail it
# ---------------------------------------------------------------------------
from coolplot.testing.pdf_reader import read_pdf  # noqa: E402
from coolplot.testing import check_pdf  # noqa: E402


def _factory(cls=MatplotlibRenderer):
    return lambda: cls(use_pyplot=False)


def test_matplotlib_passes_the_pdf_check():
    assert check_pdf(_factory()) == []


class _Type3Fonts(MatplotlibRenderer):
    def save(self, path, **kwargs):
        super().save(path, pdf_fonts="type3")


class _NoTitle(MatplotlibRenderer):
    def save(self, path, **kwargs):
        super().save(path, metadata={"Title": None})


class _MathText(MatplotlibRenderer):
    def _apply(self, artist, item):
        super()._apply(artist, item)
        if isinstance(item, Text):
            artist.set_parse_math(True)


class _HaloAsPathEffect(MatplotlibRenderer):
    """The old way: the halo as a path effect turns the label into outlines."""
    def _apply_halo(self, item, artist):
        from matplotlib import patheffects
        s = item.style
        if s.halo_color is not None and s.halo_width_pt > 0.0:
            artist.set_path_effects([patheffects.withStroke(linewidth=2.0 * s.halo_width_pt,
                                                            foreground=s.halo_color)])


class _ForeignColour(MatplotlibRenderer):
    def save(self, path, **kwargs):
        self.ax.set_facecolor("#ff0000")
        super().save(path, **kwargs)


class _NotReproducible(MatplotlibRenderer):
    _count = 0

    def save(self, path, **kwargs):
        _NotReproducible._count += 1
        super().save(path, metadata={"Subject": "save number {0}".format(_NotReproducible._count)})


class _DamagedFont(MatplotlibRenderer):
    """Declares the TrueType font program as a CFF one (same length, so the file stays readable)."""
    def save(self, path, **kwargs):
        super().save(path, **kwargs)
        with open(path, "rb") as f:
            data = f.read()
        with open(path, "wb") as f:
            f.write(data.replace(b"/FontFile2", b"/FontFile3"))


@pytest.mark.parametrize("defect", [_Type3Fonts, _NoTitle, _MathText, _HaloAsPathEffect, _ForeignColour,
                                    _NotReproducible, _DamagedFont])
def test_the_pdf_check_rejects_defects(defect):
    assert check_pdf(_factory(defect)) != []


def test_reader_finds_fonts_texts_colours_and_pages(tmp_path):
    path = tmp_path / "ph.pdf"
    d = _diagram()
    d.settings = d.settings.with_(labels={"mode": "edge"})   # full label texts
    d.draw(MatplotlibRenderer(use_pyplot=False)).save(str(path))
    content = read_pdf(str(path))
    assert content.pages == 1 and content.info["Title"] == "R290, costs $5"
    assert all(f.program_kind == "truetype" and not f.problems for f in content.fonts)
    assert {"R290, costs $5", "T=50 \u00b0C", "x=0.5", "Saturation"} <= set(content.texts)
    theme = d.spec.settings.look
    assert theme.saturation.color in content.colors and not content.cmyk
    with pytest.raises(ValueError):
        bad = tmp_path / "objstm.pdf"
        bad.write_bytes(b"%PDF-1.5\n1 0 obj\n<< /Type /ObjStm /N 1 >>\nstream\n\nendstream\nendobj\n")
        read_pdf(str(bad))


def test_replace_info_keeps_the_content(tmp_path):
    from coolplot.testing.pdf_reader import replace_info
    path = tmp_path / "ph.pdf"
    _diagram().draw(MatplotlibRenderer(use_pyplot=False)).save(str(path))
    before = read_pdf(str(path))
    replace_info(str(path), {"Title": "Neuer Titel (mit Klammern)", "Author": "J\u00f6rg"})
    after = read_pdf(str(path))
    assert after.info == {"Title": "Neuer Titel (mit Klammern)", "Author": "J\u00f6rg"}
    assert after.texts == before.texts and after.colors == before.colors and after.pages == 1
    data = path.read_bytes()
    xref = int(re.search(rb"startxref\s+(\d+)", data).group(1))
    assert data[xref:xref + 4] == b"xref"     # the new table is where the trailer says


def test_stream_data_is_skipped_by_its_length():
    from coolplot.testing.pdf_reader import _Pdf
    payload = b"BT (endobj endstream) Tj ET"
    data = (b"%PDF-1.4\n1 0 obj\n<< /Length " + str(len(payload)).encode() + b" >>\nstream\n" + payload
            + b"\nendstream\nendobj\n2 0 obj\n<< /Type /Catalog >>\nendobj\n")
    pdf = _Pdf(data)
    assert pdf.stream(1) == payload and sorted(pdf.objects) == [1, 2]


# ---------------------------------------------------------------------------
# Review findings
# ---------------------------------------------------------------------------
def _pretend_cff(monkeypatch, suffix):
    """Pretend the font file ending in ``suffix`` were CFF OpenType."""
    real = mpl_backend._has_truetype_outlines
    monkeypatch.setattr(mpl_backend, "_has_truetype_outlines",
                        lambda path, face=0: False if path.endswith(suffix) else real(path, face))


def _one_text(font, text="label"):
    scene = Scene(AxesSpec(x_limits=(0.0, 1.0), y_limits=(0.0, 1.0)),
                  [Text(id="t", x=0.5, y=0.5, text=text, style=TextStyle(font=font))])
    renderer = MatplotlibRenderer(use_pyplot=False)
    renderer.sync(scene)
    return renderer


def test_a_cff_font_later_in_the_list_is_left_out_too(tmp_path, monkeypatch):
    # Matplotlib falls back glyph by glyph: a CFF font anywhere in the list could damage the file
    _pretend_cff(monkeypatch, "DejaVuSerif.ttf")
    renderer = _one_text(Font(family=("DejaVu Sans", "DejaVu Serif", "sans-serif")))
    with pytest.warns(UserWarning, match="DejaVu Serif \\(CFF OpenType\\) cannot be embedded"):
        renderer.save(str(tmp_path / "a.pdf"))
    assert renderer.backend_object("t").get_fontfamily() == ["DejaVu Sans", "DejaVu Serif", "sans-serif"]


def test_strict_fonts_refuse_a_replacement_and_the_screen_stays(tmp_path, monkeypatch):
    import warnings
    _pretend_cff(monkeypatch, "DejaVuSans.ttf")
    font = Font(family=("DejaVu Sans", "DejaVu Serif", "serif"))
    renderer = _one_text(font)
    renderer.strict_fonts = True
    with pytest.raises(ValueError, match="strict_fonts"):
        renderer.save(str(tmp_path / "a.pdf"))
    assert renderer.backend_object("t").get_fontfamily() == ["DejaVu Sans", "DejaVu Serif", "serif"]
    # A failure while replacing (warnings turned into errors) leaves every text as it was
    renderer = _one_text(font)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(UserWarning):
            renderer.save(str(tmp_path / "b.pdf"))
    assert renderer.backend_object("t").get_fontfamily() == ["DejaVu Sans", "DejaVu Serif", "serif"]
    # Each renderer warns for itself, so a second figure does not stay silent
    for _ in range(2):
        with pytest.warns(UserWarning, match="instead"):
            _one_text(font).save(str(tmp_path / "c.pdf"))
    # fonts_used tells the fonts on screen and the fonts in the file
    renderer = _one_text(font)
    assert "DejaVu Sans" in renderer.fonts_used().values()
    assert set(renderer.fonts_used(pdf=True).values()) >= {"DejaVu Serif"}


def test_font_collections_are_checked_face_by_face(tmp_path):
    def collection(face_head):
        # "ttcf", version, one font, offset 16 -> the face starts with face_head
        return b"ttcf" + b"\x00\x01\x00\x00" + (1).to_bytes(4, "big") + (16).to_bytes(4, "big") + face_head
    truetype, cff = tmp_path / "t.ttc", tmp_path / "c.ttc"
    truetype.write_bytes(collection(b"\x00\x01\x00\x00"))
    cff.write_bytes(collection(b"OTTO"))
    assert mpl_backend._has_truetype_outlines(str(truetype))
    assert not mpl_backend._has_truetype_outlines(str(cff))


def test_a_font_file_that_is_no_font_warns_once(tmp_path):
    bad = tmp_path / "broken.ttf"
    bad.write_bytes(b"not a font")
    font = Font(family=("DejaVu Sans",), files=(str(bad),))
    with pytest.warns(UserWarning, match="could not be loaded"):
        _one_text(font)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _one_text(font)   # reported once, not again


def test_eps_files_are_reproducible(tmp_path):
    import time
    paths = [tmp_path / "a.eps", tmp_path / "b.eps"]
    for path in paths:
        _diagram().draw(MatplotlibRenderer(use_pyplot=False)).save(str(path))
        time.sleep(1.1)
    assert paths[0].read_bytes().replace(b"a.eps", b"b.eps") == paths[1].read_bytes()


def _minimal_pdf(content: bytes, resources: bytes = b"<< >>") -> bytes:
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /Resources " + resources + b" /Contents 4 0 R >>",
               b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"]
    out = b"%PDF-1.4\n"
    for i, body in enumerate(objects, start=1):
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    return out + b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"


@pytest.mark.parametrize("content, unchecked, cmyk", [
    (b"/DeviceCMYK cs 0 1 1 0 sc 0 0 10 10 re f", [], True),
    (b"0 1 1 0 k 0 0 10 10 re f", [], True),
    (b"/Sh0 sh", ["shading"], False),
    (b"BI /W 1 /H 1 /CS /G /BPC 8 ID ) EI 1 0 0 rg 0 0 10 10 re f", ["inline image"], False),
    (b"/Pattern cs /P0 scn 0 0 10 10 re f", ["pattern"], False),
    (b"/Lab cs 50 0 0 sc 0 0 10 10 re f", ["colour space Lab"], False),
])
def test_reader_reports_paint_it_cannot_check(tmp_path, content, unchecked, cmyk):
    path = tmp_path / "x.pdf"
    path.write_bytes(_minimal_pdf(content))
    found = read_pdf(str(path))
    assert found.unchecked == unchecked and found.cmyk == cmyk
    if content.startswith(b"BI"):
        assert found.colors == {"#ff0000"}   # what follows the inline image is still read


def test_reader_refuses_what_it_cannot_read(tmp_path):
    path = tmp_path / "x.pdf"
    path.write_bytes(_minimal_pdf(b"(unterminated \\"))
    with pytest.raises(ValueError):
        read_pdf(str(path))
    path.write_bytes(_minimal_pdf(b"1 0 0 rg ) 0 0 1 1 re f"))   # a stray closing parenthesis
    with pytest.raises(ValueError):
        read_pdf(str(path))


def test_reader_is_not_slowed_down_by_many_trailers(tmp_path):
    import time
    path = tmp_path / "x.pdf"
    path.write_bytes(_minimal_pdf(b"0 0 1 1 re f") + b"trailer <<" * 20000)
    start = time.monotonic()
    with pytest.raises(ValueError):
        read_pdf(str(path))   # the last trailer is unterminated
    assert time.monotonic() - start < 2.0


def test_replace_info_refuses_other_generations(tmp_path):
    from coolplot.testing.pdf_reader import replace_info
    path = tmp_path / "x.pdf"
    path.write_bytes(_minimal_pdf(b"0 0 1 1 re f").replace(b"4 0 obj", b"4 2 obj").replace(b"4 0 R", b"4 2 R"))
    with pytest.raises(ValueError, match="generations"):
        replace_info(str(path), {"Title": "x"})


def test_plotly_escapes_legend_names():
    pytest.importorskip("plotly")
    from coolplot.render.plotly import PlotlyRenderer
    from coolplot.scene import Line
    renderer = PlotlyRenderer()
    renderer.sync(Scene(AxesSpec(x_limits=(0.0, 1.0), y_limits=(0.0, 1.0)),
                        [Line(id="l", x=[0, 1], y=[0, 1], legend="costs $5 <b>or</b> $6")]))
    names = [trace.name for trace in renderer.figure.data]
    assert all("$" not in n and "<b>" not in n for n in names)
    assert renderer.describe_axes()["legend"][0][0] == "costs $5 <b>or</b> $6"


def test_kaleido_is_not_promised_without_a_browser(monkeypatch):
    pytest.importorskip("plotly")
    from coolplot.render import plotly as plotly_backend
    monkeypatch.setenv("BROWSER_PATH", "/no/such/chrome")
    assert plotly_backend.kaleido_available() is False


def test_kaleido_finds_a_browser_with_an_older_choreographer(monkeypatch, tmp_path):
    pytest.importorskip("plotly")
    pytest.importorskip("kaleido")
    chromium = pytest.importorskip("choreographer.browsers.chromium")
    from coolplot.render import plotly as plotly_backend
    monkeypatch.delenv("BROWSER_PATH", raising=False)
    if hasattr(chromium.Chromium, "find_browser"):
        monkeypatch.delattr(chromium.Chromium, "find_browser")   # as in choreographer 1.0.5
    # A Chromium on the PATH is found
    program = tmp_path / "bin" / "chromium"
    program.parent.mkdir()
    program.write_text("#!/bin/sh\n")
    program.chmod(0o755)
    monkeypatch.setenv("PATH", str(program.parent))
    assert plotly_backend.kaleido_available() is True
    # No browser at all: nothing is promised
    monkeypatch.setenv("PATH", str(tmp_path))
    assert plotly_backend.kaleido_available() is False
