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

import html
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
  var queue = Promise.resolve();
  function send(msg) {
    // One request after the other, so a quick click never arrives as release before press
    if (!input) { return; }
    queue = queue.then(function () {
      return fetch(input, { method: "POST", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(msg) });
    }).catch(function () {});
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
  window.addEventListener("mouseup", function (event) {   // also a release outside the chart
    var p = position(event);
    send({ type: "release", px: p[0], py: p[1], button: event.button + 1 });
  });
  root.addEventListener("wheel", function (event) {
    var p = position(event);
    event.preventDefault();
    // deltaY in pixels: about 100 per notch of a mouse wheel, less per trackpad event
    var scale = event.deltaMode === 1 ? 33 : (event.deltaMode === 2 ? 800 : 1);
    send({ type: "wheel", px: p[0], py: p[1], delta: event.deltaY * scale });
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
    #: A press that moves less than this (SVG pixels) is still a click.
    CLICK_SLOP_PX = 4.0
    #: Zoom factor per wheel step (a wheel delta of 100 pixels, one notch).
    ZOOM_STEP = 1.2
    #: Largest and smallest span of a view: decades on log axes, and
    #: relative to the size of the values on linear axes.
    MAX_DECADES = 30.0
    MIN_SPAN = 1e-9

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
        """Call ``callback(message)`` with every patch, as a JSON string.

        Callbacks run while the renderer is locked, in the thread that
        calls :meth:`sync`, so they should only hand the message on (put it
        in a queue, write it to a socket) and return quickly.
        """
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

    def to_svg(self) -> str:
        with self._lock:   # another thread may be in sync
            return super().to_svg()

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
        text = PAGE.format(title=html.escape(title), attributes=attributes,
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
            with self._lock:
                return super()._document()
        if self._parsed is None:
            markup = self._page.evaluate("document.querySelector('#coolplot-root svg').outerHTML")
            self._parsed = ElementTree.fromstring(markup)
        return self._parsed

    # Input from the browser -------------------------------------------------------
    @staticmethod
    def check_input(message) -> dict:
        """The input message as a clean dict, or ValueError.

        Input comes from the network, so everything is checked: the type,
        and that every number is finite (JSON text may hold NaN).
        """
        if isinstance(message, (str, bytes)):
            message = json.loads(message)   # JSONDecodeError is a ValueError
        if not isinstance(message, dict):
            raise ValueError("An input message is a JSON object, not {0}.".format(type(message).__name__))

        def number(value):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("Expected a number, got {0!r}.".format(value))
            try:
                value = float(value)   # a huge JSON integer overflows here
            except OverflowError:
                value = math.inf
            if not math.isfinite(value):
                raise ValueError("Expected a finite number, got {0!r}.".format(value))
            return value

        kind = message.get("type")
        if kind == "view":
            limits = [message.get("x_limits"), message.get("y_limits")]
            if not all(isinstance(v, (list, tuple)) and len(v) == 2 for v in limits):
                raise ValueError("A view message needs x_limits and y_limits, two numbers each.")
            return {"type": kind, "x_limits": tuple(number(v) for v in limits[0]),
                    "y_limits": tuple(number(v) for v in limits[1])}
        if kind not in ("move", "press", "release", "wheel"):
            raise ValueError("Unknown input type {0!r}.".format(kind))
        out = {"type": kind, "px": number(message.get("px")), "py": number(message.get("py"))}
        if kind in ("press", "release"):
            button = message.get("button", 1)
            if button not in (1, 2, 3, 4, 5):
                raise ValueError("Unknown mouse button {0!r}.".format(button))
            out["button"] = int(button)
        if kind == "wheel":
            out["delta"] = number(message.get("delta", 0.0))
        return out

    def receive(self, message):
        """Handle one input message from the client (a dict or JSON text).

        Raises ValueError for a malformed message, see :meth:`check_input`.
        """
        message = self.check_input(message)
        with self._lock:
            kind = message["type"]
            if kind == "view":
                view = self._valid_view((message["x_limits"], message["y_limits"]))
                if view is not None:
                    self._emit(ViewChanged(*view))
                return
            px, py = message["px"], message["py"]
            x, y = self._from_px(px, py)
            if kind == "move":
                self._on_move(px, py, x, y)
            elif kind == "press":
                item_id, index = self._hit(px, py)
                draggable = isinstance(self._items.get(item_id), Markers) and index is not None
                self._press = dict(item_id=item_id, index=index, draggable=draggable, px=px, py=py,
                                   limits=tuple(self._limits()), moved=False, button=message["button"])
            elif kind == "release":
                press, self._press = self._press, None
                if press is None:
                    return
                if press["moved"] and press["draggable"]:
                    self._emit(DragEnd(press["item_id"], press["index"], x, y))
                elif not press["moved"]:
                    self._emit(Click(x, y, press["item_id"], press["index"], press["button"]))
            elif kind == "wheel":
                self._zoom(px, py, message["delta"])

    def _on_move(self, px, py, x, y):
        press = self._press
        if press is None:
            item_id, index = self._hit(px, py)
            self._emit(Hover(x, y, item_id, index))
            return
        if not press["moved"] and math.hypot(px - press["px"], py - press["py"]) < self.CLICK_SLOP_PX:
            return   # jitter of a click
        first = not press["moved"]
        press["moved"] = True
        if press["draggable"]:
            if first:
                self._emit(DragStart(press["item_id"], press["index"], x, y))
            self._emit(Drag(press["item_id"], press["index"], x, y))
        else:
            # Dragging empty space pans the view
            view = self._valid_view(self._shifted(press["limits"], px - press["px"], py - press["py"]))
            if view is not None:
                self._emit(ViewChanged(*view))

    # Views are worked out on the axis scale: log10 of the values on log
    # axes, so zooming and panning feel the same on both kinds of axes.
    def _shifted(self, limits, dx_px, dy_px):
        axes = self._axes or AxesSpec()
        bx, by, bw, bh = self._box
        out = []
        for (lo, hi), log, shift in ((limits[0], axes.x_log, -dx_px / bw), (limits[1], axes.y_log, dy_px / bh)):
            a, b = (math.log10(lo), math.log10(hi)) if log else (lo, hi)
            out.append((a + shift * (b - a), b + shift * (b - a), log))
        return out

    def _zoom(self, px, py, delta):
        if delta == 0.0:
            return
        # One notch of a mouse wheel (100 pixels) is one step; a trackpad
        # sends many small deltas, each a fraction of a step
        steps = max(-1.0, min(1.0, delta / 100.0))
        factor = self.ZOOM_STEP ** steps   # wheel down (positive delta) zooms out
        axes = self._axes or AxesSpec()
        bx, by, bw, bh = self._box
        fractions = ((px - bx) / bw, 1.0 - (py - by) / bh)
        out = []
        for (lo, hi), log, f in zip(self._limits(), (axes.x_log, axes.y_log), fractions):
            a, b = (math.log10(lo), math.log10(hi)) if log else (lo, hi)
            centre = a + f * (b - a)
            out.append((centre + (a - centre) * factor, centre + (b - centre) * factor, log))
        view = self._valid_view(out)
        if view is not None:
            self._emit(ViewChanged(*view))

    def _valid_view(self, view):
        """The view as ((x0, x1), (y0, y1)), or None when it is not usable.

        ``view`` holds (lo, hi) per axis in data values or, from
        :meth:`_shifted` and :meth:`_zoom`, (a, b, log) on the axis scale.
        A view that would overflow, invert or shrink to nothing is refused,
        so zooming far out or in simply stops.
        """
        axes = self._axes or AxesSpec()
        out = []
        for limits, log in zip(view, (axes.x_log, axes.y_log)):
            if len(limits) == 3:
                a, b, log = limits
            else:
                lo, hi = limits
                if log and not (lo > 0.0 and hi > 0.0):
                    return None
                a, b = (math.log10(lo), math.log10(hi)) if log else (lo, hi)
            if not (math.isfinite(a) and math.isfinite(b) and b > a):
                return None
            if log:
                if not (-300.0 < a and b < 300.0 and self.MIN_SPAN < b - a <= self.MAX_DECADES):
                    return None
                out.append((10.0 ** a, 10.0 ** b))
            else:
                size = max(abs(a), abs(b))
                if not (b - a > self.MIN_SPAN * size and size < 1e300):
                    return None
                out.append((a, b))
        return tuple(out)

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
        bx, by, bw, bh = self._box
        if not (bx - radius <= px <= bx + bw + radius and by - radius <= py <= by + bh + radius):
            return None, None   # in the margin: lines and markers are clipped at the plot area
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
                ax, ay, ex, ey = xs[:-1], ys[:-1], xs[1:], ys[1:]
                dx, dy = ex - ax, ey - ay
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

    Some care is taken because a web page in any browser tab can reach a
    local server: requests must name this server in their ``Host`` header
    (against DNS rebinding) and input must come from the server's own page
    (``Origin``) as JSON. A browser that stops reading the stream is
    dropped instead of collecting messages without end; its page then
    reconnects and starts again from the whole chart.
    """

    #: Largest input message, in bytes.
    MAX_INPUT = 64 * 1024
    #: Messages waiting for one browser before it is dropped.
    MAX_QUEUED = 1000

    def __init__(self, renderer: WebRenderer, host: str = "127.0.0.1", port: int = 0, title: str = "CoolPlot"):
        self.renderer = renderer
        self.title = title
        self._clients: List[queue.Queue] = []
        self._clients_lock = threading.Lock()
        self._started = False
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            timeout = 30   # seconds; a browser that stops reading is cut off

            def log_message(self, *args):
                pass   # keep the console quiet

            def _refused(self) -> bool:
                host = self.headers.get("Host", "")
                origin = self.headers.get("Origin")
                if server._hosts is not None and host not in server._hosts:
                    self.send_error(403, "Unknown host")
                    return True
                if origin is not None and origin != "http://" + host:
                    self.send_error(403, "Foreign origin")
                    return True
                return False

            def _reply(self, code: int):
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                if self._refused():
                    return
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
                if self._refused():
                    return
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    self.send_error(415, "Input has to be JSON")
                    return
                try:
                    length = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    self.send_error(411)
                    return
                if not 0 < length <= server.MAX_INPUT:
                    self.send_error(413)
                    return
                try:
                    message = server.renderer.check_input(self.rfile.read(length))
                except ValueError:
                    self._reply(400)
                    return
                self._reply(204)
                server.renderer.receive(message)

            def _stream(self):
                self.close_connection = True   # a stream has no length: never reuse the socket
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                client = queue.Queue(maxsize=server.MAX_QUEUED)
                client.dropped = False
                # Under the renderer's lock no patch can be sent between
                # the snapshot and the registration of this browser
                with server.renderer._lock:
                    client.put(server.renderer.snapshot())
                    with server._clients_lock:
                        server._clients.append(client)
                try:
                    while not server._stopping.is_set() and not client.dropped:
                        try:
                            message = client.get(timeout=1.0)
                        except queue.Empty:
                            self.wfile.write(b": keep-alive\n\n")
                            self.wfile.flush()
                            continue
                        self.wfile.write(b"data: " + message.encode("ascii") + b"\n\n")
                        self.wfile.flush()
                except OSError:
                    pass   # the browser went away, or stopped reading (timeout)
                finally:
                    with server._clients_lock:
                        server._clients.remove(client)

        self._stopping = threading.Event()
        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._httpd.daemon_threads = True
        # Host headers that name this server; None when it is bound to a
        # public address, where the name it is reached by is not known
        bound = self._httpd.server_address[1]
        if host in ("127.0.0.1", "localhost"):
            self._hosts = {"127.0.0.1:{0}".format(bound), "localhost:{0}".format(bound)}
        else:
            self._hosts = None
        self._thread = None
        renderer.listen(self._broadcast)

    def _broadcast(self, message: str):
        with self._clients_lock:
            for client in self._clients:
                try:
                    client.put_nowait(message)
                except queue.Full:
                    client.dropped = True   # its page reconnects and gets the whole chart

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return "http://{0}:{1}/".format(host, port)

    def start(self) -> "WebServer":
        self._started = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def serve_forever(self):
        """Serve in the current thread until interrupted."""
        self._started = True
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self._stopping.set()
        if self._started:   # shutdown() waits for serve_forever, which never ran otherwise
            self._httpd.shutdown()
        self._httpd.server_close()
        self.renderer.unlisten(self._broadcast)
