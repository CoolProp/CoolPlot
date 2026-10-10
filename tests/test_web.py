# -*- coding: utf-8 -*-
"""The web backend: patches, a real browser, input and the development server."""
import glob
import json
import random
import threading
import time
import urllib.request
from dataclasses import replace
from xml.etree import ElementTree

import numpy as np
import pytest

from coolplot.core.events import Click, DragEnd, Hover, ViewChanged
from coolplot.render.testing import check_events, run_conformance
from coolplot.render.web import WebRenderer, WebServer
from coolplot.scene import AxesSpec, Line, Markers, Scene, Text
from coolplot.style.values import LineStyle, MarkerStyle


def _chromium():
    pytest.importorskip("playwright")
    found = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    if not found:
        pytest.skip("no Chromium for Playwright")
    return found[-1]


@pytest.fixture(scope="module")
def browser():
    exe = _chromium()   # skips first when Playwright or Chromium is missing
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe)
        yield b
        b.close()


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


def test_development_server_end_to_end(browser):
    from coolplot import PropertyDiagram
    from coolplot.interaction import Interaction
    diagram = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    diagram.set_isolines("Q", num=3)
    diagram.add_cycle("Heat pump", [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
                                    {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}])
    renderer = WebRenderer()
    hovered = threading.Event()
    Interaction(diagram, renderer, on_hover=lambda state, event: event.item_id and hovered.set())
    renderer.sync(diagram.update_scene(renderer.plot_size_pt()))
    server = WebServer(renderer).start()
    try:
        page_html = urllib.request.urlopen(server.url).read().decode("ascii")
        assert 'data-stream="/stream"' in page_html
        page = browser.new_page()
        page.goto(server.url)
        page.wait_for_selector("g.cp-items g[data-item='cycle/Heat pump/states']")
        # Move the real mouse onto state 1 of the cycle
        s1 = diagram.cycle_states("Heat pump")[1]
        to_px, _ = renderer._mapper()
        px, py = (float(v) for v in to_px(s1.h / 1e3, s1.p / 1e5))
        box = page.evaluate("(() => { const b = document.querySelector('#coolplot-root svg')"
                            ".getBoundingClientRect(); return [b.left, b.top]; })()")
        page.mouse.move(box[0] + px, box[1] + py)
        assert hovered.wait(10.0)
        # Drag state 3 to a higher pressure: the browser receives the patches
        s3 = diagram.cycle_states("Heat pump")[3]
        x3, y3 = (float(v) for v in to_px(s3.h / 1e3, s3.p / 1e5))
        x4, y4 = (float(v) for v in to_px(s3.h / 1e3, 20.0))
        page.mouse.move(box[0] + x3, box[1] + y3)
        page.mouse.down()
        page.mouse.move(box[0] + x4, box[1] + y4, steps=5)
        page.mouse.up()
        page.wait_for_function("document.querySelector(\"g[data-item='cycle/Heat pump/number/3'] text\")"
                               ".getAttribute('y') < %f" % (y3 - 10.0), timeout=10000)
        assert diagram.cycle_states("Heat pump")[3].p > 18e5
        page.close()
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# Input from the network and the development server
# ---------------------------------------------------------------------------
def _post(server, body, headers=None):
    import http.client
    host, port = server._httpd.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=5)
    sent = {"Content-Type": "application/json", "Host": "127.0.0.1:{0}".format(port)}
    sent.update(headers or {})
    connection.request("POST", "/input", body=body, headers=sent)
    status = connection.getresponse().status
    connection.close()
    return status


def test_server_accepts_only_its_own_page():
    renderer = WebRenderer()
    renderer.sync(Scene(AxesSpec(x_limits=(0.0, 10.0), y_limits=(0.0, 10.0)), []))
    events = []
    renderer.connect(events.append)
    server = WebServer(renderer).start()
    port = server._httpd.server_address[1]
    move = json.dumps({"type": "move", "px": 100.0, "py": 100.0})
    try:
        assert _post(server, move, {"Origin": "http://127.0.0.1:{0}".format(port)}) == 204
        assert _post(server, move) == 204   # no Origin: not from a browser page
        assert len(events) == 2
        assert _post(server, move, {"Origin": "http://evil.example"}) == 403
        assert _post(server, move, {"Host": "evil.example"}) == 403   # DNS rebinding
        assert _post(server, move, {"Content-Type": "text/plain"}) == 415   # a "simple" cross-site request
        assert _post(server, "{not json") == 400
        assert _post(server, '{"type": "move", "px": NaN, "py": 1}') == 400
        assert _post(server, '{"type": "move"}') == 400
        assert _post(server, "[1, 2]") == 400
        assert _post(server, "x" * (WebServer.MAX_INPUT + 1)) == 413
        assert len(events) == 2
    finally:
        server.stop()


def test_server_stops_without_starting():
    server = WebServer(WebRenderer())
    done = threading.Event()
    threading.Thread(target=lambda: (server.stop(), done.set()), daemon=True).start()
    assert done.wait(5.0)


def test_a_browser_that_stops_reading_is_dropped():
    import queue
    server = WebServer(WebRenderer())
    client = queue.Queue(maxsize=2)
    client.dropped = False
    server._clients.append(client)
    for i in range(3):
        server._broadcast("message {0}".format(i))
    assert client.dropped and client.qsize() == 2
    server.stop()


def test_no_patch_is_lost_while_a_browser_connects():
    # A sync from another thread while the server takes the snapshot for a
    # new browser: the browser gets either the old snapshot and the patch,
    # or the new snapshot, never the old snapshot alone.
    import http.client
    renderer = WebRenderer()
    scene = Scene(AxesSpec(x_limits=(0.0, 10.0), y_limits=(0.0, 10.0)), [Markers(id="m", x=[5.0], y=[5.0])])
    renderer.sync(scene)
    original = renderer.snapshot

    def slow_snapshot():
        text = original()
        moved = Scene(scene.axes, [replace(scene["m"], x=[6.0])])
        worker = threading.Thread(target=renderer.sync, args=(moved,))
        worker.start()
        worker.join(0.3)   # blocks on the renderer's lock until the browser is registered
        return text

    renderer.snapshot = slow_snapshot
    server = WebServer(renderer).start()
    host, port = server._httpd.server_address[:2]
    try:
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/stream")
        response = connection.getresponse()
        ops = []
        deadline = time.monotonic() + 5.0   # keep-alive lines arrive every second, so no socket timeout
        while len(ops) < 2 and time.monotonic() < deadline:
            line = response.readline().decode("ascii").strip()
            if line.startswith("data: "):
                ops.append(json.loads(line[6:])["op"])
        assert ops == ["reset", "put"]
        connection.close()
    finally:
        server.stop()


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


def test_page_title_is_escaped_once():
    page = WebRenderer().page(title="a<b & c")
    assert "<title>a&lt;b &amp; c</title>" in page
