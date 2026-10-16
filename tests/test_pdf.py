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
    d.set_isolines("Q", num=5, labels=True)
    d.set_isolines("T", values=[0.0, 50.0], labels=True)
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
                        lambda path: False if path.endswith("DejaVuSans.ttf") else real(path))
    monkeypatch.setattr(mpl_backend, "_substituted", set())
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
