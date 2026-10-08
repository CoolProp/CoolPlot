# -*- coding: utf-8 -*-
"""Matplotlib backend (requires matplotlib 3.8 or later).

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
  halo colour drawn underneath the normal rendering. The stroke inherits
  the dash pattern and alpha of the line, as docs/backends.md requires.
* Stacking: the axes with their grid and ticks sit at z order 0.5
  (``set_axisbelow``), items at 1 + z_order plus a tiny fraction per
  position, so the scene order breaks ties, and the frame and legend above
  everything.
* The diamond marker "D" is drawn sqrt(2) times wider than its nominal
  size by matplotlib; it is scaled down so its bounding box is size_pt.
* Read-back uses a few private attributes where matplotlib has no public
  getter; each one is marked "private:".
"""
from __future__ import annotations

import math

import numpy as np
import matplotlib
from matplotlib import patheffects
from matplotlib.colors import to_hex
from matplotlib.font_manager import FontProperties
from matplotlib.markers import MarkerStyle as _MplMarker

from ..scene import AxesSpec, Item, Line, Markers, Text
from ..style import dash_pattern_pt
from .base import Renderer, SyncReport

_CAPS = {"butt": "butt", "round": "round", "square": "projecting"}
_CAPS_BACK = {v: k for k, v in _CAPS.items()}
_RANK_STEP = 1e-9     # z order tie breaker, small against any real z_order difference
_ITEM_BASE = 1.0      # items start above the grid (0.5)
_DECORATION_Z = 1e5   # the frame above all items
_LEGEND_Z = 1e6
_GENERIC = {"sans-serif", "serif", "monospace", "cursive", "fantasy"}
_installed = None


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


def _marker_scale(shape: str) -> float:
    """Bounding-box width of a matplotlib marker of markersize 1, in points."""
    marker = _MplMarker(shape)
    return marker.get_path().get_extents(marker.get_transform()).width


def _stroke_effect(artist):
    for effect in artist.get_path_effects():
        if isinstance(effect, patheffects.Stroke):
            return effect
    return None


def _draws_itself(artist) -> bool:
    """True if the artist's own stroke is drawn (no path effects, or one of them is Normal)."""
    effects = artist.get_path_effects()
    return not effects or any(isinstance(e, (patheffects.Normal, patheffects.withStroke)) for e in effects)


def _font_description(prefix, text, full=True) -> dict:
    out = {prefix + "_font_family": tuple(text.get_fontfamily()),
           prefix + "_font_size_pt": text.get_fontsize(), prefix + "_color": _hex_or_none(text.get_color())}
    if full:
        weight = text.get_fontweight()
        if not isinstance(weight, str):
            weight = "bold" if weight >= 600 else "normal"
        out.update({prefix + "_font_weight": weight, prefix + "_font_style": text.get_fontstyle()})
    return out


class MatplotlibRenderer(Renderer):
    """Draw a scene into a matplotlib Axes

    Parameters
    ----------
    ax : matplotlib.axes.Axes, optional
        Draw into an existing Axes, for example one embedded in a GUI or
        one panel of a larger figure. The figure then stays under your
        control: its background and layout are not touched, so leave room
        for a legend placed "outside right".
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
        self.owns_canvas = ax is None
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
        # The frame goes above all items. Matplotlib draws grid lines as part
        # of the axis artists, so the axes (with their ticks) stay below the
        # items to keep the grid there.
        for spine in ax.spines.values():
            spine.set_zorder(_DECORATION_Z)
        ax.set_axisbelow(True)

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
        if self.owns_canvas:
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
        for which, grid in (("major", st.grid_major), ("minor", st.grid_minor)):
            if grid is None or grid.color is None:
                ax.grid(False, which=which)   # a grid without paint is no grid
                continue
            if which == "minor":
                ax.minorticks_on()
            ax.grid(True, which=which, color=grid.color, linewidth=grid.width_pt, alpha=grid.alpha,
                    linestyle=_mpl_dashes(grid.dash, grid.width_pt),
                    solid_capstyle=_CAPS[grid.cap], dash_capstyle=_CAPS[grid.cap],
                    solid_joinstyle=grid.join, dash_joinstyle=grid.join)

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
            # A new artist replaces the old one in the same place in the stack
            rank = self._rank.get(old.id)
            super()._update(old, new)
            if rank is not None:
                self._rank[new.id] = rank
                self._artists[new.id].set_zorder(_ITEM_BASE + new.z_order + rank * _RANK_STEP)
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
            artist.set_zorder(_ITEM_BASE + self._drawn[item_id].z_order + self._rank[item_id] * _RANK_STEP)

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
        legend.set_zorder(_LEGEND_Z)

    def _finish(self, report: SyncReport):
        if not report.changed:
            return   # an unchanged scene must not touch the backend
        axes = self._axes
        if axes is not None and (axes.x_limits is None or axes.y_limits is None):
            # set_data does not update matplotlib's data limits by itself
            self.ax.relim(visible_only=True)
            self.ax.autoscale_view(scalex=axes.x_limits is None, scaley=axes.y_limits is None)
        if self.figure.canvas is not None:
            self.figure.canvas.draw_idle()

    # Applying item properties -------------------------------------------
    def _apply(self, artist, item: Item):
        """Copy every property of an item onto its artist."""
        artist.set_zorder(_ITEM_BASE + item.z_order + self._rank.get(item.id, 0) * _RANK_STEP)
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
            artist.set_markersize(s.size_pt / _marker_scale(s.shape))
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
            artist.set_verticalalignment(s.v_align)
            # With transform_rotates_text, matplotlib interprets the rotation
            # as an angle in data coordinates and converts it to a screen
            # angle at every draw, so labels stay aligned after zooming,
            # resizing and on log axes. Keeping the data angle within
            # +-90 degrees keeps the screen angle upright as well, because
            # the axes are never inverted.
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
        alpha = 1.0 if artist.get_alpha() is None else artist.get_alpha()
        if isinstance(item, Line):
            stroke = _stroke_effect(artist)
            offset, seq = getattr(artist, "_dash_pattern", (0.0, None))   # private: final dashes in points
            dash = tuple(seq) if seq else ()
            width = artist.get_linewidth()
            out.update(kind="line", color=_hex_or_none(artist.get_color()) if _draws_itself(artist) else None,
                       alpha=alpha, width_pt=width, dash_pt=dash,
                       cap=_CAPS_BACK[artist.get_solid_capstyle()], join=artist.get_solid_joinstyle(),
                       n_points=self._n_drawable(artist))
            if stroke is not None:
                gc = stroke._gc   # private: the overrides the Stroke effect applies
                out.update(casing_color=_hex_or_none(gc["foreground"]),
                           casing_width_pt=(gc["linewidth"] - width) / 2.0,
                           casing_dash_pt=dash if "dashes" not in gc else tuple(gc["dashes"][1] or ()),
                           casing_alpha=gc.get("alpha", alpha))
            else:
                out.update(casing_color=None, casing_width_pt=0.0)
        elif isinstance(item, Markers):
            shape = artist.get_marker()
            out.update(kind="markers", shape=shape,
                       size_pt=artist.get_markersize() * _marker_scale(shape),
                       face_color=None if shape in ("x", "+") else _hex_or_none(artist.get_markerfacecolor()),
                       edge_color=_hex_or_none(artist.get_markeredgecolor()),
                       edge_width_pt=artist.get_markeredgewidth(), alpha=alpha,
                       n_points=self._n_drawable(artist))
        elif isinstance(item, Text):
            stroke = _stroke_effect(artist)
            weight = artist.get_fontweight()
            if not isinstance(weight, str):
                weight = "bold" if weight >= 600 else "normal"
            # get_rotation applies the data-to-screen transform because of
            # transform_rotates_text, so this is the angle on screen.
            angle = artist.get_rotation() if out["visible"] else 0.0
            angle = (angle + 180.0) % 360.0 - 180.0
            out.update(kind="text", text=artist.get_text(), font_family=tuple(artist.get_fontfamily()),
                       font_size_pt=artist.get_fontsize(), font_weight=weight,
                       font_style=artist.get_fontstyle(), color=_hex_or_none(artist.get_color()),
                       alpha=alpha, h_align=artist.get_horizontalalignment(),
                       v_align=artist.get_verticalalignment(),
                       halo_color=_hex_or_none(stroke._gc["foreground"]) if stroke else None,   # private
                       halo_width_pt=stroke._gc["linewidth"] / 2.0 if stroke else 0.0,
                       screen_angle_deg=angle)
        if out["visible"]:
            out["draw_rank"] = self._draw_rank(item_id)
        return out

    def describe_axes(self) -> dict:
        ax = self.ax
        spine = ax.spines["left"]
        tick = ax.xaxis.get_major_ticks()[0]
        x_lim, y_lim = tuple(ax.get_xlim()), tuple(ax.get_ylim())
        gridline = tick.gridline
        grid_on = gridline.get_visible()
        out = dict(
            x_label=ax.get_xlabel(), y_label=ax.get_ylabel(),
            x_log=ax.get_xscale() == "log", y_log=ax.get_yscale() == "log",
            x_limits=x_lim, y_limits=y_lim, title=ax.get_title(),
            background=_hex_or_none(ax.get_facecolor()),
            frame_color=_hex_or_none(spine.get_edgecolor()), frame_width_pt=spine.get_linewidth(),
            tick_direction=getattr(tick, "_tickdir", None),   # private: no public getter
            tick_color=_hex_or_none(tick.tick1line.get_color()),
            tick_length_pt=tick.tick1line.get_markersize(), tick_width_pt=tick.tick1line.get_markeredgewidth(),
            grid_color=_hex_or_none(gridline.get_color()) if grid_on else None,
            grid_minor_color=self._minor_grid_color(),
            plot_size_pt=(ax.bbox.width * 72.0 / self.figure.dpi, ax.bbox.height * 72.0 / self.figure.dpi),
            legend=self._legend_description(),
        )
        if grid_on:
            seq = getattr(gridline, "_dash_pattern", (0.0, None))[1]   # private: final dashes
            items_z = [a.get_zorder() for a in self._artists.values()]
            out.update(grid_width_pt=gridline.get_linewidth(), grid_dash_pt=tuple(seq) if seq else (),
                       # the axis artist draws the grid, so its z order counts
                       grid_below_items=not items_z or ax.xaxis.get_zorder() < min(items_z),
                       grid_lines=self._count_in_view(ax.xaxis.get_majorticklocs(), x_lim)
                       + self._count_in_view(ax.yaxis.get_majorticklocs(), y_lim))
        location = self._legend_location()
        if location is not None:
            out["legend_location"] = location
        if self.owns_canvas:
            out["figure_background"] = _hex_or_none(self.figure.get_facecolor())
        out.update(_font_description("x_label", ax.xaxis.label))
        out.update(_font_description("y_label", ax.yaxis.label))
        out.update(_font_description("title", ax.title))
        out.update(_font_description("tick_label", tick.label1, full=False))
        return out

    # Read-back helpers -------------------------------------------------
    @staticmethod
    def _count_in_view(locations, limits):
        lo, hi = min(limits), max(limits)
        return sum(1 for v in locations if lo <= v <= hi)

    def _minor_grid_color(self):
        ticks = self.ax.xaxis.get_minor_ticks()
        if not ticks or not ticks[0].gridline.get_visible():
            return None
        return _hex_or_none(ticks[0].gridline.get_color())

    def _legend_description(self):
        legend = self.ax.get_legend()
        if legend is None:
            return []
        rows = []
        # private: the packed rows of the legend; each row holds a drawing
        # area with the sample artists and a text area with the label.
        for row in legend._legend_handle_box.get_children()[0].get_children():
            area, text_area = row.get_children()
            colors = set()
            for sample in area.get_children():
                if sample.get_linestyle() not in ("None", "none", "", " "):
                    colors.add(_hex_or_none(sample.get_color()))
                if sample.get_marker() not in ("None", "none", "", " ", None):
                    colors.add(_hex_or_none(sample.get_markeredgecolor())
                               or _hex_or_none(sample.get_markerfacecolor()))
            text = text_area.get_children()[0].get_text()
            rows.append((text, tuple(sorted(colors - {None}))))
        return rows

    def _legend_location(self):
        """Where the legend actually is, classified from its bounding box."""
        legend = self.ax.get_legend()
        if legend is None:
            return None
        renderer = self.figure._get_renderer()   # private: works without a GUI canvas
        box = legend.get_window_extent(renderer)
        plot = self.ax.get_window_extent(renderer)
        if box.x0 >= plot.x1 - 0.5:
            return "outside right"
        vertical = "upper" if (box.y0 + box.y1) / 2.0 > (plot.y0 + plot.y1) / 2.0 else "lower"
        horizontal = "right" if (box.x0 + box.x1) / 2.0 > (plot.x0 + plot.x1) / 2.0 else "left"
        return vertical + " " + horizontal

    def _n_drawable(self, artist) -> int:
        """Points that survive matplotlib's own transform (NaN and masked log values drop out)."""
        xy = np.column_stack([np.asarray(artist.get_xdata(), dtype=float),
                              np.asarray(artist.get_ydata(), dtype=float)])
        if not len(xy):
            return 0
        with np.errstate(divide="ignore", invalid="ignore"):
            screen = artist.get_transform().transform(xy)
        return int(np.sum(np.all(np.isfinite(screen), axis=1)))

    def _draw_rank(self, item_id) -> int:
        """Position among our visible artists in matplotlib's own drawing order."""
        children = self.ax.get_children()
        ours = {id(a): i for i, a in self._artists.items() if a.get_visible()}
        drawn = sorted((c for c in children if id(c) in ours), key=lambda a: a.get_zorder())
        return [ours[id(a)] for a in drawn].index(item_id)

    # Output ------------------------------------------------------------
    def save(self, path, **kwargs):
        if str(path).endswith(".png"):
            kwargs.setdefault("metadata", {"Software": None})   # no version string, deterministic
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
    elif angle_deg <= -90.0:
        angle_deg += 180.0
    return angle_deg
