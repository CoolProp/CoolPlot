# -*- coding: utf-8 -*-
"""SVG backend without third party dependencies.

Useful for web pages, reports and tests, and the reference to read when
writing a new backend. Every item becomes one SVG element carrying the
item id in ``data-item`` and its role and group as CSS classes
("cp-role-isoline cp-group-iso-T"), so a web page can restyle or patch
items without regenerating the document.

The element text is cached per item, so a sync only regenerates the
elements of changed items. When the coordinate mapping changes (limits,
scales, plot size, an outside legend that changes width) all elements are
regenerated.

Lengths: styles are in points, SVG user units are CSS pixels, 1 pt = 4/3 px.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree
from xml.sax.saxutils import escape, quoteattr

import numpy as np

from ..core.numbers import format_number
from ..scene import AxesSpec, Item, Line, Markers, Text, drawable_limits
from .ticks import ticks as _ticks
from ..style.values import AxesStyle, TextStyle, dash_pattern_pt
from .base import Renderer, SyncReport

PX_PER_PT = 4.0 / 3.0
_CAPS = {"butt": "butt", "round": "round", "square": "square"}


def _px(value_pt: float) -> str:
    return _num(value_pt * PX_PER_PT)


def _num(value: float) -> str:
    """Compact, deterministic number formatting; refuses NaN and infinity."""
    if not math.isfinite(value):
        raise ValueError("Non-finite value in SVG output.")
    text = "{0:.3f}".format(value).rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


# Characters XML 1.0 does not allow anywhere: control characters, lone
# surrogates (invalid Unicode) and the two non-characters U+FFFE and U+FFFF.
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def check_suffix(path, suffixes, renderer: str, what: str):
    """Refuse a file name whose extension promises another format than ``what``."""
    import os
    suffix = os.path.splitext(os.fspath(path))[1].lower()
    if suffix not in suffixes:
        raise ValueError("{0} writes {1} files ({2}), not {3!r}; MatplotlibRenderer writes PDF, PNG and "
                         "EPS.".format(renderer, what, ", ".join(suffixes), suffix or "a name without extension"))


def _ascii(text: str) -> str:
    """Non-ASCII characters as XML character references."""
    return text.encode("ascii", "xmlcharrefreplace").decode("ascii")


def _clean(text: str) -> str:
    """Drop characters that would make the document invalid XML."""
    return _CONTROL.sub("", str(text))


def _xml_text(text: str) -> str:
    """Escape text for XML; characters not allowed in XML are dropped."""
    return escape(_clean(text))


def _attr(text: str) -> str:
    """A quoted, escaped XML attribute value."""
    return quoteattr(_clean(text))


def _css_class(prefix: str, value: str) -> str:
    return prefix + re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")


def _font_family(families) -> str:
    return ", ".join("'{0}'".format(f) if " " in f else f for f in families)


def _text_attrs(style: TextStyle) -> str:
    f = style.font
    attrs = ['font-family={0}'.format(_attr(_font_family(f.family))),
             'font-size="{0}"'.format(_px(f.size_pt)),
             'font-weight="{0}"'.format(f.weight), 'font-style="{0}"'.format(f.style),
             'fill="{0}"'.format(style.color or "none"), 'fill-opacity="{0}"'.format(_num(style.alpha))]
    if style.halo_color is not None and style.halo_width_pt > 0.0:
        attrs += ['stroke="{0}"'.format(style.halo_color),
                  'stroke-width="{0}"'.format(_px(2.0 * style.halo_width_pt)),
                  'stroke-opacity="{0}"'.format(_num(style.alpha)),
                  'stroke-linejoin="round"', 'paint-order="stroke"']
    return " ".join(attrs)


def _stroke_attrs(color, width_pt, dash_pt, alpha, cap, join) -> str:
    attrs = ['fill="none"', 'stroke="{0}"'.format(color or "none"),
             'stroke-width="{0}"'.format(_px(width_pt)), 'stroke-opacity="{0}"'.format(_num(alpha)),
             'stroke-linecap="{0}"'.format(_CAPS[cap]), 'stroke-linejoin="{0}"'.format(join)]
    if dash_pt:
        attrs.append('stroke-dasharray="{0}"'.format(",".join(_px(v) for v in dash_pt)))
    return " ".join(attrs)


def _marker_shape(shape: str, x: float, y: float, r: float) -> str:
    """One marker centred on (x, y) in pixels; r is half the box width."""
    X, Y = _num(x), _num(y)
    if shape == "o":
        return '<circle cx="{0}" cy="{1}" r="{2}"/>'.format(X, Y, _num(r))
    if shape == "s":
        return '<rect x="{0}" y="{1}" width="{2}" height="{2}"/>'.format(_num(x - r), _num(y - r), _num(2 * r))
    points = {
        "^": [(0, -r), (r, r), (-r, r)],
        "v": [(0, r), (r, -r), (-r, -r)],
        "D": [(0, -r), (r, 0), (0, r), (-r, 0)],
    }
    if shape in points:
        return '<path d="M{0}Z"/>'.format("L".join(
            "{0},{1}".format(_num(x + dx), _num(y + dy)) for dx, dy in points[shape]))
    if shape == "x":
        return '<path d="M{0},{1}L{2},{3}M{0},{3}L{2},{1}"/>'.format(
            _num(x - r), _num(y - r), _num(x + r), _num(y + r))
    if shape == "+":
        return '<path d="M{0},{1}L{2},{1}M{3},{4}L{3},{5}"/>'.format(
            _num(x - r), Y, _num(x + r), X, _num(y - r), _num(y + r))
    raise ValueError("Unknown marker shape {0!r}.".format(shape))


class SvgRenderer(Renderer):
    """Render a scene to an SVG string

    Parameters
    ----------
    width, height : int
        Size of the drawing in pixels.
    margins : (left, right, top, bottom)
        Space around the plotting area for ticks and labels, in pixels.
        An outside legend adds to the right margin.
    id_prefix : str
        Prefix for the few document-level ids (the clip path). Give every
        SVG embedded in the same HTML page its own prefix.
    """

    capabilities = frozenset({"file_output", "css_classes"})
    default_suffix = ".svg"
    text_output = True
    owns_canvas = True

    def __init__(self, width: int = 800, height: int = 600, margins=(80, 20, 40, 60),
                 id_prefix: str = "coolplot"):
        super().__init__()
        self.width = width
        self.height = height
        self.margins = margins
        prefix = re.sub(r"[^A-Za-z0-9_-]+", "-", id_prefix).strip("-")
        # An XML id has to start with a letter or underscore
        self.id_prefix = prefix if re.match(r"[A-Za-z_]", prefix or "") else "cp-" + prefix
        self._items: Dict[str, Item] = {}
        self._elements: Dict[str, str] = {}
        self._mapping_key = None
        self._legend_entries: List = []
        self._legend_style = None
        self._parsed = None
        self._extra_margins = (0.0, 0.0, 0.0, 0.0)   # room for unclipped text, see _finish
        self.elements_built = 0  # element strings generated, for tests

    # Backend hooks -----------------------------------------------------
    def _set_axes(self, axes: AxesSpec):
        self._parsed = None

    def _add(self, item: Item):
        self._items[item.id] = item
        self._elements.pop(item.id, None)

    def _update(self, old: Item, new: Item):
        self._add(new)

    def _remove(self, item: Item):
        self._items.pop(item.id, None)
        self._elements.pop(item.id, None)

    def _reorder(self, order):
        pass  # to_svg writes elements in self._order, which the base class keeps

    def _set_legend(self, entries, style):
        self._legend_entries = list(entries)
        self._legend_style = style

    def _finish(self, report: SyncReport):
        self._parsed = None
        if report.changed:
            self._extra_margins = self._unclipped_margins()

    # Geometry ----------------------------------------------------------
    @property
    def _style(self) -> AxesStyle:
        return (self._axes or AxesSpec()).style

    def _legend_chars(self) -> int:
        """Longest legend text that fits: the legend may take at most 40 % of the width."""
        size_px = self._legend_style.text.font.size_pt * PX_PER_PT
        return max(4, int((0.4 * self.width - 44.0) / (0.6 * size_px)))

    def _legend_text(self, text: str) -> str:
        limit = self._legend_chars()
        return text if len(text) <= limit else text[:limit - 3] + "..."

    def _legend_size(self) -> Tuple[float, float]:
        """Estimated (width, height) in px; text width is guessed from its length."""
        st = self._legend_style
        if st is None or not st.visible or not self._legend_entries:
            return 0.0, 0.0
        size_px = st.text.font.size_pt * PX_PER_PT
        longest = max(len(self._legend_text(text)) for text, _ in self._legend_entries)
        return 44.0 + 0.6 * size_px * longest, 8.0 + 1.6 * size_px * len(self._legend_entries)

    def _unclipped_margins(self) -> Tuple[float, float, float, float]:
        """Extra (left, right, top, bottom) margins in px for text outside the frame.

        Margin labels sit on the frame and reach outwards; without room they
        would run off the drawing. The text size is estimated from its length,
        as for the legend.
        """
        need = [0.0, 0.0, 0.0, 0.0]
        (x0, x1), (y0, y1) = self._limits()
        axes = self._axes or AxesSpec()
        for item in self._items.values():
            if not (isinstance(item, Text) and item.visible and not item.clip):
                continue
            fx, fy = _fraction(item.x, x0, x1, axes.x_log), _fraction(item.y, y0, y1, axes.y_log)
            if math.isfinite(fx) and math.isfinite(fy):
                need = [max(n, r) for n, r in zip(need, _margin_reach(item, fx, fy))]
        left, right, top, bottom = self.margins
        # With a title the configured top margin holds the title, so labels
        # above the frame need their whole height on top of it
        top_extra = need[2] if axes.title else max(0.0, need[2] - top)
        return (max(0.0, need[0] - left), max(0.0, need[1] - right), top_extra,
                max(0.0, need[3] - bottom))

    @property
    def _box(self) -> Tuple[float, float, float, float]:
        extra = self._extra_margins
        left, right, top, bottom = (m + e for m, e in zip(self.margins, extra))
        st = self._legend_style
        if st is not None and st.location == "outside right":
            right += self._legend_size()[0] + 12.0 if self._legend_size()[0] else 0.0
        # Never let margins and an outside legend eat the whole drawing
        width = max(self.width - left - right, 0.25 * self.width)
        return left, top, width, max(self.height - top - bottom, 0.25 * self.height)

    def _limits(self):
        axes = self._axes or AxesSpec()
        result = []
        for limits, key, log in ((axes.x_limits, "x", axes.x_log), (axes.y_limits, "y", axes.y_log)):
            if limits is None:
                limits = self._data_limits(key, log)
            result.append(drawable_limits(limits, log))
        return result

    def _data_limits(self, key: str, log: bool):
        """The span of the visible lines and markers on one axis (autoscale), or a default."""
        values = []
        for item in self._items.values():
            if item.visible and isinstance(item, (Line, Markers)):
                v = np.asarray(getattr(item, key), dtype=float)
                values.append(v[np.isfinite(v) & ((v > 0.0) if log else True)])
        values = np.concatenate(values) if values else np.array([])
        if values.size == 0:
            return (1.0, 10.0) if log else (0.0, 1.0)
        return float(values.min()), float(values.max())

    def _mapper(self):
        """f(x, y) -> (px, py) arrays; NaN where a value cannot be shown."""
        axes = self._axes or AxesSpec()
        (x0, x1), (y0, y1) = self._limits()
        bx, by, bw, bh = self._box

        def frac(values, lo, hi, log):
            values = np.asarray(values, dtype=float)
            if log:
                with np.errstate(divide="ignore", invalid="ignore"):
                    out = (np.log10(values) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
                return np.where(values > 0.0, out, np.nan)
            return (values - lo) / (hi - lo)

        def to_px(x, y):
            return (bx + frac(x, x0, x1, axes.x_log) * bw,
                    by + bh - frac(y, y0, y1, axes.y_log) * bh)

        return to_px, (bx, by, bw, bh, x0, x1, y0, y1, axes.x_log, axes.y_log)

    # Output ------------------------------------------------------------
    def to_svg(self) -> str:
        """The complete SVG document for the last synchronised scene, ASCII only."""
        head, items, tail = self._document_parts()
        return "\n".join([head, '<g class="cp-items">'] + [e for _, e in items] + ['</g>', tail])

    def _build_elements(self):
        """Make the SVG element of every item that has none yet (all of them after the axes changed)."""
        to_px, mapping_key = self._mapper()
        if mapping_key != self._mapping_key:
            self._elements.clear()
            self._mapping_key = mapping_key
        for item_id, item in self._items.items():
            if item_id not in self._elements:
                self._elements[item_id] = _ascii(self._element(item, to_px))
                self.elements_built += 1
        return to_px

    def _document_parts(self):
        """(head, [(item id, element)], tail) of the document, ASCII only.

        The head holds everything below the items (background, grid), the
        tail everything above them (frame, ticks, labels, legend). Items are
        listed in drawing order; hidden items are left out.
        """
        to_px = self._build_elements()
        axes = self._axes or AxesSpec()
        st = axes.style
        bx, by, bw, bh = self._box
        (x0, x1), (y0, y1) = self._limits()
        clip = self.id_prefix + "-plot-area"
        head: List[str] = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" viewBox="0 0 {0} {1}" '
            'data-x-log="{2}" data-y-log="{3}" data-x-limits="{4} {5}" data-y-limits="{6} {7}">'.format(
                self.width, self.height, int(axes.x_log), int(axes.y_log),
                repr(x0), repr(x1), repr(y0), repr(y1)),
            '<rect class="cp-figure" width="100%" height="100%" fill="{0}"/>'.format(
                st.figure_background or "none"),
            '<defs><clipPath id="{0}"><rect x="{1}" y="{2}" width="{3}" height="{4}"/></clipPath></defs>'.format(
                clip, _num(bx), _num(by), _num(bw), _num(bh)),
            '<rect class="cp-background" x="{0}" y="{1}" width="{2}" height="{3}" fill="{4}"/>'.format(
                _num(bx), _num(by), _num(bw), _num(bh), st.background or "none"),
        ]
        head.extend(self._grid(to_px, axes))
        # Every item clips itself (see _open), so that unclipped text keeps
        # its place in the drawing order.
        items = [(i, self._elements[i]) for i in self._order if i in self._elements and self._elements[i]]
        tail: List[str] = [
            '<rect class="cp-frame" x="{0}" y="{1}" width="{2}" height="{3}" fill="none" '
            'stroke="{4}" stroke-width="{5}"/>'.format(_num(bx), _num(by), _num(bw), _num(bh),
                                                     st.frame_color or "none", _px(st.frame_width_pt))]
        tail.extend(self._ticks_and_labels(to_px, axes))
        tail.extend(self._legend_elements())
        tail.append('</svg>')
        return _ascii("\n".join(head)), items, _ascii("\n".join(tail))

    def plot_size_pt(self):
        """(width, height) of the plot area in points."""
        bx, by, bw, bh = self._box
        return bw / PX_PER_PT, bh / PX_PER_PT

    def save(self, path):
        """Write the SVG document; the file name has to end in ".svg"."""
        check_suffix(path, (".svg",), type(self).__name__, "SVG")
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write(self.to_svg())

    # Item elements -----------------------------------------------------
    def _open(self, item: Item, extra: str = "") -> str:
        classes = " ".join(c for c in ("cp-item", _css_class("cp-role-", item.role) if item.role else "",
                                       _css_class("cp-group-", item.group) if item.group else "") if c)
        if getattr(item, "clip", True):
            extra = ' clip-path="url(#{0}-plot-area)"'.format(self.id_prefix) + extra
        return '<g data-item={0} class="{1}"{2}>'.format(_attr(item.id), classes, extra)

    def _element(self, item: Item, to_px) -> str:
        """SVG text for one item; empty for hidden items, which are not drawn."""
        if not item.visible:
            return ""
        if isinstance(item, Line):
            return self._line(item, to_px)
        if isinstance(item, Markers):
            return self._markers(item, to_px)
        if isinstance(item, Text):
            return self._text(item, to_px)
        raise TypeError("SvgRenderer cannot draw {0}.".format(type(item).__name__))

    @staticmethod
    def _path_data(px, py) -> str:
        commands = []
        pen_down = False
        for x, y in zip(px, py):
            if not (math.isfinite(x) and math.isfinite(y)):
                pen_down = False   # NaN, or a non-positive value on a log axis, splits the line
                continue
            commands.append("{0}{1},{2}".format("L" if pen_down else "M", _num(x), _num(y)))
            pen_down = True
        return "".join(commands)

    def _line(self, item: Line, to_px) -> str:
        s = item.style
        d = self._path_data(*to_px(item.x, item.y))
        dash = dash_pattern_pt(s.dash, s.width_pt)
        parts = [self._open(item)]
        if s.casing_color is not None and s.casing_width_pt > 0.0:
            parts.append('<path class="cp-casing" d="{0}" {1}/>'.format(d, _stroke_attrs(
                s.casing_color, s.width_pt + 2.0 * s.casing_width_pt, dash, s.alpha, s.cap, s.join)))
        parts.append('<path class="cp-stroke" d="{0}" {1}/>'.format(d, _stroke_attrs(
            s.color, s.width_pt, dash, s.alpha, s.cap, s.join)))
        parts.append('</g>')
        return "".join(parts)

    def _markers(self, item: Markers, to_px) -> str:
        s = item.style
        px, py = to_px(item.x, item.y)
        r = s.size_pt * PX_PER_PT / 2.0
        face = "none" if s.shape in ("x", "+") or s.face_color is None else s.face_color
        shapes = [_marker_shape(s.shape, x, y, r) for x, y in zip(px, py)
                  if math.isfinite(x) and math.isfinite(y)]
        extra = (' fill="{0}" stroke="{1}" stroke-width="{2}" opacity="{3}" data-shape={4} '
                 'data-size-pt="{5}"').format(face, s.edge_color or "none", _px(s.edge_width_pt),
                                              _num(s.alpha), _attr(s.shape), _num(s.size_pt))
        return self._open(item, extra) + "".join(shapes) + "</g>"

    def _text(self, item: Text, to_px) -> str:
        if not (math.isfinite(item.x) and math.isfinite(item.y)):
            return ""
        px, py = (float(v) for v in to_px(item.x, item.y))
        if not (math.isfinite(px) and math.isfinite(py)):
            return ""
        # The angle is measured at the anchor point; the offset moves the
        # text afterwards. Screen y points down, the offset y up.
        offset_x, offset_y = item.offset_pt[0] * PX_PER_PT, -item.offset_pt[1] * PX_PER_PT
        angle = _svg_angle(item, to_px, px, py)
        s = item.style
        anchor = {"left": "start", "center": "middle", "right": "end"}[s.h_align]
        baseline = {"bottom": "text-after-edge", "center": "central", "top": "text-before-edge"}[s.v_align]
        return (self._open(item) + '<text x="{0}" y="{1}" text-anchor="{2}" dominant-baseline="{3}" '
                'transform="rotate({4} {0} {1})" {5}>{6}</text></g>').format(
            _num(px + offset_x), _num(py + offset_y), anchor, baseline, _num(angle), _text_attrs(s),
            _xml_text(item.text))

    # Axes decoration ---------------------------------------------------
    def _grid(self, to_px, axes: AxesSpec) -> List[str]:
        st = axes.style
        (x0, x1), (y0, y1) = self._limits()
        bx, by, bw, bh = self._box
        out = []
        for level, grid in (("minor", st.grid_minor), ("major", st.grid_major)):
            if grid is None:
                continue
            attrs = _stroke_attrs(grid.color, grid.width_pt, dash_pattern_pt(grid.dash, grid.width_pt),
                                  grid.alpha, grid.cap, grid.join)
            for value in _ticks(x0, x1, axes.x_log, minor=level == "minor"):
                px = float(to_px(value, y0)[0])
                out.append('<line class="cp-grid-{0}" x1="{1}" y1="{2}" x2="{1}" y2="{3}" {4}/>'.format(
                    level, _num(px), _num(by), _num(by + bh), attrs))
            for value in _ticks(y0, y1, axes.y_log, minor=level == "minor"):
                py = float(to_px(x0, value)[1])
                out.append('<line class="cp-grid-{0}" x1="{1}" y1="{2}" x2="{3}" y2="{2}" {4}/>'.format(
                    level, _num(bx), _num(py), _num(bx + bw), attrs))
        return out

    def _ticks_and_labels(self, to_px, axes: AxesSpec) -> List[str]:
        st = axes.style
        (x0, x1), (y0, y1) = self._limits()
        bx, by, bw, bh = self._box
        length = st.tick_length_pt * PX_PER_PT * (1.0 if st.tick_direction == "out" else -1.0)
        tick = 'stroke="{0}" stroke-width="{1}"'.format(st.tick_color or "none", _px(st.tick_width_pt))
        label_attrs = _text_attrs(st.tick_label)
        gap = abs(length) if st.tick_direction == "out" else 0.0
        out = []
        for value in _ticks(x0, x1, axes.x_log):
            px = float(to_px(value, y0)[0])
            out.append('<line class="cp-tick cp-tick-x" x1="{0}" y1="{1}" x2="{0}" y2="{2}" {3}/>'.format(
                _num(px), _num(by + bh), _num(by + bh + length), tick))
            out.append('<text class="cp-tick-label cp-tick-label-x" x="{0}" y="{1}" text-anchor="middle" '
                       'dominant-baseline="text-before-edge" data-value="{4}" {2}>{3}</text>'.format(
                           _num(px), _num(by + bh + gap + 3.0), label_attrs,
                           format_number(value, axes.tick_digits), repr(float(value))))
        for value in _ticks(y0, y1, axes.y_log):
            py = float(to_px(x0, value)[1])
            out.append('<line class="cp-tick cp-tick-y" x1="{0}" y1="{1}" x2="{2}" y2="{1}" {3}/>'.format(
                _num(bx), _num(py), _num(bx - length), tick))
            out.append('<text class="cp-tick-label cp-tick-label-y" x="{0}" y="{1}" text-anchor="end" '
                       'dominant-baseline="central" data-value="{4}" {2}>{3}</text>'.format(
                           _num(bx - gap - 3.0), _num(py), label_attrs,
                           format_number(value, axes.tick_digits), repr(float(value))))
        out.append('<text class="cp-x-label" x="{0}" y="{1}" text-anchor="middle" '
                   'dominant-baseline="text-after-edge" {2}>{3}</text>'.format(
                       _num(bx + bw / 2.0), _num(self.height - 8.0), _text_attrs(st.axis_label),
                       _xml_text(axes.x_label)))
        out.append('<text class="cp-y-label" x="18" y="{0}" text-anchor="middle" dominant-baseline="central" '
                   'transform="rotate(-90 18 {0})" {1}>{2}</text>'.format(
                       _num(by + bh / 2.0), _text_attrs(st.axis_label), _xml_text(axes.y_label)))
        if axes.title:
            out.append('<text class="cp-title" x="{0}" y="{1}" text-anchor="middle" '
                       'dominant-baseline="text-after-edge" {2}>{3}</text>'.format(
                           _num(bx + bw / 2.0), _num(by - 8.0 - self._extra_margins[2]), _text_attrs(st.title),
                           _xml_text(axes.title)))
        return out

    def _legend_elements(self) -> List[str]:
        st = self._legend_style
        width, height = self._legend_size()
        if not width:
            return []
        bx, by, bw, bh = self._box
        pad = 8.0
        x = {"upper left": bx + pad, "lower left": bx + pad, "upper right": bx + bw - pad - width,
             "lower right": bx + bw - pad - width, "outside right": bx + bw + 12.0}[st.location]
        y = by + pad if st.location in ("upper left", "upper right", "outside right") else by + bh - pad - height
        size_px = st.text.font.size_pt * PX_PER_PT
        out = ['<g class="cp-legend">',
               '<rect class="cp-legend-box" x="{0}" y="{1}" width="{2}" height="{3}" fill="{4}" '
               'stroke="{5}"/>'.format(_num(x), _num(y), _num(width), _num(height), st.background or "none",
                                      st.frame_color or "none")]
        for i, (text, items) in enumerate(self._legend_entries):
            cy = y + 4.0 + size_px * (1.6 * i + 0.8)
            out.append('<g class="cp-legend-entry">')
            for item in items:
                out.extend(self._legend_sample(item, x, cy))
            out.append('<text class="cp-legend-text" x="{0}" y="{1}" dominant-baseline="central" '
                       '{2}>{3}</text></g>'.format(_num(x + 34.0), _num(cy), _text_attrs(st.text),
                                                  _xml_text(self._legend_text(text))))
        out.append('</g>')
        return out

    def _legend_sample(self, item: Item, x: float, cy: float) -> List[str]:
        """A short line or one marker at the start of a legend row."""
        out = []
        s = item.style
        if isinstance(item, Line):
            if s.casing_color is not None and s.casing_width_pt > 0.0:
                out.append('<line class="cp-casing" x1="{0}" y1="{1}" x2="{2}" y2="{1}" {3}/>'.format(
                    _num(x + 6.0), _num(cy), _num(x + 28.0), _stroke_attrs(
                        s.casing_color, s.width_pt + 2.0 * s.casing_width_pt,
                        dash_pattern_pt(s.dash, s.width_pt), s.alpha, s.cap, s.join)))
            out.append('<line x1="{0}" y1="{1}" x2="{2}" y2="{1}" {3}/>'.format(
                _num(x + 6.0), _num(cy), _num(x + 28.0), _stroke_attrs(
                    s.color, s.width_pt, dash_pattern_pt(s.dash, s.width_pt), s.alpha, s.cap, s.join)))
        elif isinstance(item, Markers):
            face = "none" if s.shape in ("x", "+") or s.face_color is None else s.face_color
            out.append('<g class="cp-legend-marker" fill="{0}" stroke="{1}" stroke-width="{2}" '
                       'opacity="{3}">{4}</g>'.format(
                           face, s.edge_color or "none", _px(s.edge_width_pt), _num(s.alpha),
                           _marker_shape(s.shape, x + 17.0, cy, s.size_pt * PX_PER_PT / 2.0)))
        return out

    # Read back ---------------------------------------------------------
    # Everything below is parsed from the SVG text that to_svg() produces,
    # so it reports what a browser would draw.
    def _document(self):
        if self._parsed is None:
            self._parsed = ElementTree.fromstring(self.to_svg())
        return self._parsed

    def describe_item(self, item_id: str) -> dict:
        """Read back the item as drawn, from its SVG elements."""
        item = self._items[item_id]   # KeyError for unknown ids, as required
        root = self._document()
        groups = [g for g in root.iter() if g.get("data-item") is not None]
        element = next((g for g in groups if g.get("data-item") == item_id), None)
        kind = {Line: "line", Markers: "markers", Text: "text"}[type(item)]
        if element is None:
            return {"visible": False, "kind": kind}
        out = {"visible": True, "kind": kind, "draw_rank": groups.index(element),
               "clip": element.get("clip-path") is not None}
        bx, by, bw, bh = self._box

        def frac(px, py):
            """A drawn point as a fraction of the plot area, y up."""
            return ((px - bx) / bw, 1.0 - (py - by) / bh)

        if kind == "line":
            out.update(_describe_line_element(element, frac))
        elif kind == "markers":
            out.update(_describe_marker_element(element, frac))
        else:
            text = next(iter(element))
            out.update(_describe_text_element(text))
            # Offset: where the text was drawn, compared with its anchor
            to_px, _ = self._mapper()
            px, py = (float(v) for v in to_px(item.x, item.y))
            drawn_x, drawn_y = float(text.get("x")), float(text.get("y"))
            out["offset_pt"] = ((drawn_x - px) / PX_PER_PT, (py - drawn_y) / PX_PER_PT)
            out["drawn_points"] = [frac(drawn_x, drawn_y)]
        return out

    def describe_axes(self) -> dict:
        """Read back the axes as drawn, from the SVG elements."""
        root = self._document()
        by_class = {}
        order = {}
        for index, el in enumerate(root.iter()):
            order[id(el)] = index
            for c in (el.get("class") or "").split():
                by_class.setdefault(c, []).append(el)

        def first(cls):
            found = by_class.get(cls)
            return found[0] if found else None

        frame, background = first("cp-frame"), first("cp-background")
        bw, bh = float(background.get("width")), float(background.get("height"))
        item_positions = [order[id(g)] for g in root.iter() if g.get("data-item") is not None]
        out = dict(
            x_log=root.get("data-x-log") == "1", y_log=root.get("data-y-log") == "1",
            x_limits=tuple(float(v) for v in root.get("data-x-limits").split()),
            y_limits=tuple(float(v) for v in root.get("data-y-limits").split()),
            background=_color(background.get("fill")), figure_background=_color(first("cp-figure").get("fill")),
            plot_size_pt=(bw / PX_PER_PT, bh / PX_PER_PT),
            legend=self._legend_description(by_class),
            x_tick_labels=_tick_label_rows(by_class, "x"), y_tick_labels=_tick_label_rows(by_class, "y"),
        )
        out.update(_describe_frame(frame, order, item_positions))
        out.update(_describe_texts(first, by_class))
        out.update(_describe_ticks(first("cp-tick-x"), first("cp-tick-y")))
        out.update(self._describe_legend_box(first, background, order, item_positions))
        out.update(_describe_grid(by_class, order, item_positions))
        return out

    def _describe_legend_box(self, first, background, order, item_positions) -> dict:
        legend_box = first("cp-legend-box")
        if legend_box is None:
            return {}
        out = dict(legend_background=_color(legend_box.get("fill")),
                   items_below_legend=not item_positions or max(item_positions) < order[id(legend_box)],
                   legend_location=self._legend_location(legend_box, background))
        legend_text = first("cp-legend-text")
        if legend_text is not None:
            out.update(_without_weight_and_style(_text_description("legend", legend_text)))
        return out

    @staticmethod
    def _legend_description(by_class):
        rows = []
        for entry in by_class.get("cp-legend-entry", []):
            text = next(el for el in entry.iter() if "cp-legend-text" in (el.get("class") or ""))
            rows.append((text.text or "", tuple(sorted(_sample_colors(entry) - {None}))))
        return rows

    @staticmethod
    def _legend_location(box, plot):
        bx, by = float(box.get("x")), float(box.get("y"))
        bw, bh = float(box.get("width")), float(box.get("height"))
        px, py = float(plot.get("x")), float(plot.get("y"))
        pw, ph = float(plot.get("width")), float(plot.get("height"))
        if bx >= px + pw - 0.5:
            return "outside right"
        vertical = "upper" if by + bh / 2.0 < py + ph / 2.0 else "lower"   # screen y points down
        horizontal = "right" if bx + bw / 2.0 > px + pw / 2.0 else "left"
        return vertical + " " + horizontal


_NS = "{http://www.w3.org/2000/svg}"


def _fraction(v: float, lo: float, hi: float, log: bool) -> float:
    """Where a value lies on an axis, 0 at lo and 1 at hi; NaN where it cannot be shown."""
    if not math.isfinite(v):
        return math.nan
    if log:
        return (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) if v > 0 else math.nan
    return (v - lo) / (hi - lo)


def _text_extent_px(item: Text):
    """(left, right, down, up) reach of a text from its anchor in px, from its length and alignment."""
    size_px = item.style.font.size_pt * PX_PER_PT
    length, height = 0.6 * size_px * len(item.text), 1.25 * size_px
    vertical = item.direction is not None and abs(item.direction[1]) > abs(item.direction[0])
    h_align, v_align = item.style.h_align, item.style.v_align
    along = {"left": (0.0, length), "center": (length / 2, length / 2), "right": (length, 0.0)}[h_align]
    across = {"bottom": (0.0, height), "center": (height / 2, height / 2), "top": (height, 0.0)}[v_align]
    if vertical:   # reads upwards: its start is at the bottom
        return across[1], across[0], along[0], along[1]
    return along[0], along[1], across[0], across[1]


def _margin_reach(item: Text, fx: float, fy: float):
    """How far (left, right, top, bottom) a text on the frame reaches beyond it, in px, with
    a little room; zero on the sides the text does not touch."""
    left_px, right_px, down_px, up_px = _text_extent_px(item)
    dx, dy = item.offset_pt[0] * PX_PER_PT, item.offset_pt[1] * PX_PER_PT
    reach = (left_px - dx + 4.0, right_px + dx + 4.0, up_px + dy + 4.0, down_px - dy + 4.0)
    touches = (fx <= 1e-9, fx >= 1.0 - 1e-9, fy >= 1.0 - 1e-9, fy <= 1e-9)
    return tuple(r if t else 0.0 for r, t in zip(reach, touches))


def _svg_angle(item: Text, to_px, px: float, py: float) -> float:
    """The SVG rotation of a text that follows its direction, kept upright."""
    if item.direction is None:
        return 0.0
    dx, dy = item.direction
    step = 1e-3
    qx, qy = (float(v) for v in to_px(item.x + dx * step, item.y + dy * step))
    if not (math.isfinite(qx) and math.isfinite(qy)) or (qx, qy) == (px, py):
        return 0.0
    # Screen y points down, so a rising line has a negative SVG angle.
    angle = math.degrees(math.atan2(qy - py, qx - px))
    # Upright: the screen angle (counter-clockwise, the negative of the SVG
    # angle) stays in (-90, 90], so straight down becomes straight up and
    # the text reads bottom to top.
    if angle >= 90.0:
        return angle - 180.0
    if angle < -90.0:
        return angle + 180.0
    return angle


def _describe_line_element(element, frac) -> dict:
    paths = {p.get("class"): p for p in element.iter(_NS + "path")}
    main, casing = paths["cp-stroke"], paths.get("cp-casing")
    vertices = re.findall(r"[ML](-?[0-9.e]+),(-?[0-9.e]+)", main.get("d") or "")
    out = dict(_stroke_description(main), n_points=len(vertices),
               drawn_points=[frac(float(x), float(y)) for x, y in vertices])
    if casing is not None:
        cased = _stroke_description(casing)
        out.update(casing_color=cased["color"], casing_width_pt=(cased["width_pt"] - out["width_pt"]) / 2.0,
                   casing_dash_pt=cased["dash_pt"], casing_alpha=cased["alpha"])
    else:
        out.update(casing_color=None, casing_width_pt=0.0)
    return out


def _describe_marker_element(element, frac) -> dict:
    shapes = list(element)
    return dict(shape=_shape_from_geometry(shapes[0]) if shapes else None,
                size_pt=_shape_width_px(shapes[0]) / PX_PER_PT if shapes else 0.0,
                drawn_points=[frac(*_shape_centre(el)) for el in shapes],
                connected=any(el.tag in (_NS + "polyline", _NS + "line") for el in shapes)
                or any(_shape_width_px(el) > 3.0 * _shape_width_px(shapes[0]) for el in shapes),
                face_color=_color(element.get("fill")), edge_color=_color(element.get("stroke")),
                edge_width_pt=float(element.get("stroke-width")) / PX_PER_PT,
                alpha=float(element.get("opacity")), n_points=len(shapes))


def _describe_text_element(text) -> dict:
    angle = float(re.match(r"rotate\(([-0-9.e]+)", text.get("transform")).group(1))
    halo = text.get("stroke")
    out = _text_description("", text)
    out.update(text=text.text or "",
               h_align={"start": "left", "middle": "center", "end": "right"}[text.get("text-anchor")],
               v_align={"text-after-edge": "bottom", "central": "center",
                        "text-before-edge": "top"}[text.get("dominant-baseline")],
               halo_color=_color(halo) if halo else None,
               halo_width_pt=float(text.get("stroke-width")) / PX_PER_PT / 2.0 if halo else 0.0,
               screen_angle_deg=-angle,   # SVG angles turn clockwise
               alpha=float(text.get("fill-opacity")))
    return out


def _tick_label_rows(by_class, axis: str):
    return [(float(t.get("data-value")), t.text or "") for t in by_class.get("cp-tick-label-" + axis, [])]


def _describe_frame(frame, order, item_positions) -> dict:
    # One rectangle draws all four sides of the frame with one style
    return dict(frame_color=_color(frame.get("stroke")), frame_width_pt=float(frame.get("stroke-width")) / PX_PER_PT,
                frame_sides=4 if frame.get("stroke") not in (None, "none") else 0,
                items_below_frame=not item_positions or max(item_positions) < order[id(frame)])


def _describe_texts(first, by_class) -> dict:
    """The axis titles, the title and the tick label font."""
    out = dict(x_label=(first("cp-x-label").text or ""), y_label=(first("cp-y-label").text or ""),
               title=(first("cp-title").text or "") if first("cp-title") is not None else "")
    out.update(_text_description("x_label", first("cp-x-label")))
    out.update(_text_description("y_label", first("cp-y-label")))
    if first("cp-title") is not None:
        out.update(_text_description("title", first("cp-title")))
    labels = by_class.get("cp-tick-label")
    if labels:
        out.update(_without_weight_and_style(_text_description("tick_label", labels[0])))
    return out


def _describe_ticks(x_tick, y_tick) -> dict:
    out = {}
    if x_tick is not None:
        length = float(x_tick.get("y2")) - float(x_tick.get("y1"))
        out.update(tick_direction="out" if length > 0 else "in", tick_color=_color(x_tick.get("stroke")),
                   tick_length_pt=abs(length) / PX_PER_PT,
                   tick_width_pt=float(x_tick.get("stroke-width")) / PX_PER_PT)
    if y_tick is not None:
        length = float(y_tick.get("x1")) - float(y_tick.get("x2"))   # outward points left
        out.update(y_tick_direction="out" if length > 0 else "in", y_tick_color=_color(y_tick.get("stroke")),
                   y_tick_length_pt=abs(length) / PX_PER_PT,
                   y_tick_width_pt=float(y_tick.get("stroke-width")) / PX_PER_PT)
    return out


def _describe_grid(by_class, order, item_positions) -> dict:
    major, minor = by_class.get("cp-grid-major"), by_class.get("cp-grid-minor")
    out = dict(grid_color=_color(major[0].get("stroke")) if major else None,
               grid_minor_color=_color(minor[0].get("stroke")) if minor else None)
    if major:
        grid = _stroke_description(major[0])
        vertical = [g for g in major if g.get("x1") == g.get("x2")]
        out.update(x_grid_lines=len(vertical), y_grid_lines=len(major) - len(vertical),
                   grid_width_pt=grid["width_pt"], grid_dash_pt=grid["dash_pt"], grid_lines=len(major),
                   grid_below_items=not item_positions
                   or max(order[id(g)] for g in major + (minor or [])) < min(item_positions))
    return out


def _without_weight_and_style(described: dict) -> dict:
    return {k: v for k, v in described.items() if not k.endswith(("weight", "style"))}


def _sample_colors(entry) -> set:
    """The colours of the line and marker samples of one legend entry."""
    colors = set()
    for el in entry.iter():
        cls = el.get("class") or ""
        if el.tag == _NS + "line" and "cp-casing" not in cls:
            colors.add(_color(el.get("stroke")))
        elif "cp-legend-marker" in cls:
            colors.add(_color(el.get("stroke")) or _color(el.get("fill")))
    return colors


def _stroke_description(el) -> dict:
    width_pt = float(el.get("stroke-width")) / PX_PER_PT
    dash = el.get("stroke-dasharray")
    return dict(color=_color(el.get("stroke")), alpha=float(el.get("stroke-opacity", 1.0)), width_pt=width_pt,
                dash_pt=tuple(float(v) / PX_PER_PT for v in dash.split(",")) if dash else (),
                cap=el.get("stroke-linecap"), join=el.get("stroke-linejoin"))


def _text_description(prefix, el) -> dict:
    p = prefix + "_" if prefix else ""
    families = tuple(f.strip().strip("'") for f in el.get("font-family").split(","))
    return {p + "font_family": families, p + "font_size_pt": float(el.get("font-size")) / PX_PER_PT,
            p + "font_weight": el.get("font-weight"), p + "font_style": el.get("font-style"),
            p + "color": _color(el.get("fill"))}


def _path_points(el):
    return [(float(x), float(y)) for x, y in re.findall(r"[ML](-?[0-9.e]+),(-?[0-9.e]+)", el.get("d") or "")]


def _shape_centre(el):
    """Centre of one drawn marker in pixels, from its geometry."""
    if el.tag == _NS + "circle":
        return float(el.get("cx")), float(el.get("cy"))
    if el.tag == _NS + "rect":
        return float(el.get("x")) + float(el.get("width")) / 2.0, float(el.get("y")) + float(el.get("height")) / 2.0
    points = _path_points(el)
    if not points:
        return math.nan, math.nan
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0


def _shape_from_geometry(el) -> Optional[str]:
    """Which marker shape an element draws, judged from its geometry only."""
    if el.tag == _NS + "circle":
        return "o"
    if el.tag == _NS + "rect":
        return "s"
    if el.tag != _NS + "path":
        return None
    d = el.get("d") or ""
    points = _path_points(el)
    if d.rstrip().endswith("Z"):
        return _closed_shape(el, points)
    if len(points) == 4 and d.count("M") == 2:
        (x0, y0), (x1, y1) = points[0], points[1]
        return "+" if (x0 == x1 or y0 == y1) else "x"
    return None


def _closed_shape(el, points) -> Optional[str]:
    """A diamond or a triangle, judged from its corners."""
    if len(points) == 4:
        return "D"
    if len(points) == 3:
        cx, cy = _shape_centre(el)
        # One corner above the centre (screen y points down): pointing up
        above = sum(1 for _, y in points if y < cy)
        return "^" if above == 1 else "v"
    return None


def _shape_width_px(el) -> float:
    """Width of one drawn marker, from its geometry."""
    if el.tag == _NS + "circle":
        return 2.0 * float(el.get("r"))
    if el.tag == _NS + "rect":
        return float(el.get("width"))
    xs = [float(v) for v in re.findall(r"[ML](-?[0-9.]+),", el.get("d"))]
    return max(xs) - min(xs)


def _color(value: Optional[str]) -> Optional[str]:
    return None if value in (None, "none") else value


def _fmt(value: float) -> str:
    return "{0:.6g}".format(value)
