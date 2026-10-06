# -*- coding: utf-8 -*-
"""SVG backend without third party dependencies.

Useful for web pages, reports and tests, and as a small reference for
writing new backends. Every item becomes one SVG element whose ``id`` is
the item id. The element text is cached per item, so a sync only
regenerates the elements of changed items; a change of the axes (limits,
scales) regenerates all of them because the coordinate mapping changed.

A browser front end can use the same ids to patch an existing SVG
document instead of replacing it.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple
from xml.sax.saxutils import escape, quoteattr

import numpy as np

from ..scene import AxesSpec, Item, Line, Markers, Text
from .base import Renderer, SyncReport

_DASHARRAY = {"solid": None, "dashed": "6,3", "dotted": "1.5,2.5", "dashdot": "6,2.5,1.5,2.5"}


class SvgRenderer(Renderer):
    """Render a scene to an SVG string

    Parameters
    ----------
    width, height : int
        Size of the drawing in pixels.
    margins : (left, right, top, bottom)
        Space around the plotting area for ticks and labels, in pixels.
    """

    def __init__(self, width: int = 800, height: int = 600, margins=(80, 20, 30, 60)):
        super().__init__()
        self.width = width
        self.height = height
        self.margins = margins
        self._elements: Dict[str, str] = {}
        self._items: Dict[str, Item] = {}
        self.elements_built = 0  # how many element strings were generated, for tests

    # Coordinate mapping --------------------------------------------------
    @property
    def _box(self) -> Tuple[float, float, float, float]:
        left, right, top, bottom = self.margins
        return left, top, self.width - left - right, self.height - top - bottom

    def _limits(self):
        axes = self._axes or AxesSpec()
        x_lim, y_lim = axes.x_limits, axes.y_limits
        if x_lim is None or y_lim is None:
            # Autoscale over everything drawn
            xs = [i.x for i in self._items.values() if hasattr(i, "x")]
            ys = [i.y for i in self._items.values() if hasattr(i, "y")]
            xs = np.concatenate([np.atleast_1d(v) for v in xs]) if xs else np.array([0.0, 1.0])
            ys = np.concatenate([np.atleast_1d(v) for v in ys]) if ys else np.array([0.0, 1.0])
            x_lim = x_lim or (np.nanmin(xs), np.nanmax(xs))
            y_lim = y_lim or (np.nanmin(ys), np.nanmax(ys))
        return x_lim, y_lim

    def _mapper(self):
        """Return f(x, y) -> (px, py) for the current axes."""
        axes = self._axes or AxesSpec()
        (x0, x1), (y0, y1) = self._limits()
        bx, by, bw, bh = self._box

        def scale(values, lo, hi, log):
            values = np.asarray(values, dtype=float)
            if log:
                with np.errstate(divide="ignore", invalid="ignore"):
                    return (np.log10(values) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
            return (values - lo) / (hi - lo)

        def to_px(x, y):
            px = bx + scale(x, x0, x1, axes.x_log) * bw
            py = by + bh - scale(y, y0, y1, axes.y_log) * bh
            return px, py

        return to_px

    # Backend hooks -----------------------------------------------------
    def _set_axes(self, axes: AxesSpec):
        # The mapping changed, so every cached element is stale.
        self._elements.clear()

    def _add(self, item: Item):
        self._items[item.id] = item
        self._elements.pop(item.id, None)

    def _update(self, old: Item, new: Item):
        self._add(new)

    def _remove(self, item: Item):
        self._items.pop(item.id, None)
        self._elements.pop(item.id, None)

    def _finish(self, report: SyncReport):
        axes = self._axes or AxesSpec()
        if axes.x_limits is None or axes.y_limits is None:
            self._elements.clear()  # autoscaled limits may have moved

    # Output ------------------------------------------------------------
    def to_svg(self) -> str:
        """The complete SVG document for the last synchronised scene."""
        to_px = self._mapper()
        for item_id, item in self._items.items():
            if item_id not in self._elements:
                self._elements[item_id] = self._element(item, to_px)
                self.elements_built += 1
        bx, by, bw, bh = self._box
        out: List[str] = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" '
            'viewBox="0 0 {0} {1}" font-family="sans-serif">'.format(self.width, self.height),
            '<rect width="100%" height="100%" fill="white"/>',
            '<defs><clipPath id="plot-area"><rect x="{0}" y="{1}" width="{2}" height="{3}"/>'
            '</clipPath></defs>'.format(bx, by, bw, bh),
        ]
        out.extend(self._axes_elements(to_px))
        out.append('<g clip-path="url(#plot-area)">')
        order = sorted(self._items.values(), key=lambda i: i.z_order)
        out.extend(self._elements[i.id] for i in order if i.visible)
        out.append('</g>')
        out.append('<rect x="{0}" y="{1}" width="{2}" height="{3}" fill="none" stroke="black"/>'.format(
            bx, by, bw, bh))
        out.append('</svg>')
        return "\n".join(out)

    def save(self, path):
        with open(path, "w", encoding="ascii", errors="xmlcharrefreplace") as f:
            f.write(self.to_svg())

    # Element builders --------------------------------------------------
    def _element(self, item: Item, to_px) -> str:
        if isinstance(item, Line):
            return self._line(item, to_px)
        if isinstance(item, Markers):
            return self._markers(item, to_px)
        if isinstance(item, Text):
            return self._text(item, to_px)
        raise TypeError("SvgRenderer cannot draw {0}.".format(type(item).__name__))

    def _line(self, item: Line, to_px) -> str:
        px, py = to_px(item.x, item.y)
        commands = []
        pen_down = False
        for x, y in zip(px, py):
            if not (np.isfinite(x) and np.isfinite(y)):
                pen_down = False   # NaN splits the line
                continue
            commands.append("{0}{1:.2f},{2:.2f}".format("L" if pen_down else "M", x, y))
            pen_down = True
        s = item.style
        dash = _DASHARRAY.get(s.dash)
        return '<path id={0} d="{1}" fill="none" stroke={2} stroke-width="{3}" stroke-opacity="{4}"{5}/>'.format(
            quoteattr(item.id), " ".join(commands), quoteattr(s.color), s.width * 4.0 / 3.0, s.alpha,
            ' stroke-dasharray="{0}"'.format(dash) if dash else "")

    def _markers(self, item: Markers, to_px) -> str:
        px, py = to_px(item.x, item.y)
        s = item.style
        r = s.size * 4.0 / 3.0 / 2.0
        shapes = []
        for x, y in zip(px, py):
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            if s.shape == "s":
                shapes.append('<rect x="{0:.2f}" y="{1:.2f}" width="{2:.2f}" height="{2:.2f}"/>'.format(
                    x - r, y - r, 2 * r))
            else:
                shapes.append('<circle cx="{0:.2f}" cy="{1:.2f}" r="{2:.2f}"/>'.format(x, y, r))
        return '<g id={0} fill={1} stroke={2} opacity="{3}">{4}</g>'.format(
            quoteattr(item.id), quoteattr(s.face_color), quoteattr(s.edge_color), s.alpha, "".join(shapes))

    def _text(self, item: Text, to_px) -> str:
        px, py = to_px(item.x, item.y)
        px, py = float(px), float(py)
        angle = 0.0
        if item.direction is not None:
            # Map a short step along the direction to pixels to get the screen angle
            dx, dy = item.direction
            qx, qy = to_px(item.x + dx, item.y + dy)
            angle = math.degrees(math.atan2(float(qy) - py, float(qx) - px))
            if angle > 90.0:
                angle -= 180.0
            elif angle < -90.0:
                angle += 180.0
        s = item.style
        anchor = {"left": "start", "center": "middle", "right": "end"}.get(s.h_align, "middle")
        baseline = {"bottom": "auto", "center": "central", "top": "hanging"}.get(s.v_align, "central")
        return ('<text id={0} x="{1:.2f}" y="{2:.2f}" fill={3} font-size="{4}" text-anchor="{5}" '
                'dominant-baseline="{6}" transform="rotate({7:.2f} {1:.2f} {2:.2f})">{8}</text>').format(
            quoteattr(item.id), px, py, quoteattr(s.color), s.size * 4.0 / 3.0, anchor, baseline,
            angle, escape(item.text))

    def _axes_elements(self, to_px) -> List[str]:
        axes = self._axes or AxesSpec()
        (x0, x1), (y0, y1) = self._limits()
        bx, by, bw, bh = self._box
        out = []
        for value in _ticks(x0, x1, axes.x_log):
            px, _ = to_px(value, y0)
            out.append('<line x1="{0:.2f}" y1="{1}" x2="{0:.2f}" y2="{2}" stroke="black"/>'.format(
                float(px), by + bh, by + bh + 5))
            out.append('<text x="{0:.2f}" y="{1}" font-size="11" text-anchor="middle">{2}</text>'.format(
                float(px), by + bh + 18, _fmt(value)))
            if axes.grid:
                out.append('<line x1="{0:.2f}" y1="{1}" x2="{0:.2f}" y2="{2}" stroke="#dddddd"/>'.format(
                    float(px), by, by + bh))
        for value in _ticks(y0, y1, axes.y_log):
            _, py = to_px(x0, value)
            out.append('<line x1="{0}" y1="{1:.2f}" x2="{2}" y2="{1:.2f}" stroke="black"/>'.format(
                bx - 5, float(py), bx))
            out.append('<text x="{0}" y="{1:.2f}" font-size="11" text-anchor="end" '
                       'dominant-baseline="central">{2}</text>'.format(bx - 8, float(py), _fmt(value)))
            if axes.grid:
                out.append('<line x1="{0}" y1="{1:.2f}" x2="{2}" y2="{1:.2f}" stroke="#dddddd"/>'.format(
                    bx, float(py), bx + bw))
        out.append('<text x="{0}" y="{1}" font-size="13" text-anchor="middle">{2}</text>'.format(
            bx + bw / 2, self.height - 15, escape(axes.x_label)))
        out.append('<text x="20" y="{0}" font-size="13" text-anchor="middle" '
                   'transform="rotate(-90 20 {0})">{1}</text>'.format(by + bh / 2, escape(axes.y_label)))
        if axes.title:
            out.append('<text x="{0}" y="20" font-size="14" text-anchor="middle">{1}</text>'.format(
                bx + bw / 2, escape(axes.title)))
        return out


def _ticks(lo: float, hi: float, log: bool) -> List[float]:
    """Round tick positions between lo and hi."""
    lo, hi = min(lo, hi), max(lo, hi)
    if log and lo > 0.0:
        first, last = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
        mantissas = (1.0,) if last - first > 2 else (1.0, 2.0, 5.0)
        ticks = [m * 10.0 ** e for e in range(first, last + 1) for m in mantissas]
        return [t for t in ticks if lo <= t <= hi]
    span = hi - lo
    if not span > 0.0:
        return [lo]
    raw_step = span / 6.0
    magnitude = 10.0 ** math.floor(math.log10(raw_step))
    step = min((m * magnitude for m in (1.0, 2.0, 5.0, 10.0) if m * magnitude >= raw_step))
    start = math.ceil(lo / step) * step
    return [start + i * step for i in range(int((hi - start) / step + 1e-9) + 1)]


def _fmt(value: float) -> str:
    return "{0:.6g}".format(value)
