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
Connect ``listen`` and ``receive`` to your own web framework or
websocket; ``examples/web_app/server.py`` is a small development server
without dependencies that shows how (page, server-sent events, input).
"""
from __future__ import annotations

import html
import json
import math
import threading
from typing import Callable, Dict, List, Optional, Tuple
from xml.etree import ElementTree
from xml.sax.saxutils import quoteattr

import numpy as np

from ..core.events import Click, Drag, DragEnd, DragStart, Hover, ViewChanged
from ..scene import AxesSpec, Line, Markers
from .base import SyncReport
from .svg import PX_PER_PT, SvgRenderer, check_suffix

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


def _nearest(distances, reach: float):
    """The index of the smallest distance if it is within reach, else None."""
    distances = np.asarray(distances, dtype=float)
    if not len(distances):
        return None
    distances[~np.isfinite(distances)] = np.inf
    return int(np.argmin(distances)) if distances.min() <= reach else None


def _segment_distances(xs, ys, px, py):
    """Distance from (px, py) to every segment of a polyline, in px."""
    if len(xs) < 2:
        return np.array([])
    ax, ay, ex, ey = xs[:-1], ys[:-1], xs[1:], ys[1:]
    dx, dy = ex - ax, ey - ay
    length2 = dx * dx + dy * dy
    with np.errstate(invalid="ignore", divide="ignore"):
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / length2, 0.0, 1.0)
    return np.hypot(ax + t * dx - px, ay + t * dy - py)


def _checked_view_message(message: dict, number) -> dict:
    limits = [message.get("x_limits"), message.get("y_limits")]
    if not all(isinstance(v, (list, tuple)) and len(v) == 2 for v in limits):
        raise ValueError("A view message needs x_limits and y_limits, two numbers each.")
    return {"type": "view", "x_limits": tuple(number(v) for v in limits[0]),
            "y_limits": tuple(number(v) for v in limits[1])}


def _checked_button(button) -> int:
    if button not in (1, 2, 3, 4, 5):
        raise ValueError("Unknown mouse button {0!r}.".format(button))
    return int(button)


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
        self._lock = threading.RLock()   # see the lock property
        self._listeners: List[Callable[[str], None]] = []
        self._sent_head = self._sent_tail = None
        self._sent_items: Dict[str, str] = {}
        self._sent_order: List[str] = []
        self._press = None
        self._page = None
        self.messages_sent = 0

    # Sending ----------------------------------------------------------------
    @property
    def lock(self) -> threading.RLock:
        """The lock every sync takes. A server holds it while it takes a
        snapshot for a new browser and registers that browser, so that no
        patch is sent before the snapshot or lost between the two."""
        return self._lock

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
            self._send_patches(items)
        self._sent_head, self._sent_tail = head, tail
        self._sent_items = dict(items)
        self._sent_order = [i for i, _ in items]

    def _send_patches(self, items):
        """Only what changed since the last message: new or changed elements, removals, the order."""
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
        """Write a static page with the chart; the file name has to end in ".html"."""
        check_suffix(path, (".html", ".htm"), type(self).__name__, "HTML")
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
            return _checked_view_message(message, number)
        if kind not in ("move", "press", "release", "wheel"):
            raise ValueError("Unknown input type {0!r}.".format(kind))
        out = {"type": kind, "px": number(message.get("px")), "py": number(message.get("py"))}
        if kind in ("press", "release"):
            out["button"] = _checked_button(message.get("button", 1))
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
                self._on_press(px, py, message["button"])
            elif kind == "release":
                self._on_release(x, y)
            elif kind == "wheel":
                self._zoom(px, py, message["delta"])

    def _on_press(self, px, py, button):
        item_id, index = self._hit(px, py)
        draggable = isinstance(self._items.get(item_id), Markers) and index is not None
        self._press = dict(item_id=item_id, index=index, draggable=draggable, px=px, py=py,
                           limits=tuple(self._limits()), moved=False, button=button)

    def _on_release(self, x, y):
        press, self._press = self._press, None
        if press is None:
            return
        if press["moved"] and press["draggable"]:
            self._emit(DragEnd(press["item_id"], press["index"], x, y))
        elif not press["moved"]:
            self._emit(Click(x, y, press["item_id"], press["index"], press["button"]))

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
            checked = self._valid_axis_limits(limits, log)
            if checked is None:
                return None
            out.append(checked)
        return tuple(out)

    def _valid_axis_limits(self, limits, log: bool):
        """(lo, hi) of one axis in data values, or None when the limits are not usable."""
        if len(limits) == 3:
            a, b, log = limits
        else:
            lo, hi = limits
            if log and not (lo > 0.0 and hi > 0.0):
                return None
            a, b = (math.log10(lo), math.log10(hi)) if log else (lo, hi)
        if not (math.isfinite(a) and math.isfinite(b) and b > a):
            return None
        return self._log_axis_limits(a, b) if log else self._linear_axis_limits(a, b)

    def _log_axis_limits(self, a: float, b: float):
        """Decades a to b as data values, unless the span is too small, too large or would overflow."""
        usable = -300.0 < a and b < 300.0 and self.MIN_SPAN < b - a <= self.MAX_DECADES
        return (10.0 ** a, 10.0 ** b) if usable else None

    def _linear_axis_limits(self, a: float, b: float):
        size = max(abs(a), abs(b))
        usable = b - a > self.MIN_SPAN * size and size < 1e300
        return (a, b) if usable else None

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
                index = _nearest(np.hypot(xs - px, ys - py), reach)
            else:
                index = _nearest(_segment_distances(xs, ys, px, py), radius)
            if index is not None:
                return item_id, index
        return None, None

    # For tests and the conformance kit: the same path as browser input
    def simulate_pointer(self, kind: str, x: float, y: float, button: int = 1):
        to_px, _ = self._mapper()
        px, py = (float(v) for v in to_px(x, y))
        self.receive({"type": kind, "px": px, "py": py, "button": button})

    def simulate_view(self, x_limits, y_limits):
        self.receive({"type": "view", "x_limits": list(x_limits), "y_limits": list(y_limits)})
