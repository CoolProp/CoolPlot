# -*- coding: utf-8 -*-
"""A backend that draws scenes with plotly.

The scene becomes a ``plotly.graph_objects.Figure``: lines and markers are
scatter traces, texts are annotations. Traces are updated in place, so an
application that shows ``renderer.figure`` (for example in a notebook or
a Dash app) keeps the same objects across updates.

plotly takes care of the page, but a few things are decided here so that
the figure follows the scene exactly:

* The figure has a fixed size and fixed margins (``margin.autoexpand`` is
  off), so the plot area is known; text angles depend on it.
* Ticks are placed by :func:`coolplot.render.ticks.ticks` and written with
  the central number format, as ``tickvals`` and ``ticktext``.
* Lengths in the scene are in points; plotly uses CSS pixels (96 per
  inch), so every length is multiplied by 4/3.
* Log axes take their range in powers of ten, and plotly places
  annotations on log axes in powers of ten as well.

Limitations (``limitations``, see docs/contributing/writing_a_backend.md):

* "line_caps": plotly has no setting for line caps and joins.
* "text_order": annotations are always drawn above all traces, so a line
  with a higher z order than a text still appears below it.

Texts with ``clip=True`` are hidden when their anchor leaves the plot
area, because plotly does not clip annotations; a text that only partly
reaches outside is shown whole.

The legend shows one entry per scene legend text, drawn with a separate
sample trace that overlays the line and marker styles of the entry.
"""
from __future__ import annotations

import html
import importlib.util
import json
import math
import os
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
import plotly.graph_objects as go

from ..scene import AxesSpec, Item, Line, Markers, Text, drawable_limits
from ..core.numbers import format_number
from ..style.values import AxesStyle, LineStyle, TextStyle, dash_pattern_pt
from .base import Renderer, SyncReport
from .ticks import ticks

PX_PER_PT = 4.0 / 3.0
TRANSPARENT = "rgba(0,0,0,0)"

_SYMBOLS = {"o": "circle", "s": "square", "^": "triangle-up", "v": "triangle-down", "D": "diamond",
            "x": "x-thin", "+": "cross-thin"}
_SHAPES = {v: k for k, v in _SYMBOLS.items()}
#: Width of the drawn symbol relative to plotly's marker.size, measured in
#: plotly.js (tests/test_plotly.py checks it in a browser). The size given
#: to plotly is divided by it, so that every shape is as wide as asked.
SYMBOL_WIDTH = {"circle": 1.0, "square": 1.0, "triangle-up": 1.1547, "triangle-down": 1.1547,
                "diamond": 1.3, "x-thin": 1.0, "cross-thin": 1.4}

_H_ANCHOR = {"left": "left", "center": "center", "right": "right"}
_V_ANCHOR = {"bottom": "bottom", "center": "middle", "top": "top"}
_V_BACK = {v: k for k, v in _V_ANCHOR.items()}

_LEGEND = {"upper left": dict(x=0.01, y=0.99, xanchor="left", yanchor="top"),
           "upper right": dict(x=0.99, y=0.99, xanchor="right", yanchor="top"),
           "lower left": dict(x=0.01, y=0.01, xanchor="left", yanchor="bottom"),
           "lower right": dict(x=0.99, y=0.01, xanchor="right", yanchor="bottom"),
           "outside right": dict(x=1.02, y=1.0, xanchor="left", yanchor="top")}




#: File formats drawn by kaleido.
IMAGE_SUFFIXES = (".pdf", ".png", ".svg", ".jpg", ".jpeg", ".webp")


def kaleido_available() -> bool:
    """True if plotly can draw images and PDF: kaleido is installed and finds a Chrome."""
    if importlib.util.find_spec("kaleido") is None:
        return False
    if os.environ.get("BROWSER_PATH"):
        return os.path.isfile(os.environ["BROWSER_PATH"])
    try:
        from choreographer.browsers.chromium import Chromium   # kaleido's own browser lookup
        return Chromium.find_browser(skip_local=False) is not None
    except Exception:
        return False   # cannot tell: do not promise PDF (saving still tries)

def _escape(text: str) -> str:
    """Text for plotly, which reads a few HTML tags: escape <, > and &, but
    not quotes, which plotly would show as &quot;. A dollar sign becomes an
    entity: where MathJax is loaded (as in kaleido, which draws images and
    PDF) plotly would typeset "$5 or $6" as math."""
    return html.escape(text, quote=False).replace("$", "&#36;")


def _unescape(text: str) -> str:
    """The reverse of _escape and nothing more: a stray &quot; stays visible
    in the read-back, as it does in the browser."""
    return text.replace("&#36;", "$").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _color(value: Optional[str]) -> str:
    return value if value is not None else TRANSPARENT


def _color_back(value) -> Optional[str]:
    return None if value in (None, TRANSPARENT, "none") else value


def _family(families) -> str:
    return ", ".join('"{0}"'.format(f) if " " in f else f for f in families)


def _family_back(value: str) -> Tuple[str, ...]:
    return tuple(f.strip().strip('"').strip("'") for f in (value or "").split(","))


def _dash(style: LineStyle) -> str:
    pattern = dash_pattern_pt(style.dash, style.width_pt)
    if not pattern:
        return "solid"
    return ",".join("{0:.4g}px".format(v * PX_PER_PT) for v in pattern)


def _dash_back(value: str) -> Tuple[float, ...]:
    if value in (None, "solid"):
        return ()
    return tuple(float(v) / PX_PER_PT for v in re.findall(r"([0-9.]+)px", value))


def _font(style: TextStyle) -> dict:
    font = dict(family=_family(style.font.family), size=style.font.size_pt * PX_PER_PT,
                color=_color(style.color), weight=style.font.weight, style=style.font.style)
    return font


def _font_description(prefix: str, font, full: bool = True) -> dict:
    p = prefix + "_" if prefix else ""
    out = {p + "font_family": _family_back(font.family), p + "font_size_pt": font.size / PX_PER_PT,
           p + "color": _color_back(font.color)}
    if full:
        out.update({p + "font_weight": font.weight if isinstance(font.weight, str) else
                    ("bold" if (font.weight or 400) >= 600 else "normal"),
                    p + "font_style": font.style or "normal"})
    return out


class PlotlyRenderer(Renderer):
    """Draw a scene into a plotly Figure

    Parameters
    ----------
    width, height : int
        Size of the figure in CSS pixels.
    margins : (left, right, top, bottom)
        Space around the plot area in pixels. An outside legend adds to the
        right margin.
    figure : plotly.graph_objects.Figure, optional
        Draw into this figure (for example a FigureWidget); it should be
        empty.
    """

    capabilities = frozenset({"in_place_updates", "file_output"})
    limitations = frozenset({"line_caps", "text_order"})
    default_suffix = ".html"
    text_output = True
    owns_canvas = True

    def __init__(self, width: int = 800, height: int = 600, margins=(80, 30, 50, 60), figure=None,
                 div_id: str = "coolplot"):
        super().__init__()
        if kaleido_available():
            # Images and PDF need the optional kaleido package (and Chrome)
            self.capabilities = type(self).capabilities | {"pdf_output"}
        self.width, self.height, self.margins = int(width), int(height), tuple(margins)
        self.div_id = re.sub(r"[^A-Za-z0-9_-]+", "-", div_id) or "coolplot"
        self.figure = figure if figure is not None else go.Figure()
        self._traces: Dict[str, object] = {}      # item id -> main trace
        self._casings: Dict[str, object] = {}     # item id -> casing trace (lines with a casing)
        self._texts: Dict[str, Text] = {}
        self._samples: List[object] = []          # legend sample traces
        self._rank: Dict[str, int] = {}
        self._ranges = ((0.0, 1.0), (0.0, 1.0))
        self._legend_style = None
        self._applied_log = None       # (x_log, y_log) the trace data was prepared for
        self._clipped = set()          # texts hidden because their anchor is outside
        self.figure.update_layout(width=self.width, height=self.height, autosize=False,
                                  showlegend=False, hovermode="closest")
        self._apply_margins()

    # Geometry -----------------------------------------------------------
    def _legend_room(self) -> float:
        st = self._legend_style
        if st is None or not st.visible or not self._samples or st.location != "outside right":
            return 0.0
        size_px = st.text.font.size_pt * PX_PER_PT
        longest = max((len(t.name or "") for t in self._samples), default=0)
        return 50.0 + 0.6 * size_px * longest

    def _apply_margins(self):
        left, right, top, bottom = self.margins
        right += self._legend_room()
        self.figure.update_layout(margin=dict(l=left, r=right, t=top, b=bottom, autoexpand=False))

    def plot_size_pt(self):
        """(width, height) of the plot area in points, from the figure layout."""
        m = self.figure.layout.margin
        return ((self.width - m.l - m.r) / PX_PER_PT, (self.height - m.t - m.b) / PX_PER_PT)

    def _log(self):
        axes = self._axes or AxesSpec()
        return axes.x_log, axes.y_log

    def _shown(self, values, log: bool) -> np.ndarray:
        """Values as plotly gets them: NaN where a value cannot be shown."""
        values = np.asarray(values, dtype=float)
        if log:
            values = np.where(values > 0.0, values, np.nan)
        return values

    # Backend hooks ------------------------------------------------------
    def _set_axes(self, axes: AxesSpec):
        st: AxesStyle = axes.style
        layout = self.figure.layout
        self.figure.update_layout(
            plot_bgcolor=_color(st.background), paper_bgcolor=_color(st.figure_background),
            title=dict(text=_escape(axes.title), font=_font(st.title), x=0.5, xanchor="center"))
        for name, label, log in (("xaxis", axes.x_label, axes.x_log), ("yaxis", axes.y_label, axes.y_log)):
            grid, minor = st.grid_major, st.grid_minor
            settings = dict(
                type="log" if log else "linear", title=dict(text=_escape(label), font=_font(st.axis_label)),
                showline=st.frame_color is not None, mirror=True, linecolor=_color(st.frame_color),
                linewidth=st.frame_width_pt * PX_PER_PT, layer="above traces", zeroline=False,
                ticks="outside" if st.tick_direction == "out" else "inside", tickcolor=_color(st.tick_color),
                ticklen=st.tick_length_pt * PX_PER_PT, tickwidth=st.tick_width_pt * PX_PER_PT,
                tickfont=_font(st.tick_label), tickmode="array",
                showgrid=grid is not None and grid.color is not None)
            if settings["showgrid"]:
                settings.update(gridcolor=grid.color, gridwidth=grid.width_pt * PX_PER_PT, griddash=_dash(grid))
            if minor is not None and minor.color is not None:
                settings["minor"] = dict(showgrid=True, gridcolor=minor.color, gridwidth=minor.width_pt * PX_PER_PT,
                                         griddash=_dash(minor), ticks="")
            else:
                settings["minor"] = dict(showgrid=False)
            layout[name].update(settings)
        self._legend_style = axes.style.legend

    def _add(self, item: Item):
        if isinstance(item, Text):
            self._texts[item.id] = item
            return
        if isinstance(item, Line) and item.style.casing_color is not None and item.style.casing_width_pt > 0.0:
            self.figure.add_trace(go.Scatter(mode="lines", showlegend=False, hoverinfo="skip"))
            self._casings[item.id] = self.figure.data[-1]
        self.figure.add_trace(go.Scatter(showlegend=False))
        self._traces[item.id] = self.figure.data[-1]
        self._apply(item)

    def _update(self, old: Item, new: Item):
        cased_before = old.id in self._casings
        cased_now = isinstance(new, Line) and new.style.casing_color is not None and new.style.casing_width_pt > 0
        if type(old) is not type(new) or cased_before != cased_now:
            super()._update(old, new)   # remove and add again
            return
        if isinstance(new, Text):
            self._texts[new.id] = new
            return
        self._apply(new)

    def _remove(self, item: Item):
        self._texts.pop(item.id, None)
        gone = {id(t) for t in (self._traces.pop(item.id, None), self._casings.pop(item.id, None)) if t is not None}
        if gone:
            self.figure.data = tuple(t for t in self.figure.data if id(t) not in gone)

    def _reorder(self, order):
        self._rank = {item_id: i for i, item_id in enumerate(order)}
        for item_id in self._traces:
            self._stack(item_id)

    def _stack(self, item_id):
        rank = self._rank.get(item_id, len(self._rank))
        self._traces[item_id].zorder = 2 * rank + 1
        if item_id in self._casings:
            self._casings[item_id].zorder = 2 * rank

    def _apply(self, item: Item):
        trace = self._traces[item.id]
        x_log, y_log = self._log()
        s = item.style
        data = dict(x=self._shown(item.x, x_log), y=self._shown(item.y, y_log), visible=item.visible,
                    opacity=s.alpha, name=_escape(item.legend or item.id), cliponaxis=True, connectgaps=False,
                    meta=dict(item=item.id))
        if isinstance(item, Line):
            trace.update(mode="lines", line=dict(color=_color(s.color), width=s.width_pt * PX_PER_PT,
                                                 dash=_dash(s)), **data)
            casing = self._casings.get(item.id)
            if casing is not None:
                casing.update(line=dict(color=s.casing_color, width=(s.width_pt + 2 * s.casing_width_pt) * PX_PER_PT,
                                        dash=_dash(s)), x=data["x"], y=data["y"], visible=item.visible,
                              opacity=s.alpha, cliponaxis=True, connectgaps=False, meta=dict(casing=item.id))
        else:
            symbol = _SYMBOLS[s.shape]
            line_only = s.shape in ("x", "+")
            trace.update(mode="markers", marker=dict(
                symbol=symbol, size=s.size_pt * PX_PER_PT / SYMBOL_WIDTH[symbol],
                color=TRANSPARENT if line_only or s.face_color is None else s.face_color,
                line=dict(color=_color(s.edge_color), width=s.edge_width_pt * PX_PER_PT)), **data)
        self._stack(item.id)

    def _set_legend(self, entries, style):
        self._legend_style = style
        old = {id(t) for t in self._samples}
        if old:
            self.figure.data = tuple(t for t in self.figure.data if id(t) not in old)
        self._samples = []
        if style is None or not style.visible or not entries:
            self.figure.update_layout(showlegend=False)
            return
        for rank, (text, items) in enumerate(entries):
            self.figure.add_trace(go.Scatter(**_legend_sample(rank, text, items)))
            self._samples.append(self.figure.data[-1])
        legend = dict(_LEGEND[style.location], bgcolor=_color(style.background),
                      bordercolor=_color(style.frame_color), borderwidth=1 if style.frame_color else 0,
                      font=_font(style.text), traceorder="normal")
        self.figure.update_layout(showlegend=True, legend=legend)

    def _finish(self, report: SyncReport):
        if not report.changed:
            return
        self._apply_margins()
        axes = self._axes or AxesSpec()
        if self._applied_log != (axes.x_log, axes.y_log):
            # Values a log axis cannot show become gaps; redo them for new scales
            self._applied_log = (axes.x_log, axes.y_log)
            for item_id in self._traces:
                self._apply(self._drawn[item_id])
        ranges = []
        for limits, key, log, name in ((axes.x_limits, "x", axes.x_log, "xaxis"),
                                       (axes.y_limits, "y", axes.y_log, "yaxis")):
            if limits is None:
                limits = self._autoscale(key, log)
            lo, hi = drawable_limits(limits, log)
            ranges.append((lo, hi))
            self._set_axis_range(name, lo, hi, log, axes)
        self._ranges = tuple(ranges)
        self._annotate()

    def _set_axis_range(self, name: str, lo: float, hi: float, log: bool, axes: AxesSpec):
        """The range and the tick positions and texts of one axis."""
        major = ticks(lo, hi, log)
        self.figure.layout[name].update(
            range=[math.log10(lo), math.log10(hi)] if log else [lo, hi],
            tickvals=major, ticktext=[format_number(v, axes.tick_digits) for v in major])
        st = axes.style
        if st.grid_minor is not None and st.grid_minor.color is not None:
            self.figure.layout[name].minor.tickvals = ticks(lo, hi, log, minor=True)

    def _autoscale(self, key: str, log: bool):
        values = []
        for item in self._drawn.values():
            if item.visible and isinstance(item, (Line, Markers)):
                v = np.asarray(getattr(item, key), dtype=float)
                values.append(v[np.isfinite(v) & ((v > 0.0) if log else True)])
        values = np.concatenate(values) if values else np.array([])
        if values.size == 0:
            return (1.0, 10.0) if log else (0.0, 1.0)
        return float(values.min()), float(values.max())

    # Texts ----------------------------------------------------------------
    def _figure_ranges(self):
        """The axis ranges the figure really holds, in data values."""
        out = []
        for axis, wanted in zip((self.figure.layout.xaxis, self.figure.layout.yaxis), self._ranges):
            if axis.range is None:   # before the first sync
                out.append(wanted)
                continue
            lo, hi = (float(v) for v in axis.range)
            if axis.type == "log":
                # 10 ** log10(50) is 49.99999...: keep the exact value when the figure holds it
                exact = all(math.isclose(v, math.log10(w), rel_tol=1e-12, abs_tol=1e-12)
                            for v, w in zip((lo, hi), wanted) if w > 0.0)
                lo, hi = wanted if exact else (10.0 ** lo, 10.0 ** hi)
            out.append((lo, hi))
        return tuple(out)

    def _fraction(self, x, y):
        """A point as fractions of the plot area, y up, read from the figure."""
        (x0, x1), (y0, y1) = self._figure_ranges()
        x_log, y_log = self._log()

        def frac(v, lo, hi, log):
            if log:
                return (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) if v > 0 else math.nan
            return (v - lo) / (hi - lo)
        return frac(x, x0, x1, x_log), frac(y, y0, y1, y_log)

    def _screen_angle(self, item: Text) -> float:
        """Counter-clockwise screen angle of the text direction, kept upright."""
        if item.direction is None:
            return 0.0
        width, height = self.plot_size_pt()
        fx0, fy0 = self._fraction(item.x, item.y)
        step = 1e-6
        fx1, fy1 = self._fraction(item.x + item.direction[0] * step, item.y + item.direction[1] * step)
        angle = math.degrees(math.atan2((fy1 - fy0) * height, (fx1 - fx0) * width))
        if not math.isfinite(angle):
            return 0.0
        if angle > 90.0:
            angle -= 180.0
        elif angle <= -90.0:
            angle += 180.0
        return angle

    def _annotate(self):
        """Rebuild the annotations from the texts, in drawing order."""
        x_log, y_log = self._log()
        annotations = []
        self._clipped = set()
        for item_id in sorted(self._texts, key=lambda i: self._rank.get(i, 0)):
            item = self._texts[item_id]
            if not _showable(item, x_log, y_log):
                continue
            fx, fy = self._fraction(item.x, item.y)
            inside = 0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0
            if item.visible and item.clip and not inside:
                self._clipped.add(item_id)
            annotations.append(self._annotation_of(item_id, item, x_log, y_log, inside))
        self.figure.layout.annotations = annotations

    def _annotation_of(self, item_id: str, item: Text, x_log: bool, y_log: bool, inside: bool) -> dict:
        s = item.style
        return dict(
            x=math.log10(item.x) if x_log else item.x, y=math.log10(item.y) if y_log else item.y,
            xref="x", yref="y", text=_escape(item.text), showarrow=False,
            textangle=-self._screen_angle(item), xanchor=_H_ANCHOR[s.h_align], yanchor=_V_ANCHOR[s.v_align],
            xshift=item.offset_pt[0] * PX_PER_PT, yshift=item.offset_pt[1] * PX_PER_PT,
            font=_font_with_halo(s), opacity=s.alpha, visible=item.visible and (inside or not item.clip),
            name=item_id, captureevents=False)

    # Output -------------------------------------------------------------
    def save(self, path: str, include_plotlyjs="cdn"):
        """Write the chart; the format follows the file name.

        ".html": a page (plotly.js from its CDN by default); ".json": the
        figure as JSON; ".pdf", ".png", ".svg", ".jpg", ".webp": an image
        drawn by kaleido, an optional package (pip install kaleido) that
        needs Chrome. A PDF gets the chart title as its title and no
        creation date, so the same chart gives the same file.
        """
        suffix = os.path.splitext(os.fspath(path))[1].lower()
        if suffix in IMAGE_SUFFIXES:
            self._write_image(path, suffix)
            return
        if suffix == ".json":
            text = json.dumps(self.figure.to_plotly_json(), sort_keys=True, ensure_ascii=True,
                              cls=_PlotlyEncoder)
        elif suffix not in (".html", ".htm"):
            raise ValueError("PlotlyRenderer writes .html, .json and, with kaleido, {0}; not {1!r}.".format(
                ", ".join(IMAGE_SUFFIXES), suffix or "a name without extension"))
        else:
            text = self.figure.to_html(include_plotlyjs=include_plotlyjs, full_html=True, div_id=self.div_id)
            text = text.encode("ascii", "xmlcharrefreplace").decode("ascii")
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write(text)

    def _write_image(self, path, suffix: str):
        if importlib.util.find_spec("kaleido") is None:
            raise RuntimeError("Writing {0} files with plotly needs kaleido: pip install kaleido. Kaleido also "
                               "needs Chrome (plotly_get_chrome installs one).".format(suffix))
        # Sizes in CSS pixels; a PDF page comes out in points (0.75 per pixel), as the scene is laid out.
        # Full Chrome now and then refuses to print a PDF ("Printing is not available"): try twice.
        for attempt in (1, 2):
            try:
                self.figure.write_image(path, width=self.width, height=self.height)
                break
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError("Kaleido could not write {0}: {1}".format(path, e)) from e
        if suffix == ".pdf":
            # Kaleido writes a creation date and no title; rewrite the
            # information so that the same chart gives the same file.
            from ..testing.pdf_reader import replace_info
            title = self._axes.title if self._axes is not None else ""
            replace_info(path, {"Title": title} if title else {})

    def show(self):
        """Show the figure (``figure.show()``)."""
        self.figure.show()

    # Read back ----------------------------------------------------------
    def backend_object(self, item_id):
        """The plotly trace or annotation drawn for an item id."""
        return self._traces.get(item_id) or self._annotation(item_id)

    def _annotation(self, item_id):
        return next((a for a in self.figure.layout.annotations if a.name == item_id), None)

    def describe_item(self, item_id: str) -> dict:
        """Read back the item as drawn, from its trace or annotation."""
        item = self._drawn[item_id]   # KeyError for unknown ids, as required
        if isinstance(item, Text):
            return self._describe_text(item_id)
        trace = self._traces[item_id]
        kind = "line" if trace.mode == "lines" else "markers"
        out = {"visible": trace.visible is not False, "kind": kind, "clip": bool(trace.cliponaxis),
               "alpha": 1.0 if trace.opacity is None else trace.opacity}
        if not out["visible"]:
            return out
        xs = np.asarray(trace.x, dtype=float)
        ys = np.asarray(trace.y, dtype=float)
        ok = np.isfinite(xs) & np.isfinite(ys)
        out["n_points"] = int(ok.sum())
        out["drawn_points"] = [self._fraction(x, y) for x, y in zip(xs[ok], ys[ok])]
        visible = sorted((t for i, t in self._traces.items() if t.visible is not False), key=lambda t: t.zorder)
        out["draw_rank"] = [t.meta["item"] for t in visible].index(item_id)
        if kind == "line":
            out.update(_describe_trace_line(trace, self._casings.get(item_id)))
        else:
            out.update(_describe_trace_markers(trace))
        return out

    def _describe_text(self, item_id: str) -> dict:
        annotation = self._annotation(item_id)
        # A text hidden because it lies outside the plot area is clipped,
        # not hidden: it is described like any other clipped text
        shown = {a.name for a in self.figure.layout.annotations if a.visible is not False} | self._clipped
        if annotation is None or item_id not in shown:
            return {"visible": False, "kind": "text"}
        texts = [a.name for a in self.figure.layout.annotations if a.name in shown]
        fx, fy = self._fraction(*self._annotation_data_position(annotation))
        width, height = self.plot_size_pt()
        dx, dy = annotation.xshift / PX_PER_PT, annotation.yshift / PX_PER_PT
        out = {"visible": True, "kind": "text", "draw_rank": texts.index(item_id),
               "text": _unescape(annotation.text), "alpha": 1.0 if annotation.opacity is None else annotation.opacity,
               "h_align": annotation.xanchor, "v_align": _V_BACK[annotation.yanchor],
               "screen_angle_deg": -(annotation.textangle or 0.0), "offset_pt": (dx, dy),
               # Clipping is emulated by hiding texts outside the plot area
               "clip": self._drawn[item_id].clip,
               "drawn_points": [(fx + dx / width, fy + dy / height)]}
        out.update(_font_description("", annotation.font))
        out.update(_halo_from_shadow(annotation.font.shadow))
        return out

    def _annotation_data_position(self, annotation):
        """(x, y) of an annotation in data values (plotly keeps log10 on log axes)."""
        x_log, y_log = self._log()
        return (10.0 ** annotation.x if x_log else annotation.x, 10.0 ** annotation.y if y_log else annotation.y)

    def describe_axes(self) -> dict:
        """Read back the axes as drawn, from the layout."""
        layout = self.figure.layout
        xa, ya = layout.xaxis, layout.yaxis
        (x0, x1), (y0, y1) = self._figure_ranges()
        out = dict(
            x_log=xa.type == "log", y_log=ya.type == "log", x_limits=(x0, x1), y_limits=(y0, y1),
            background=_color_back(layout.plot_bgcolor), figure_background=_color_back(layout.paper_bgcolor),
            plot_size_pt=self.plot_size_pt(), legend=self._legend_description(),
            grid_color=xa.gridcolor if xa.showgrid else None,
            grid_minor_color=xa.minor.gridcolor if xa.minor.showgrid else None,
            x_tick_labels=_tick_label_rows(xa), y_tick_labels=_tick_label_rows(ya),
        )
        out.update(_describe_layout_frame(xa, ya))
        out.update(_describe_layout_texts(layout))
        for prefix, axis in (("", xa), ("y_", ya)):
            out.update(_describe_axis_ticks(prefix, axis))
        if xa.showgrid:
            out.update(_describe_layout_grid(xa, ya, (x0, x1), (y0, y1)))
        if layout.showlegend and self._samples:
            out.update(_describe_layout_legend(layout.legend))
        return out

    def _legend_description(self):
        if not self.figure.layout.showlegend:
            return []
        rows = []
        for sample in sorted(self._samples, key=lambda t: t.legendrank):
            colors = set()
            if "lines" in sample.mode:
                colors.add(_color_back(sample.line.color))
            if "markers" in sample.mode:
                colors.add(_color_back(sample.marker.line.color) or _color_back(sample.marker.color))
            rows.append((_unescape(sample.name), tuple(sorted(colors - {None}))))
        return rows


def _showable(item: Text, x_log: bool, y_log: bool) -> bool:
    """Whether a text has a place on the axes at all (finite, positive on log axes)."""
    if not (math.isfinite(item.x) and math.isfinite(item.y)):
        return False
    return not ((x_log and item.x <= 0) or (y_log and item.y <= 0))


def _legend_sample(rank: int, text: str, items) -> dict:
    """An invisible trace whose legend entry shows the line and marker styles of the items."""
    lines = [i for i in items if isinstance(i, Line)]
    markers = [i for i in items if isinstance(i, Markers)]
    mode = "+".join(m for m, used in (("lines", lines), ("markers", markers)) if used)
    sample = dict(x=[None], y=[None], mode=mode, name=_escape(text), showlegend=True, hoverinfo="skip",
                  legendrank=rank + 1, meta=dict(legend=True))
    if lines:
        ls = lines[0].style
        sample["line"] = dict(color=_color(ls.color), width=ls.width_pt * PX_PER_PT, dash=_dash(ls))
    if markers:
        sample["marker"] = _marker_sample(markers[0].style)
    return sample


def _marker_sample(ms) -> dict:
    symbol = _SYMBOLS[ms.shape]
    face = TRANSPARENT if ms.face_color is None or ms.shape in ("x", "+") else ms.face_color
    return dict(symbol=symbol, size=ms.size_pt * PX_PER_PT / SYMBOL_WIDTH[symbol], color=face,
                line=dict(color=_color(ms.edge_color), width=ms.edge_width_pt * PX_PER_PT))


def _font_with_halo(s: TextStyle) -> dict:
    """The annotation font, with the halo drawn as four text shadows."""
    font = _font(s)
    if s.halo_color is not None and s.halo_width_pt > 0.0:
        w = s.halo_width_pt * PX_PER_PT
        font["shadow"] = ", ".join("{0:.4g}px {1:.4g}px {2:.4g}px {3}".format(dx * w, dy * w, 0, s.halo_color)
                                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    return font


def _halo_from_shadow(shadow) -> dict:
    match = re.match(r"\s*(-?[0-9.]+)px [^,]* (#[0-9a-fA-F]{6})", shadow or "")
    if match:
        return dict(halo_color=match.group(2), halo_width_pt=abs(float(match.group(1))) / PX_PER_PT)
    return dict(halo_color=None, halo_width_pt=0.0)


def _describe_trace_line(trace, casing) -> dict:
    line = trace.line
    out = dict(color=_color_back(line.color), width_pt=line.width / PX_PER_PT, dash_pt=_dash_back(line.dash))
    if casing is not None:
        width = casing.line.width / PX_PER_PT
        out.update(casing_color=_color_back(casing.line.color), casing_width_pt=(width - out["width_pt"]) / 2,
                   casing_dash_pt=_dash_back(casing.line.dash),
                   casing_alpha=1.0 if casing.opacity is None else casing.opacity)
    else:
        out.update(casing_color=None, casing_width_pt=0.0)
    return out


def _describe_trace_markers(trace) -> dict:
    marker = trace.marker
    shape = _SHAPES[marker.symbol]
    return dict(shape=shape, size_pt=marker.size * SYMBOL_WIDTH[marker.symbol] / PX_PER_PT,
                face_color=None if shape in ("x", "+") else _color_back(marker.color),
                edge_color=_color_back(marker.line.color), edge_width_pt=marker.line.width / PX_PER_PT,
                connected="lines" in trace.mode)


def _tick_label_rows(axis):
    return list(zip((float(v) for v in axis.tickvals or ()), axis.ticktext or ()))


def _describe_layout_frame(xa, ya) -> dict:
    mirrored = (xa.showline and ya.showline and xa.mirror is True and ya.mirror is True
                and xa.linecolor == ya.linecolor and xa.linewidth == ya.linewidth)
    return dict(frame_color=_color_back(xa.linecolor) if xa.showline else None,
                frame_width_pt=(xa.linewidth or 0.0) / PX_PER_PT, frame_sides=4 if mirrored else 0,
                items_below_frame=xa.layer == "above traces" and ya.layer == "above traces")


def _describe_layout_texts(layout) -> dict:
    """Axis titles, the title and their fonts, plus the tick label font."""
    xa, ya = layout.xaxis, layout.yaxis
    out = dict(x_label=_unescape(xa.title.text or ""), y_label=_unescape(ya.title.text or ""),
               title=_unescape(layout.title.text or ""))
    out.update(_font_description("x_label", xa.title.font))
    out.update(_font_description("y_label", ya.title.font))
    if out["title"]:
        out.update(_font_description("title", layout.title.font))
    out.update(_font_description("tick_label", xa.tickfont, full=False))
    return out


def _describe_axis_ticks(prefix: str, axis) -> dict:
    return {prefix + "tick_direction": "out" if axis.ticks == "outside" else "in",
            prefix + "tick_color": _color_back(axis.tickcolor),
            prefix + "tick_length_pt": axis.ticklen / PX_PER_PT,
            prefix + "tick_width_pt": axis.tickwidth / PX_PER_PT}


def _describe_layout_grid(xa, ya, x_range, y_range) -> dict:
    x0, x1 = x_range
    y0, y1 = y_range
    out = dict(grid_width_pt=xa.gridwidth / PX_PER_PT, grid_dash_pt=_dash_back(xa.griddash),
               grid_below_items=True,   # plotly always draws the grid below the traces
               x_grid_lines=sum(1 for v in xa.tickvals or () if min(x0, x1) <= v <= max(x0, x1)),
               y_grid_lines=sum(1 for v in ya.tickvals or () if min(y0, y1) <= v <= max(y0, y1)))
    out["grid_lines"] = out["x_grid_lines"] + out["y_grid_lines"]
    return out


def _describe_layout_legend(legend) -> dict:
    location = next((name for name, place in _LEGEND.items()
                     if (legend.x, legend.y, legend.xanchor, legend.yanchor)
                     == (place["x"], place["y"], place["xanchor"], place["yanchor"])), None)
    out = dict(legend_location=location, legend_background=_color_back(legend.bgcolor),
               items_below_legend=True)   # plotly draws the legend above everything
    out.update(_font_description("legend", legend.font, full=False))
    return out


class _PlotlyEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, np.ndarray):
            return [None if not math.isfinite(v) else float(v) for v in o.ravel()]
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        return super().default(o)
