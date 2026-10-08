# -*- coding: utf-8 -*-
"""Matplotlib backend.

This is the only module in CoolPlot that imports matplotlib. Existing
artists are updated in place (``set_data``, ``set_color``, ...) instead of
being recreated, and the canvas is asked for a repaint with ``draw_idle``,
which matplotlib coalesces in interactive GUIs.

Points to note for maintainers
------------------------------
* Matplotlib multiplies dash lengths by the line width when the rcParam
  ``lines.scale_dashes`` is on. CoolPlot dash patterns are already final
  lengths in points, so they are divided by the width before they are
  handed over (see :func:`_mpl_dashes`).
* Casings and text halos are path effects: a wider stroke in the casing or
  halo colour drawn underneath the normal rendering.
* Ties in z order are broken by adding a tiny fraction per position, so
  the scene order decides the stacking, not the order artists were created.
"""
from __future__ import annotations

import math

import numpy as np
import matplotlib
from matplotlib import patheffects
from matplotlib.colors import to_hex
from matplotlib.font_manager import FontProperties

from ..scene import AxesSpec, Item, Line, Markers, Text
from ..style import dash_pattern_pt
from .base import Renderer, SyncReport

_CAPS = {"butt": "butt", "round": "round", "square": "projecting"}
_CAPS_BACK = {v: k for k, v in _CAPS.items()}
_V_ALIGN = {"bottom": "bottom", "center": "center", "top": "top"}
_RANK_STEP = 1e-9    # z order tie breaker, small against any real z_order difference


def _mpl_dashes(dash, width_pt):
    """Matplotlib linestyle for a CoolPlot dash, compensating dash scaling."""
    seq = dash_pattern_pt(dash, width_pt)
    if not seq:
        return "solid"
    if matplotlib.rcParams["lines.scale_dashes"] and width_pt > 0.0:
        seq = tuple(v / width_pt for v in seq)
    return (0.0, seq)


def _hex_or_none(color):
    if color is None:
        return None
    if isinstance(color, str) and color.lower() == "none":
        return None
    rgba = matplotlib.colors.to_rgba(color)
    if rgba[3] == 0.0:
        return None
    return to_hex(rgba, keep_alpha=False)


_GENERIC = {"sans-serif", "serif", "monospace", "cursive", "fantasy"}
_installed = None


def _families(family):
    """Keep only installed fonts and generic names, in order.

    Matplotlib logs a warning for every family in the list it cannot find,
    which would flood the console for portable lists like
    ("Helvetica", "Arial", "sans-serif").
    """
    global _installed
    if _installed is None:
        from matplotlib.font_manager import fontManager
        _installed = {f.name.lower() for f in fontManager.ttflist}
    kept = [f for f in family if f.lower() in _GENERIC or f.lower() in _installed]
    return kept or ["sans-serif"]


def _font(font) -> FontProperties:
    return FontProperties(family=_families(font.family), size=font.size_pt, weight=font.weight,
                          style=font.style)


def _apply_text_style(text, style):
    text.set_fontfamily(_families(style.font.family))
    text.set_fontsize(style.font.size_pt)
    text.set_fontweight(style.font.weight)
    text.set_fontstyle(style.font.style)
    text.set_color(style.color or "none")
    text.set_alpha(style.alpha)
    if style.halo_color is not None and style.halo_width_pt > 0.0:
        text.set_path_effects([patheffects.withStroke(linewidth=2.0 * style.halo_width_pt,
                                                      foreground=style.halo_color)])
    else:
        text.set_path_effects([])


def _stroke_effect(artist):
    for effect in artist.get_path_effects():
        if isinstance(effect, patheffects.Stroke):
            return effect
    return None


class MatplotlibRenderer(Renderer):
    """Draw a scene into a matplotlib Axes

    Parameters
    ----------
    ax : matplotlib.axes.Axes, optional
        Draw into an existing Axes, for example one embedded in a GUI or
        one panel of a larger figure. The figure then stays under your
        control: its background and layout are not touched.
    use_pyplot : bool
        Only relevant when ``ax`` is None. If True (default) the new figure
        is created through pyplot so that :meth:`show` works. Set it to
        False in servers and GUIs, where pyplot's global state is unwanted.
    figsize : tuple
        Size of a newly created figure in inches.
    """

    capabilities = frozenset({"in_place_updates", "file_output", "interactive"})
    default_suffix = ".png"
    text_output = False

    def __init__(self, ax=None, use_pyplot: bool = True, figsize=(8.0, 6.0)):
        super().__init__()
        self._owns_figure = ax is None
        if ax is None:
            if use_pyplot:
                import matplotlib.pyplot as plt
                figure = plt.figure(figsize=figsize, layout="constrained")
            else:
                from matplotlib.figure import Figure
                figure = Figure(figsize=figsize, layout="constrained")
            ax = figure.add_subplot()
        self.ax = ax
        self.figure = ax.figure
        self._artists = {}
        self._rank = {}

    # Backend hooks -----------------------------------------------------
    def _set_axes(self, axes: AxesSpec):
        ax, st = self.ax, axes.style
        # nonpositive="mask" turns values that a log axis cannot show into
        # gaps, like NaN; matplotlib's default would drop the line to the
        # bottom edge instead.
        for setter, log in ((ax.set_xscale, axes.x_log), (ax.set_yscale, axes.y_log)):
            if log:
                setter("log", nonpositive="mask")
            else:
                setter("linear")
        for label, text, style in ((ax.xaxis.label, axes.x_label, st.axis_label),
                                   (ax.yaxis.label, axes.y_label, st.axis_label),
                                   (ax.title, axes.title, st.title)):
            label.set_text(text)
            _apply_text_style(label, style)
        for limits, setter, log, axis in ((axes.x_limits, ax.set_xlim, axes.x_log, "x"),
                                          (axes.y_limits, ax.set_ylim, axes.y_log, "y")):
            if limits is None:
                ax.autoscale(axis=axis)
            else:
                setter(_safe_limits(limits, log))

        ax.set_facecolor(st.background or "none")
        if self._owns_figure:
            self.figure.set_facecolor(st.figure_background or "none")
        for spine in ax.spines.values():
            spine.set_edgecolor(st.frame_color or "none")
            spine.set_linewidth(st.frame_width_pt)
        ax.tick_params(axis="both", which="both", color=st.tick_color or "none",
                       direction=st.tick_direction, width=st.tick_width_pt,
                       labelcolor=st.tick_label.color or "none", labelsize=st.tick_label.font.size_pt,
                       labelfontfamily=_families(st.tick_label.font.family))
        ax.tick_params(axis="both", which="major", length=st.tick_length_pt)
        ax.tick_params(axis="both", which="minor", length=0.6 * st.tick_length_pt)
        ax.set_axisbelow(True)
        for which, grid in (("major", st.grid_major), ("minor", st.grid_minor)):
            if grid is None:
                ax.grid(False, which=which)
            else:
                if which == "minor":
                    ax.minorticks_on()
                ax.grid(True, which=which, color=grid.color, linewidth=grid.width_pt, alpha=grid.alpha,
                        linestyle=_mpl_dashes(grid.dash, grid.width_pt))

    def _add(self, item: Item):
        if isinstance(item, Line):
            (artist,) = self.ax.plot([], [])
        elif isinstance(item, Markers):
            (artist,) = self.ax.plot([], [], linestyle="none")
        elif isinstance(item, Text):
            artist = self.ax.text(0.0, 0.0, "", rotation_mode="anchor", transform_rotates_text=True)
        else:
            raise TypeError("MatplotlibRenderer cannot draw {0}.".format(type(item).__name__))
        self._artists[item.id] = artist
        self._rank.setdefault(item.id, len(self._rank))
        self._apply(artist, item)

    def _update(self, old: Item, new: Item):
        if type(old) is not type(new):
            super()._update(old, new)
            return
        self._apply(self._artists[new.id], new)

    def _remove(self, item: Item):
        artist = self._artists.pop(item.id, None)
        self._rank.pop(item.id, None)
        if artist is not None:
            artist.remove()

    def _reorder(self, order):
        self._rank = {item_id: i for i, item_id in enumerate(order)}
        for item_id, artist in self._artists.items():
            artist.set_zorder(self._drawn[item_id].z_order + self._rank[item_id] * _RANK_STEP)

    def _set_legend(self, entries, style):
        old = self.ax.get_legend()
        if old is not None:
            old.remove()
        if style is None or not style.visible or not entries:
            return
        # A tuple of artists is drawn as one overlaid sample (HandlerTuple)
        handles = [tuple(self._artists[i.id] for i in items) if len(items) > 1 else self._artists[items[0].id]
                   for _, items in entries]
        labels = [text for text, _ in entries]
        kwargs = dict(loc=style.location)
        if style.location == "outside right":
            kwargs = dict(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0.0)
        legend = self.ax.legend(handles, labels, prop=_font(style.text.font),
                                labelcolor=style.text.color or "none",
                                frameon=style.background is not None or style.frame_color is not None,
                                facecolor=style.background or "none",
                                edgecolor=style.frame_color or "none", framealpha=1.0, **kwargs)
        legend.set_zorder(1e6)

    def _finish(self, report: SyncReport):
        axes = self._axes
        if axes is not None and (axes.x_limits is None or axes.y_limits is None):
            # set_data does not update matplotlib's data limits by itself
            self.ax.relim(visible_only=True)
            self.ax.autoscale_view(scalex=axes.x_limits is None, scaley=axes.y_limits is None)
        if report.changed and self.figure.canvas is not None:
            self.figure.canvas.draw_idle()

    # Applying item properties -------------------------------------------
    def _apply(self, artist, item: Item):
        """Copy every property of an item onto its artist."""
        artist.set_zorder(item.z_order + self._rank.get(item.id, 0) * _RANK_STEP)
        s = item.style
        if isinstance(item, Line):
            artist.set_data(item.x, item.y)
            artist.set_color(s.color or "none")
            artist.set_alpha(s.alpha)
            artist.set_linewidth(s.width_pt)
            artist.set_linestyle(_mpl_dashes(s.dash, s.width_pt))
            artist.set_solid_capstyle(_CAPS[s.cap])
            artist.set_dash_capstyle(_CAPS[s.cap])
            artist.set_solid_joinstyle(s.join)
            artist.set_dash_joinstyle(s.join)
            if s.casing_color is not None and s.casing_width_pt > 0.0:
                artist.set_path_effects([
                    patheffects.Stroke(linewidth=s.width_pt + 2.0 * s.casing_width_pt,
                                       foreground=s.casing_color),
                    patheffects.Normal()])
            else:
                artist.set_path_effects([])
            artist.set_visible(item.visible)
        elif isinstance(item, Markers):
            artist.set_data(item.x, item.y)
            artist.set_marker(s.shape)
            artist.set_markersize(s.size_pt)
            artist.set_markerfacecolor(s.face_color or "none")
            artist.set_markeredgecolor(s.edge_color or "none")
            artist.set_markeredgewidth(s.edge_width_pt)
            artist.set_alpha(s.alpha)
            artist.set_visible(item.visible)
        elif isinstance(item, Text):
            artist.set_position((item.x, item.y))
            artist.set_text(item.text)
            _apply_text_style(artist, s)
            artist.set_horizontalalignment(s.h_align)
            artist.set_verticalalignment(_V_ALIGN[s.v_align])
            # With transform_rotates_text, matplotlib interprets the rotation
            # as an angle in data coordinates and converts it to a screen
            # angle at every draw, so labels stay aligned after zooming,
            # resizing and on log axes.
            if item.direction is None:
                artist.set_rotation(0.0)
            else:
                dx, dy = item.direction
                artist.set_rotation(_upright(math.degrees(math.atan2(dy, dx))))
            artist.set_visible(item.visible and math.isfinite(item.x) and math.isfinite(item.y))

    # Read back ---------------------------------------------------------
    def backend_object(self, item_id):
        return self._artists[item_id]

    def describe_item(self, item_id: str) -> dict:
        artist = self._artists[item_id]   # KeyError for unknown ids, as required
        item = self._drawn[item_id]
        out = {"visible": bool(artist.get_visible())}
        if isinstance(item, Line):
            stroke = _stroke_effect(artist)
            offset, seq = getattr(artist, "_dash_pattern", (0.0, None))
            width = artist.get_linewidth()
            out.update(kind="line", color=_hex_or_none(artist.get_color()),
                       alpha=1.0 if artist.get_alpha() is None else artist.get_alpha(),
                       width_pt=width, dash_pt=tuple(seq) if seq else (),
                       cap=_CAPS_BACK[artist.get_solid_capstyle()], join=artist.get_solid_joinstyle(),
                       casing_color=_hex_or_none(stroke._gc["foreground"]) if stroke else None,
                       casing_width_pt=(stroke._gc["linewidth"] - width) / 2.0 if stroke else 0.0,
                       n_points=self._n_drawable(artist))
        elif isinstance(item, Markers):
            shape = artist.get_marker()
            out.update(kind="markers", shape=shape, size_pt=artist.get_markersize(),
                       face_color=None if shape in ("x", "+") else _hex_or_none(artist.get_markerfacecolor()),
                       edge_color=_hex_or_none(artist.get_markeredgecolor()),
                       edge_width_pt=artist.get_markeredgewidth(),
                       alpha=1.0 if artist.get_alpha() is None else artist.get_alpha(),
                       n_points=self._n_drawable(artist))
        elif isinstance(item, Text):
            stroke = _stroke_effect(artist)
            weight = artist.get_fontweight()
            if not isinstance(weight, str):
                weight = "bold" if weight >= 600 else "normal"
            angle = artist.get_rotation() if out["visible"] else 0.0
            angle = (angle + 180.0) % 360.0 - 180.0
            out.update(kind="text", text=artist.get_text(), font_family=tuple(artist.get_fontfamily()),
                       font_size_pt=artist.get_fontsize(), font_weight=weight,
                       font_style=artist.get_fontstyle(), color=_hex_or_none(artist.get_color()),
                       alpha=1.0 if artist.get_alpha() is None else artist.get_alpha(),
                       h_align=artist.get_horizontalalignment(), v_align=artist.get_verticalalignment(),
                       halo_color=_hex_or_none(stroke._gc["foreground"]) if stroke else None,
                       halo_width_pt=stroke._gc["linewidth"] / 2.0 if stroke else 0.0,
                       screen_angle_deg=angle)
        if out["visible"]:
            out["draw_rank"] = self._draw_rank(item_id)
        return out

    def describe_axes(self) -> dict:
        ax = self.ax
        spine = ax.spines["left"]
        tick = ax.xaxis.get_major_ticks()[0]
        gridline = tick.gridline
        legend = ax.get_legend()
        return dict(
            x_label=ax.get_xlabel(), y_label=ax.get_ylabel(),
            x_log=ax.get_xscale() == "log", y_log=ax.get_yscale() == "log",
            x_limits=tuple(ax.get_xlim()), y_limits=tuple(ax.get_ylim()), title=ax.get_title(),
            background=_hex_or_none(ax.get_facecolor()),
            frame_color=_hex_or_none(spine.get_edgecolor()), frame_width_pt=spine.get_linewidth(),
            tick_direction=getattr(tick, "_tickdir", None), tick_color=_hex_or_none(tick.tick1line.get_color()),
            grid_color=_hex_or_none(gridline.get_color()) if gridline.get_visible() else None,
            legend=[t.get_text() for t in legend.get_texts()] if legend is not None else [],
        )

    def _n_drawable(self, artist) -> int:
        x = np.asarray(artist.get_xdata(), dtype=float)
        y = np.asarray(artist.get_ydata(), dtype=float)
        ok = np.isfinite(x) & np.isfinite(y)
        if self.ax.get_xscale() == "log":
            ok &= x > 0.0
        if self.ax.get_yscale() == "log":
            ok &= y > 0.0
        return int(np.sum(ok))

    def _draw_rank(self, item_id) -> int:
        """Position among our visible artists in matplotlib's own drawing order."""
        children = self.ax.get_children()
        ours = {id(a): i for i, a in self._artists.items() if a.get_visible()}
        drawn = sorted((c for c in children if id(c) in ours), key=lambda a: a.get_zorder())
        ids = [ours[id(a)] for a in drawn]
        return ids.index(item_id)

    # Output ------------------------------------------------------------
    def save(self, path, **kwargs):
        kwargs.setdefault("metadata", {"Software": None} if str(path).endswith(".png") else None)
        if kwargs["metadata"] is None:
            kwargs.pop("metadata")
        self.figure.savefig(path, **kwargs)

    def show(self):
        import matplotlib.pyplot as plt
        plt.show()


def _safe_limits(limits, log):
    """A log axis cannot start at zero or below; fall back to a 1000:1 range."""
    lo, hi = limits
    if log and not lo > 0.0:
        hi = hi if hi > 0.0 else 10.0
        lo = hi * 1e-3
    return lo, hi


def _upright(angle_deg: float) -> float:
    """Keep text readable: never upside down."""
    angle_deg = (angle_deg + 180.0) % 360.0 - 180.0
    if angle_deg > 90.0:
        angle_deg -= 180.0
    elif angle_deg < -90.0:
        angle_deg += 180.0
    return angle_deg
