# -*- coding: utf-8 -*-
"""The development server of examples/web_app: Host and Origin checks, streams, input."""
import importlib.util
import json
import os
import threading
import time
import urllib.request
from dataclasses import replace

import pytest

from coolplot.render.web import WebRenderer
from coolplot.scene import AxesSpec, Markers, Scene

_PATH = os.path.join(os.path.dirname(__file__), "..", "examples", "web_app", "server.py")
_spec = importlib.util.spec_from_file_location("coolplot_web_app_server", _PATH)
_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server)
WebServer = _server.WebServer


@pytest.mark.browser
def test_development_server_end_to_end(browser):
    from coolplot import PropertyDiagram
    from coolplot.interaction import Interaction
    diagram = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    diagram.set_lines("Q", num=3)
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
        deadline = time.monotonic() + 5.0   # the server answers before it handles the input
        while len(events) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
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


def test_a_dropped_stream_closes_its_connection():
    import http.client
    renderer = WebRenderer()
    renderer.sync(Scene(AxesSpec(x_limits=(0.0, 1.0), y_limits=(0.0, 1.0)), []))
    server = WebServer(renderer).start()
    host, port = server._httpd.server_address[:2]
    try:
        connection = http.client.HTTPConnection(host, port, timeout=10)
        connection.request("GET", "/stream")
        response = connection.getresponse()
        response.readline()
        deadline = time.monotonic() + 5.0
        while not server._clients and time.monotonic() < deadline:
            time.sleep(0.01)
        server._clients[0].dropped = True
        start = time.monotonic()
        while response.readline():
            pass   # until the server closes the socket
        assert time.monotonic() - start < 5.0   # not the 30 s socket timeout
        connection.close()
    finally:
        server.stop()
