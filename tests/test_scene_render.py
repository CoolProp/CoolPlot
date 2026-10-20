# -*- coding: utf-8 -*-
"""Scene diffing and renderers, without any property calculations."""
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from coolplot.render.base import Renderer
from coolplot.render.svg import SvgRenderer
from coolplot.render.ticks import ticks as _ticks
from coolplot.scene import AxesSpec, Line, LineStyle, Markers, Scene, Text, items_equal
from coolplot.core.units import EUR, SI, Unit


class RecordingRenderer(Renderer):
    """Remembers every backend call, to check what a sync touched."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def _set_axes(self, axes):
        self.calls.append(("axes", None))

    def _add(self, item):
        self.calls.append(("add", item.id))

    def _update(self, old, new):
        self.calls.append(("update", new.id))

    def _remove(self, item):
        self.calls.append(("remove", item.id))

    def _reorder(self, order):
        self.calls.append(("reorder", tuple(order)))

    def _set_legend(self, entries, style):
        self.calls.append(("legend", tuple(text for text, _ in entries)))


def _line(item_id, y0=0.0, color="black"):
    return Line(id=item_id, x=[0.0, 1.0, 2.0], y=[y0, y0 + 1.0, np.nan], style=LineStyle(color=color))


def test_unit_round_trip():
    for system in (SI, EUR):
        for key in ("T", "p", "h", "s", "rho", "u", "Q"):
            assert system[key].to_SI(system[key].from_SI(123.4)) == pytest.approx(123.4)
    assert EUR["T"].from_SI(273.15) == pytest.approx(0.0)
    assert EUR["P"].to_SI(1.0) == pytest.approx(1e5)  # aliases are accepted
    mpa = EUR.with_unit("p", Unit("MPa", 1e-6))
    assert mpa["p"].from_SI(1e6) == pytest.approx(1.0)
    assert EUR["p"].label == "bar"  # the original is untouched


def test_items_are_immutable_and_compared_by_value():
    a = _line("a")
    with pytest.raises(ValueError):
        a.x[0] = 5.0
    assert items_equal(a, _line("a"))  # NaN equals NaN here
    assert not items_equal(a, _line("a", y0=1.0))
    assert not items_equal(a, _line("a", color="red"))


def test_scene_keeps_old_object_for_equal_items():
    scene = Scene(items=[_line("a")])
    first = scene["a"]
    revision = scene.revision
    assert not scene.put(_line("a"))
    assert scene["a"] is first
    assert scene.revision == revision
    assert scene.put(_line("a", color="red"))
    assert scene.revision == revision + 1


def test_replace_all_rejects_duplicate_ids():
    with pytest.raises(ValueError):
        Scene().replace_all([_line("a"), _line("a")])


def test_renderer_only_touches_changed_items():
    scene = Scene(AxesSpec(x_label="x"), [_line("a"), _line("b"), _line("c")])
    renderer = RecordingRenderer()
    report = renderer.sync(scene)
    assert report.added == ["a", "b", "c"] and report.axes_changed

    renderer.calls.clear()
    scene.replace_all([_line("a"), _line("b", color="red"), _line("d")])
    report = renderer.sync(scene)
    assert report.updated == ["b"]
    assert report.added == ["d"]
    assert report.removed == ["c"]
    assert report.unchanged == 1
    assert ("add", "a") not in renderer.calls and ("update", "a") not in renderer.calls
    assert ("reorder", ("a", "b", "d")) in renderer.calls  # new item, restack
    assert not report.axes_changed

    renderer.calls.clear()
    report = renderer.sync(scene)
    assert not report.changed and renderer.calls == []

    scene.replace_all([_line("b", color="red"), _line("a"), _line("d")])
    report = renderer.sync(scene)
    assert report.reordered and not report.updated


def test_svg_renderer_regenerates_only_changed_elements():
    scene = Scene(AxesSpec(x_limits=(0.0, 2.0), y_limits=(0.1, 10.0), y_log=True),
                  [_line("a"), _line("b", y0=1.0),
                   Markers(id="m", x=[1.0], y=[1.0]),
                   Text(id="t", x=1.0, y=1.0, text="p < 5 & T > 3", direction=(1.0, 1.0))])
    svg = SvgRenderer()
    svg.sync(scene)
    doc = svg.to_svg()
    assert doc.startswith("<svg") and doc.endswith("</svg>")
    assert 'data-item="a"' in doc and 'data-item="m"' in doc
    assert "p &lt; 5 &amp; T &gt; 3" in doc
    doc.encode("ascii")  # the output is plain ASCII
    assert svg.elements_built == 4

    scene.put(_line("b", y0=2.0))
    svg.sync(scene)
    svg.to_svg()
    assert svg.elements_built == 5  # only "b" was rebuilt

    scene.set_axes(AxesSpec(x_limits=(0.0, 4.0), y_limits=(0.1, 10.0), y_log=True))
    svg.sync(scene)
    svg.to_svg()
    assert svg.elements_built == 9  # new mapping, everything rebuilt


def test_matplotlib_renderer_updates_artists_in_place():
    pytest.importorskip("matplotlib")
    from coolplot.render.mpl import MatplotlibRenderer

    scene = Scene(AxesSpec(x_limits=(0.0, 2.0), y_limits=(0.0, 3.0)), [_line("a"), _line("b")])
    renderer = MatplotlibRenderer(use_pyplot=False)
    renderer.sync(scene)
    artist_a, artist_b = renderer._artists["a"], renderer._artists["b"]
    assert len(renderer.ax.lines) == 2

    scene.replace_all([_line("a"), _line("b", y0=1.0, color="red")])
    renderer.sync(scene)
    assert renderer._artists["a"] is artist_a
    assert renderer._artists["b"] is artist_b  # same artist, new data
    assert artist_b.get_color() == "#ff0000"  # colours arrive normalised
    np.testing.assert_allclose(artist_b.get_ydata()[:2], [1.0, 2.0])

    scene.remove("a")
    renderer.sync(scene)
    assert len(renderer.ax.lines) == 1


def test_scene_validation():
    with pytest.raises(ValueError):
        Line(id="a", x=[0.0], y=[0.0], z_order=-1.0)
    with pytest.raises(ValueError):
        AxesSpec(x_limits=(0.0, float("nan")))
    assert AxesSpec(x_limits=(10.0, 0.0)).x_limits == (0.0, 10.0)   # stored ascending


def test_svg_survives_hostile_text_and_long_legends():
    from xml.etree import ElementTree
    long_text = "x" * 200
    scene = Scene(AxesSpec(title="bad\x01title", x_limits=(0.0, 1.0), y_limits=(0.0, 1.0)), [
        Line(id="a", x=[0.0, 1.0], y=[0.0, 1.0], legend=long_text),
        Text(id="t", x=0.5, y=0.5, text="ctrl\x02char"),
    ])
    svg = SvgRenderer(width=400, height=300, id_prefix="1 bad id")
    svg.sync(scene)
    doc = svg.to_svg()
    ElementTree.fromstring(doc)                       # still valid XML
    assert svg.describe_item("t")["text"] == "ctrlchar"
    assert svg.id_prefix[0].isalpha() and 'id="cp-1-bad-id-plot-area"' in doc
    width_pt, height_pt = svg.describe_axes()["plot_size_pt"]
    assert width_pt > 0.2 * 400 / (4.0 / 3.0)           # the legend did not eat the plot
    assert svg.describe_axes()["legend"][0][0].endswith("...")


def test_svg_stays_valid_xml_with_awkward_characters():
    import xml.etree.ElementTree as ET
    from coolplot.render.svg import SvgRenderer
    from coolplot.scene import AxesSpec, Line, Scene, Text
    from coolplot.style.values import Font, TextStyle
    bad = "a\x01b\x0bc\ud800d\uffff"
    scene = Scene(AxesSpec(x_limits=(0.0, 1.0), y_limits=(0.0, 1.0), title=bad), [
        Line(id="line/" + bad, x=[0.1, 0.9], y=[0.1, 0.9], legend=bad),
        Text(id="text/" + bad, x=0.5, y=0.5, text=bad,
             style=TextStyle(font=Font(family=("Fancy" + bad, "sans-serif")))),
    ])
    renderer = SvgRenderer()
    renderer.sync(scene)
    ET.fromstring(renderer.to_svg())   # raises if the document is not well-formed


def test_text_direction_has_to_be_finite():
    from coolplot.scene import Text
    for direction in ((float("nan"), 1.0), (0.0, 0.0), (1.0, float("inf"))):
        with pytest.raises(ValueError):
            Text(id="t", x=0.0, y=0.0, text="t", direction=direction)


def test_svg_and_web_refuse_other_formats(tmp_path):
    from coolplot.render.svg import SvgRenderer
    from coolplot.render.web import WebRenderer
    with pytest.raises(ValueError, match="SvgRenderer writes SVG"):
        SvgRenderer().save(str(tmp_path / "chart.pdf"))
    with pytest.raises(ValueError, match="WebRenderer writes HTML"):
        WebRenderer().save(str(tmp_path / "chart.svg"))
    SvgRenderer().save(str(tmp_path / "chart.SVG"))
    WebRenderer().save(str(tmp_path / "chart.htm"))


# Regression tests from the adversarial review of 0.2 ------------------------

def test_svg_margin_labels_stay_on_the_canvas():
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    diagram.title = "Margin labels"
    diagram.settings = diagram.settings.with_(labels={"mode": "margin"})
    diagram.set_lines("T", num=8, rounding=True, labels=True)
    renderer = diagram.draw(SvgRenderer())
    root = ET.fromstring(renderer.to_svg())
    ns = "{http://www.w3.org/2000/svg}"
    labels = [g for g in root.iter(ns + "g") if (g.get("class") or "").find("cp-role-isoline_label") >= 0]
    assert labels
    for group in labels:
        text = next(group.iter(ns + "text"))
        size_px = float(text.get("font-size"))
        # Vertical text reading upwards from its anchor: its far end
        assert float(text.get("y")) - 0.6 * size_px * len(text.text) >= 0.0
    # The title (its bottom edge at y) sits above the far ends of the labels
    title = next(t for t in root.iter(ns + "text") if t.get("class") == "cp-title")
    far_ends = [float(t.get("y")) - 0.6 * float(t.get("font-size")) * len(t.text)
                for g in labels for t in g.iter(ns + "text")]
    assert float(title.get("y")) <= min(far_ends)


def test_svg_ticks_on_a_narrow_log_range():
    assert len(_ticks(1.5, 1.9, True)) >= 2
