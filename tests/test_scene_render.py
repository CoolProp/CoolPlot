# -*- coding: utf-8 -*-
"""Scene diffing and renderers, without any property calculations."""
import numpy as np
import pytest

from CoolPlot.render.base import Renderer
from CoolPlot.render.svg import SvgRenderer
from CoolPlot.scene import AxesSpec, Line, LineStyle, Markers, Scene, Text, items_equal
from CoolPlot.units import EUR, SI, Unit


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
    assert not report.axes_changed

    renderer.calls.clear()
    report = renderer.sync(scene)
    assert not report.changed and renderer.calls == []


def test_svg_renderer_regenerates_only_changed_elements():
    scene = Scene(AxesSpec(x_limits=(0.0, 2.0), y_limits=(0.1, 10.0), y_log=True),
                  [_line("a"), _line("b", y0=1.0),
                   Markers(id="m", x=[1.0], y=[1.0]),
                   Text(id="t", x=1.0, y=1.0, text="p < 5 & T > 3", direction=(1.0, 1.0))])
    svg = SvgRenderer()
    svg.sync(scene)
    doc = svg.to_svg()
    assert doc.startswith("<svg") and doc.endswith("</svg>")
    assert 'id="a"' in doc and 'id="m"' in doc
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
    from CoolPlot.render.mpl import MatplotlibRenderer

    scene = Scene(AxesSpec(x_limits=(0.0, 2.0), y_limits=(0.0, 3.0)), [_line("a"), _line("b")])
    renderer = MatplotlibRenderer(use_pyplot=False)
    renderer.sync(scene)
    artist_a, artist_b = renderer._artists["a"], renderer._artists["b"]
    assert len(renderer.ax.lines) == 2

    scene.replace_all([_line("a"), _line("b", y0=1.0, color="red")])
    renderer.sync(scene)
    assert renderer._artists["a"] is artist_a
    assert renderer._artists["b"] is artist_b  # same artist, new data
    assert artist_b.get_color() == "red"
    np.testing.assert_allclose(artist_b.get_ydata()[:2], [1.0, 2.0])

    scene.remove("a")
    renderer.sync(scene)
    assert len(renderer.ax.lines) == 1
