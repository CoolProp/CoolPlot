# -*- coding: utf-8 -*-
"""A backend for the browser: SVG elements streamed as patches.

:class:`WebRenderer` builds exactly the SVG elements of
:class:`coolplot.render.svg.SvgRenderer`, but instead of writing a file it
sends what changed to a small JavaScript client as JSON messages:

* ``{"op": "reset", "svg": ...}`` the whole document, when the axes, the
  legend or the page layout changed (then every element moves anyway);
* ``{"op": "put", "id": ..., "svg": ...}`` one new or changed item;
* ``{"op": "remove", "id": ...}`` one removed item;
* ``{"op": "order", "ids": [...]}`` the new drawing order.

Dragging a state of a cycle therefore sends a few hundred bytes, not the
chart. Because the elements are those of the SVG backend, the browser
shows exactly what the SVG backend would write.

The client sends raw pointer input back (``{"type": "move" | "press" |
"release" | "wheel", "px": ..., "py": ...}`` in SVG pixels). The renderer
turns it into the events of :mod:`coolplot.core.events`: hit testing
happens here in Python, so input from a test and from a real browser take
exactly the same path. Dragging empty space pans and the mouse wheel
zooms; both arrive as ``ViewChanged``.

Messages go to the functions registered with :meth:`WebRenderer.listen`.
:class:`WebServer` is a small development server without dependencies:
it serves the page, streams the messages with server-sent events and
receives the input. For production, connect ``listen`` and ``receive`` to
your own web framework or websocket.
"""
from __future__ import annotations

import json
import math
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, List, Optional, Tuple
from xml.etree import ElementTree
from xml.sax.saxutils import quoteattr

import numpy as np

from ..core.events import Click, Drag, DragEnd, DragStart, Hover, ViewChanged
from ..scene import AxesSpec, Line, Markers
from .base import SyncReport
from .svg import PX_PER_PT, SvgRenderer

#: The JavaScript client. Plain ES2017, no libraries; ASCII only.
CLIENT_JS = r"""
(function () {
  "use strict";
  var root = document.getElementById("coolplot-root");
  var NS = "http://www.w3.org/2000/svg";
  function fragment(text) {
    var doc = new DOMParser().parseFromString('<svg xmlns="' + NS + '">' + text + "</svg>", "image/svg+xml");
    return document.importNode(doc.documentElement.firstElementChild, true);
  }
  function items() { return root.querySelector("g.cp-items"); }
  function find(id) {
    var group = items();
    if (!group) { return null; }
    for (var i = 0; i < group.children.length; i++) {
      if (group.children[i].getAttribute("data-item") === id) { return group.children[i]; }
    }
    return null;
  }
  function apply(msg) {
    if (msg.op === "reset") {
      root.innerHTML = msg.svg;
    } else if (msg.op === "put") {
      var element = fragment(msg.svg), old = find(msg.id);
      if (old) { old.replaceWith(element); } else { items().appendChild(element); }
    } else if (msg.op === "remove") {
      var gone = find(msg.id);
      if (gone) { gone.remove(); }
    } else if (msg.op === "order") {
      var group = items();
      msg.ids.forEach(function (id) { var el = find(id); if (el) { group.appendChild(el); } });
    }
  }
  window.coolplot = { apply: apply };

  var input = root.getAttribute("data-input");
  function send(msg) {
    if (input) { fetch(input, { method: "POST", body: JSON.stringify(msg) }); }
  }
  function position(event) {
    var svg = root.querySelector("svg");
    var box = svg.getBoundingClientRect(), view = svg.viewBox.baseVal;
    return [(event.clientX - box.left) * view.width / box.width,
            (event.clientY - box.top) * view.height / box.height];
  }
  var pending = null;
  root.addEventListener("mousemove", function (event) {
    var p = position(event);
    if (pending === null) {
      requestAnimationFrame(function () { send(pending); pending = null; });
    }
    pending = { type: "move", px: p[0], py: p[1] };
  });
  root.addEventListener("mousedown", function (event) {
    var p = position(event);
    event.preventDefault();
    send({ type: "press", px: p[0], py: p[1], button: event.button + 1 });
  });
  root.addEventListener("mouseup", function (event) {
    var p = position(event);
    send({ type: "release", px: p[0], py: p[1], button: event.button + 1 });
  });
  root.addEventListener("wheel", function (event) {
    var p = position(event);
    event.preventDefault();
    send({ type: "wheel", px: p[0], py: p[1], delta: event.deltaY });
  }, { passive: false });

  var stream = root.getAttribute("data-stream");
  if (stream) {
    var source = new EventSource(stream);
    source.onmessage = function (event) { apply(JSON.parse(event.data)); };
  }
})();
"""

PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ margin: 0; }}
#coolplot-root svg {{ max-width: 100%; height: auto; user-select: none; }}
</style>
</head>
<body>
<div id="coolplot-root"{attributes}>
{svg}
</div>
<script>{script}</script>
</body>
</html>
"""


class WebRenderer(SvgRenderer):
    """Stream a scene to browsers, see the module docstring

    Takes the same arguments as :class:`coolplot.render.svg.SvgRenderer`.
    """

    capabilities = frozenset({"file_output", "css_classes", "events", "interactive"})
    default_suffix = ".html"

    #: Points within this distance (in points) of a marker or line hit it.
    PICK_RADIUS_PT = 5.0
    #: Zoom factor per wheel step.
    ZOOM_STEP = 1.2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = threading.RLock()
        self._listeners: List[Callable[[str], None]] = []
        self._sent_head = self._sent_tail = None
        self._sent_items: Dict[str, str] = {}
        self._sent_order: List[str] = []
        self._press = None
        self._page = None
        self.messages_sent = 0

    # Sending ----------------------------------------------------------------
    def listen(self, callback: Callable[[str], None]) -> Callable[[str], None]:
        """Call ``callback(message)`` with every patch, as a JSON string."""
        with self._lock:
            self._listeners.append(callback)
        return callback

    def unlisten(self, callback):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def snapshot(self) -> str:
        """A reset message with the current document, for a new client."""
        with self._lock:
            return json.dumps({"op": "reset", "svg": self.to_svg()})

    def _send(self, message: dict):
        text = json.dumps(message)
        self.messages_sent += 1
        for callback in list(self._listeners):
            callback(text)

    def sync(self, scene):
        with self._lock:
            return super().sync(scene)

    def _finish(self, report: SyncReport):
        super()._finish(report)
        if not report.changed:
            return
        head, items, tail = self._document_parts()
        if head != self._sent_head or tail != self._sent_tail:
            # Axes, legend or page layout changed: every element moved
            self._send({"op": "reset", "svg": "\n".join([head, '<g class="cp-items">'] + [e for _, e in items]
                                                       + ["</g>", tail])})
        else:
            current = dict(items)
            for item_id, element in items:
                if self._sent_items.get(item_id) != element:
                    self._send({"op": "put", "id": item_id, "svg": element})
            for item_id in self._sent_items:
                if item_id not in current:
                    self._send({"op": "remove", "id": item_id})
            order = [i for i, _ in items]
            if order != [i for i in self._sent_order if i in current]:
                self._send({"op": "order", "ids": order})
        self._sent_head, self._sent_tail = head, tail
        self._sent_items = dict(items)
        self._sent_order = [i for i, _ in items]

    # The page -----------------------------------------------------------------
    def page(self, stream: Optional[str] = None, input: Optional[str] = None, title: str = "CoolPlot") -> str:
        """A complete HTML page with the current chart and the client.

        ``stream`` is the URL of a server-sent event stream with patches,
        ``input`` the URL the client posts pointer input to. Without them
        the page is a static, self-contained chart.
        """
        attributes = ""
        if stream:
            attributes += " data-stream=" + quoteattr(stream)
        if input:
            attributes += " data-input=" + quoteattr(input)
        text = PAGE.format(title=title.replace("<", "&lt;").replace("&", "&amp;"), attributes=attributes,
                           svg=self.to_svg(), script=CLIENT_JS)
        return text.encode("ascii", "xmlcharrefreplace").decode("ascii")

    def save(self, path):
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write(self.page())

    # Reading back from a real browser -------------------------------------------
    def attach_page(self, page):
        """Mirror the chart into a browser page (for example a Playwright page).

        The page gets the static HTML, then every patch is applied there as
        it is sent, and :meth:`describe_item` and :meth:`describe_axes` read
        the document back from the browser: what the conformance kit then
        checks is what the browser shows after applying the patches.
        """
        self._page = page
        page.set_content(self.page())
        self.listen(lambda message: page.evaluate("m => window.coolplot.apply(JSON.parse(m))", message))

    def _document(self):
        if self._page is None:
            return super()._document()
        if self._parsed is None:
            markup = self._page.evaluate("document.querySelector('#coolplot-root svg').outerHTML")
            self._parsed = ElementTree.fromstring(markup)
        return self._parsed

    # Input from the browser -------------------------------------------------------
    def receive(self, message):
        """Handle one input message from the client (a dict or JSON text)."""
        if isinstance(message, str):
            message = json.loads(message)
        with self._lock:
            kind = message.get("type")
            if kind == "view":
                self._emit(ViewChanged(tuple(message["x_limits"]), tuple(message["y_limits"])))
                return
            px, py = float(message["px"]), float(message["py"])
            x, y = self._from_px(px, py)
            if kind == "move":
                self._on_move(px, py, x, y)
            elif kind == "press":
                item_id, index = self._hit(px, py)
                draggable = isinstance(self._items.get(item_id), Markers) and index is not None
                self._press = dict(item_id=item_id, index=index, draggable=draggable, px=px, py=py,
                                   limits=tuple(self._limits()), moved=False, button=int(message.get("button", 1)))
            elif kind == "release":
                press, self._press = self._press, None
                if press is None:
                    return
                if press["moved"] and press["draggable"]:
                    self._emit(DragEnd(press["item_id"], press["index"], x, y))
                elif not press["moved"]:
                    self._emit(Click(x, y, press["item_id"], press["index"], press["button"]))
            elif kind == "wheel":
                self._zoom(px, py, float(message.get("delta", 0.0)))

    def _on_move(self, px, py, x, y):
        press = self._press
        if press is None:
            item_id, index = self._hit(px, py)
            self._emit(Hover(x, y, item_id, index))
            return
        if not press["moved"] and math.hypot(px - press["px"], py - press["py"]) < 1.0:
            return   # jitter of a click
        first = not press["moved"]
        press["moved"] = True
        if press["draggable"]:
            if first:
                self._emit(DragStart(press["item_id"], press["index"], x, y))
            self._emit(Drag(press["item_id"], press["index"], x, y))
        else:
            # Dragging empty space pans the view
            self._emit(ViewChanged(*self._shifted(press["limits"], px - press["px"], py - press["py"])))

    def _shifted(self, limits, dx_px, dy_px):
        axes = self._axes or AxesSpec()
        bx, by, bw, bh = self._box
        out = []
        for (lo, hi), log, shift in ((limits[0], axes.x_log, -dx_px / bw), (limits[1], axes.y_log, dy_px / bh)):
            if log:
                span = math.log10(hi) - math.log10(lo)
                out.append((lo * 10 ** (shift * span), hi * 10 ** (shift * span)))
            else:
                out.append((lo + shift * (hi - lo), hi + shift * (hi - lo)))
        return tuple(out)

    def _zoom(self, px, py, delta):
        if delta == 0.0:
            return
        factor = self.ZOOM_STEP if delta > 0 else 1.0 / self.ZOOM_STEP   # wheel down zooms out
        axes = self._axes or AxesSpec()
        bx, by, bw, bh = self._box
        fractions = ((px - bx) / bw, 1.0 - (py - by) / bh)
        out = []
        for (lo, hi), log, f in zip(self._limits(), (axes.x_log, axes.y_log), fractions):
            a, b = (math.log10(lo), math.log10(hi)) if log else (lo, hi)
            centre = a + f * (b - a)
            a, b = centre + (a - centre) * factor, centre + (b - centre) * factor
            out.append((10 ** a, 10 ** b) if log else (a, b))
        self._emit(ViewChanged(*out))

    def _from_px(self, px: float, py: float) -> Tuple[float, float]:
        axes = self._axes or AxesSpec()
        (x0, x1), (y0, y1) = self._limits()
        bx, by, bw, bh = self._box
        fx, fy = (px - bx) / bw, 1.0 - (py - by) / bh

        def value(f, lo, hi, log):
            if log:
                return 10.0 ** (math.log10(lo) + f * (math.log10(hi) - math.log10(lo)))
            return lo + f * (hi - lo)
        return value(fx, x0, x1, axes.x_log), value(fy, y0, y1, axes.y_log)

    def _hit(self, px: float, py: float):
        """(item_id, index) of the topmost visible line or marker within the pick radius."""
        to_px, _ = self._mapper()
        radius = self.PICK_RADIUS_PT * PX_PER_PT
        for item_id in reversed(self._order):
            item = self._items.get(item_id)
            if item is None or not item.visible or not isinstance(item, (Line, Markers)):
                continue
            xs, ys = (np.asarray(v, dtype=float) for v in to_px(item.x, item.y))
            if isinstance(item, Markers):
                reach = max(radius, item.style.size_pt * PX_PER_PT / 2.0)
                dist = np.hypot(xs - px, ys - py)
                dist[~np.isfinite(dist)] = np.inf
                if len(dist) and dist.min() <= reach:
                    return item_id, int(np.argmin(dist))
            elif len(xs) >= 2:
                ax, ay, bx_, by_ = xs[:-1], ys[:-1], xs[1:], ys[1:]
                dx, dy = bx_ - ax, by_ - ay
                length2 = dx * dx + dy * dy
                with np.errstate(invalid="ignore", divide="ignore"):
                    t = np.clip(((px - ax) * dx + (py - ay) * dy) / length2, 0.0, 1.0)
                dist = np.hypot(ax + t * dx - px, ay + t * dy - py)
                dist[~np.isfinite(dist)] = np.inf
                if dist.min() <= radius:
                    return item_id, int(np.argmin(dist))
        return None, None

    # For tests and the conformance kit: the same path as browser input
    def simulate_pointer(self, kind: str, x: float, y: float, button: int = 1):
        to_px, _ = self._mapper()
        px, py = (float(v) for v in to_px(x, y))
        self.receive({"type": kind, "px": px, "py": py, "button": button})

    def simulate_view(self, x_limits, y_limits):
        self.receive({"type": "view", "x_limits": list(x_limits), "y_limits": list(y_limits)})


# ---------------------------------------------------------------------------
# A development server
# ---------------------------------------------------------------------------
class WebServer:
    """Serve one renderer to browsers, without dependencies

    ``/`` is the page, ``/stream`` the server-sent event stream of patches
    (a new client first gets the whole chart), ``/input`` receives pointer
    input. Run it with :meth:`start` (in a background thread) and stop it
    with :meth:`stop`. Meant for development and small tools; it binds to
    the local machine by default.
    """

    def __init__(self, renderer: WebRenderer, host: str = "127.0.0.1", port: int = 0, title: str = "CoolPlot"):
        self.renderer = renderer
        self.title = title
        self._clients: List[queue.Queue] = []
        self._clients_lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass   # keep the console quiet

            def do_GET(self):
                if self.path == "/":
                    body = server.renderer.page(stream="/stream", input="/input", title=server.title).encode("ascii")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/stream":
                    self._stream()
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.path != "/input":
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", 0))
                message = json.loads(self.rfile.read(length) or b"{}")
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                server.renderer.receive(message)

            def _stream(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                client = queue.Queue()
                client.put(server.renderer.snapshot())
                with server._clients_lock:
                    server._clients.append(client)
                try:
                    while not server._stopping.is_set():
                        try:
                            message = client.get(timeout=1.0)
                        except queue.Empty:
                            self.wfile.write(b": keep-alive\n\n")
                            self.wfile.flush()
                            continue
                        self.wfile.write(b"data: " + message.encode("ascii") + b"\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    with server._clients_lock:
                        server._clients.remove(client)

        self._stopping = threading.Event()
        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._httpd.daemon_threads = True
        self._thread = None
        renderer.listen(self._broadcast)

    def _broadcast(self, message: str):
        with self._clients_lock:
            for client in self._clients:
                client.put(message)

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return "http://{0}:{1}/".format(host, port)

    def start(self) -> "WebServer":
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def serve_forever(self):
        """Serve in the current thread until interrupted."""
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self._stopping.set()
        self._httpd.shutdown()
        self._httpd.server_close()
        self.renderer.unlisten(self._broadcast)
