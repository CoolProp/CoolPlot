# -*- coding: utf-8 -*-
"""The web backend: patches, a real browser and input."""
import json
import random
from dataclasses import replace
from xml.etree import ElementTree

import numpy as np
import pytest

from coolplot.core.events import Click, DragEnd, Hover, ViewChanged
from coolplot.testing import check_events, run_conformance
from coolplot.render.web import WebRenderer
from coolplot.scene import AxesSpec, Line, Markers, Scene, Text
from coolplot.style.values import LineStyle, MarkerStyle


def _attached(browser, cls=WebRenderer):
    renderer = cls()
    renderer.attach_page(browser.new_page())
    return renderer


def _canonical(element):
    """Tag, attributes, text and children, comparable across serialisations."""
    tag = element.tag.split("}")[-1]
    return (tag, tuple(sorted(element.attrib.items())), (element.text or "").strip(),
            tuple(_canonical(child) for child in element))


def _browser_items(renderer):
    root = renderer._document()
    group = next(g for g in root.iter() if g.get("class") == "cp-items")
    return [_canonical(child) for child in group]


def _local_items(renderer):
    root = ElementTree.fromstring(renderer.to_svg())
    group = next(g for g in root.iter() if g.get("class") == "cp-items")
    return [_canonical(child) for child in group]


def test_web_passes_conformance_without_a_browser():
    assert run_conformance(WebRenderer) == []
    assert check_events(WebRenderer) == []


@pytest.mark.browser
def test_web_passes_conformance_in_a_browser(browser):
    assert run_conformance(lambda: _attached(browser)) == []


def _random_scene_steps(seed=1, steps=40):
    """Incremental changes that never touch the axes or the legend."""
    rng = random.Random(seed)
    axes = AxesSpec(x_limits=(0.0, 10.0), y_limits=(0.0, 10.0))
    items = {}

    def new(i):
        kind = rng.choice(["line", "markers", "text"])
        z = rng.choice([1.0, 2.0, 3.0])
        x, y = sorted(rng.uniform(0, 10) for _ in range(3)), [rng.uniform(0, 10) for _ in range(3)]
        if kind == "line":
            return Line(id="i{0}".format(i), x=x, y=y, z_order=z,
                        style=LineStyle(color=rng.choice(["#2a78d6", "#eb6834"]), width_pt=rng.choice([0.5, 1.0])))
        if kind == "markers":
            return Markers(id="i{0}".format(i), x=x, y=y, z_order=z, style=MarkerStyle(shape=rng.choice("os^")))
        return Text(id="i{0}".format(i), x=x[0], y=y[0], text="t{0}".format(rng.randint(0, 9)), z_order=z)

    for i in range(8):
        items["i{0}".format(i)] = new(i)
    yield Scene(axes, list(items.values()))
    counter = 8
    for _ in range(steps):
        action = rng.choice(["add", "remove", "move", "restack", "hide", "reorder"])
        ids = list(items)
        if action == "add" or not ids:
            items["i{0}".format(counter)] = new(counter)
            counter += 1
        elif action == "remove":
            items.pop(rng.choice(ids))
        elif action == "move":
            item_id = rng.choice(ids)
            item = items[item_id]
            items[item_id] = replace(item, x=item.x if isinstance(item, Text) else np.asarray(item.x) * 0.9) \
                if not isinstance(item, Text) else replace(item, x=item.x * 0.9)
        elif action == "restack":
            item_id = rng.choice(ids)
            items[item_id] = replace(items[item_id], z_order=rng.choice([1.0, 2.0, 3.0, 4.0]))
        elif action == "hide":
            item_id = rng.choice(ids)
            items[item_id] = replace(items[item_id], visible=not items[item_id].visible)
        else:
            order = list(items.items())
            rng.shuffle(order)
            items = dict(order)
        yield Scene(axes, list(items.values()))


@pytest.mark.browser
def test_incremental_patches_reproduce_the_document(browser):
    renderer = _attached(browser)
    ops = []
    renderer.listen(lambda m: ops.append(json.loads(m)["op"]))
    for scene in _random_scene_steps():
        renderer.sync(scene)
        assert _browser_items(renderer) == _local_items(renderer)
    # The sequence really used the incremental messages
    assert ops.count("reset") == 1
    assert {"put", "remove", "order"} <= set(ops)


@pytest.mark.browser
@pytest.mark.parametrize("dropped", ["put", "remove", "order"])
def test_a_client_that_drops_patches_is_caught(browser, dropped):
    class Lossy(WebRenderer):
        def attach_page(self, page):
            self._page = page
            page.set_content(self.page())
            self.listen(lambda m: None if json.loads(m)["op"] == dropped else
                        page.evaluate("m => window.coolplot.apply(JSON.parse(m))", m))

    renderer = _attached(browser, Lossy)
    mismatch = False
    for scene in _random_scene_steps():
        renderer.sync(scene)
        mismatch = mismatch or _browser_items(renderer) != _local_items(renderer)
    assert mismatch


def test_moving_one_item_sends_one_small_patch():
    renderer = WebRenderer()
    sent = []
    renderer.listen(sent.append)
    scene = Scene(AxesSpec(x_limits=(0.0, 10.0), y_limits=(0.0, 10.0)),
                  [Line(id="a", x=[0, 10], y=[0, 10]), Markers(id="b", x=[5.0], y=[5.0])])
    renderer.sync(scene)
    sent.clear()
    scene.put(replace(scene["b"], x=[6.0]))
    renderer.sync(scene)
    assert [json.loads(m)["op"] for m in sent] == ["put"] and len(sent[0]) < 500
    sent.clear()
    renderer.sync(scene)
    assert sent == []   # nothing changed, nothing sent


def test_pointer_input_becomes_events():
    renderer = WebRenderer()
    renderer.sync(Scene(AxesSpec(x_limits=(0.0, 10.0), y_limits=(1.0, 100.0), y_log=True),
                        [Markers(id="m", x=[2.0, 8.0], y=[10.0, 10.0])]))
    events = []
    renderer.connect(events.append)
    renderer.simulate_pointer("move", 8.0, 10.0)
    assert isinstance(events[-1], Hover) and events[-1].item_id == "m" and events[-1].index == 1
    assert events[-1].y == pytest.approx(10.0, rel=1e-6)   # log axis mapped back exactly
    renderer.simulate_pointer("press", 2.0, 10.0)
    renderer.simulate_pointer("move", 3.0, 20.0)
    renderer.simulate_pointer("release", 3.0, 20.0)
    assert isinstance(events[-1], DragEnd) and events[-1].index == 0
    # Dragging empty space pans, the wheel zooms
    events.clear()
    renderer.simulate_pointer("press", 5.0, 2.0)
    renderer.simulate_pointer("move", 6.0, 2.0)
    renderer.simulate_pointer("release", 6.0, 2.0)
    assert isinstance(events[0], ViewChanged)
    assert events[0].x_limits == pytest.approx((-1.0, 9.0), abs=1e-6)
    to_px, _ = renderer._mapper()
    px, py = (float(v) for v in to_px(5.0, 10.0))
    renderer.receive({"type": "wheel", "px": px, "py": py, "delta": -100})
    zoomed = events[-1]
    assert zoomed.x_limits[1] - zoomed.x_limits[0] == pytest.approx(10.0 / 1.2)
    renderer.receive(json.dumps({"type": "press", "px": 0.0, "py": 0.0}))
    renderer.receive({"type": "release", "px": 0.0, "py": 0.0})
    assert isinstance(events[-1], Click)


def test_input_is_checked():
    for bad in ({"type": "move", "px": float("nan"), "py": 0.0}, {"type": "move", "px": "1", "py": 0.0},
                {"type": "teleport", "px": 0.0, "py": 0.0}, {"type": "press", "px": 0, "py": 0, "button": 9},
                {"type": "view", "x_limits": [0, 1]}, {"type": "move", "px": True, "py": 0.0}, "[]"):
        with pytest.raises(ValueError):
            WebRenderer.check_input(bad)


def test_zoom_and_pan_on_log_axes_stay_usable():
    renderer = WebRenderer()
    renderer.sync(Scene(AxesSpec(x_limits=(0.0, 10.0), y_limits=(1e5, 1e7), y_log=True), []))
    views = []
    renderer.connect(views.append)
    bx, by, bw, bh = renderer._box
    for py in (by + bh, by):   # pointer at the bottom and at the top edge
        for _ in range(200):
            renderer.receive({"type": "wheel", "px": bx + bw / 2, "py": py, "delta": 100.0})
            if views:
                renderer.sync(Scene(AxesSpec(x_limits=views[-1].x_limits, y_limits=views[-1].y_limits,
                                             y_log=True), []))
        lo, hi = views[-1].y_limits
        assert 0.0 < lo < hi and np.log10(hi / lo) <= WebRenderer.MAX_DECADES + 1e-9
    # Zooming in stops before the view collapses
    for _ in range(500):
        renderer.receive({"type": "wheel", "px": bx + bw / 2, "py": by + bh / 2, "delta": -100.0})
        renderer.sync(Scene(AxesSpec(x_limits=views[-1].x_limits, y_limits=views[-1].y_limits, y_log=True), []))
    lo, hi = views[-1].y_limits
    assert hi > lo and np.isfinite([lo, hi]).all()
    # Panning up on the log axis shifts both limits by the same factor
    renderer.sync(Scene(AxesSpec(x_limits=(0.0, 10.0), y_limits=(1e5, 1e7), y_log=True), []))
    views.clear()
    renderer.receive({"type": "press", "px": bx + bw / 2, "py": by + bh / 2})
    renderer.receive({"type": "move", "px": bx + bw / 2, "py": by + bh / 2 + bh / 2})
    lo, hi = views[-1].y_limits
    assert (lo, hi) == pytest.approx((1e6, 1e8), rel=1e-9)
    # A trackpad delta is a fraction of a step
    renderer.receive({"type": "release", "px": 0.0, "py": 0.0})
    views.clear()
    renderer.receive({"type": "wheel", "px": bx + bw / 2, "py": by + bh / 2, "delta": 10.0})
    assert views[-1].x_limits[1] - views[-1].x_limits[0] == pytest.approx(10.0 * 1.2 ** 0.1)


def test_margin_does_not_grab_clipped_markers():
    renderer = WebRenderer()
    renderer.sync(Scene(AxesSpec(x_limits=(0.0, 10.0), y_limits=(0.0, 10.0)), [Markers(id="m", x=[-3.0], y=[5.0])]))
    to_px, _ = renderer._mapper()
    px, py = (float(v) for v in to_px(-3.0, 5.0))
    assert renderer._hit(px, py) == (None, None)


def test_markers_without_size_cannot_be_grabbed():
    from coolplot.style.values import MarkerStyle
    renderer = WebRenderer()
    hidden = MarkerStyle(size_pt=0.0, face_color="none", edge_color="none")
    renderer.sync(Scene(AxesSpec(x_limits=(0.0, 10.0), y_limits=(0.0, 10.0)),
                        [Markers(id="zone", x=[5.0], y=[5.0], style=hidden), Markers(id="m", x=[2.0], y=[2.0])]))
    to_px, _ = renderer._mapper()
    assert renderer._hit(*(float(v) for v in to_px(5.0, 5.0))) == (None, None)
    assert renderer._hit(*(float(v) for v in to_px(2.0, 2.0))) == ("m", 0)


def test_page_title_is_escaped_once():
    page = WebRenderer().page(title="a<b & c")
    assert "<title>a&lt;b &amp; c</title>" in page


def test_huge_numbers_are_refused():
    with pytest.raises(ValueError):
        WebRenderer.check_input('{"type": "move", "px": 1' + "0" * 400 + ', "py": 1}')
