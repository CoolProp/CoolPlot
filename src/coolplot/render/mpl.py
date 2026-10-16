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
* Texts are plain text: matplotlib would otherwise read "$...$" as math
  (and with the rcParam text.usetex, all text as LaTeX), changing both the
  words and the font.
* Fonts named by file in ``Font.files`` are registered with matplotlib's
  font manager before the family is looked up. ``strict_fonts=True``
  raises instead of falling back when the first family is not available.
* PDF, PS and EPS embed their fonts as TrueType (fonttype 42), which print
  checks accept and which keeps text editable; matplotlib's default,
  Type 3, is refused by many journals. Matplotlib can only embed fonts
  with TrueType outlines that way: a font installed as CFF OpenType
  (.otf starting with "OTTO") would give a damaged file. Such a text uses
  the next TrueType family of its list in the file, with a warning, see
  :meth:`MatplotlibRenderer._truetype_fonts`.
"""
from __future__ import annotations

import contextlib
import math
import os
import warnings

import numpy as np
import matplotlib
from matplotlib import patheffects
from matplotlib.colors import to_hex
from matplotlib.font_manager import FontProperties
from matplotlib.markers import MarkerStyle as _MplMarker

from ..core.events import Click, Drag, DragEnd, DragStart, Hover, Resized, ViewChanged
from ..core.numbers import format_number
from ..scene import AxesSpec, Item, Line, Markers, Text, drawable_limits
from ..style.values import dash_pattern_pt
from .base import Renderer, SyncReport

_CAPS = {"butt": "butt", "round": "round", "square": "projecting"}
_CAPS_BACK = {v: k for k, v in _CAPS.items()}
_RANK_STEP = 1e-3     # z order step between consecutive items in the drawing order
_ITEM_BASE = 1.0      # items start above the grid (0.5)
_DECORATION_Z = 1e5   # the frame above all items
_LEGEND_Z = 1e6
_GENERIC = {"sans-serif", "serif", "monospace", "cursive", "fantasy"}
_installed = None
_registered = set()   # font files given in Font.files, registered once per process
_outlines = {}        # font file -> True if it has TrueType outlines
_substituted = set()  # (font, replacement) pairs already reported
#: File formats with embedded fonts, and the rcParam saying how they are embedded.
_FONTTYPE_RC = {"pdf": "pdf.fonttype", "ps": "ps.fonttype", "eps": "ps.fonttype"}
#: Fonts that ship with matplotlib as TrueType: the last resort for embedding.
_LAST_RESORT = "DejaVu Sans"


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


def _register_files(files):
    """Make the font files of a Font known to matplotlib."""
    global _installed
    for path in files:
        if path in _registered:
            continue
        _registered.add(path)
        if not os.path.isfile(path):
            warnings.warn("Font file {0!r} does not exist; the next family is used.".format(path), UserWarning,
                          stacklevel=4)
            continue
        from matplotlib.font_manager import fontManager
        fontManager.addfont(path)
        _installed = None   # look again which families exist


def _resolve(font, strict: bool = False):
    """The families of a Font that matplotlib can use, in order."""
    _register_files(font.files)
    families = _families(font.family)
    wanted = font.family[0]
    if strict and wanted.lower() not in _GENERIC and families[0].lower() != wanted.lower():
        raise ValueError("Font {0!r} is not available and strict_fonts is on. Install it, or name its file "
                         "in Font(files=...).".format(wanted))
    return families


def _plain_text(text):
    """Draw the characters as given: no "$...$" math, no LaTeX."""
    text.set_parse_math(False)
    text.set_usetex(False)


def _font(font, strict: bool = False) -> FontProperties:
    return FontProperties(family=_resolve(font, strict), size=font.size_pt, weight=font.weight,
                          style=font.style)


def _apply_text_style(text, style, strict: bool = False):
    _plain_text(text)
    text.set_fontfamily(_resolve(style.font, strict))
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


def _font_file_family(text):
    """(family name, file) of the font matplotlib uses for a text."""
    from matplotlib.font_manager import fontManager, get_font
    path = str(os.fspath(fontManager.findfont(text.get_fontproperties())))   # newer versions return a FontPath
    return get_font(path).family_name, path


def _has_truetype_outlines(path: str) -> bool:
    """True for TrueType fonts; False for CFF OpenType ("OTTO") and collections."""
    if path not in _outlines:
        with open(path, "rb") as f:
            _outlines[path] = f.read(4) in (b"\x00\x01\x00\x00", b"true")
    return _outlines[path]


def _truetype_family(families, weight, style) -> str:
    """The first family of the list whose font file has TrueType outlines."""
    from matplotlib.font_manager import fontManager
    for name in families:
        try:
            path = fontManager.findfont(FontProperties(family=[name], weight=weight, style=style),
                                        fallback_to_default=False)
        except ValueError:
            continue
        if _has_truetype_outlines(str(os.fspath(path))):
            return name
    return _LAST_RESORT


def _visible_texts(figure):
    from matplotlib.text import Text as _MplText
    return [t for t in figure.findobj(_MplText) if t.get_visible() and t.get_text().strip()]


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
    strict_fonts : bool
        Raise ValueError when the first family of a font is not available,
        instead of using the next one. Useful for print work, where a
        silently replaced font would go unnoticed.
    """

    capabilities = frozenset({"in_place_updates", "file_output", "interactive", "events"})
    default_suffix = ".png"
    text_output = False

    def __init__(self, ax=None, use_pyplot: bool = True, figsize=(8.0, 6.0), strict_fonts: bool = False):
        super().__init__()
        self.strict_fonts = bool(strict_fonts)
        self._tick_families = ["sans-serif"]   # set with the axes
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
        self._tick_families = _resolve(st.tick_label.font, self.strict_fonts)
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
            _apply_text_style(label, style, self.strict_fonts)
        for limits, setter, log, axis in ((axes.x_limits, ax.set_xlim, axes.x_log, "x"),
                                          (axes.y_limits, ax.set_ylim, axes.y_log, "y")):
            if limits is None:
                ax.autoscale(axis=axis)
            else:
                setter(_safe_limits(limits, log))

        for axis, log in ((ax.xaxis, axes.x_log), (ax.yaxis, axes.y_log)):
            _central_tick_format(axis, log, axes.tick_digits)

        ax.set_facecolor(st.background or "none")
        if self.owns_canvas:
            self.figure.set_facecolor(st.figure_background or "none")
        for spine in ax.spines.values():
            spine.set_edgecolor(st.frame_color or "none")
            spine.set_linewidth(st.frame_width_pt)
        ax.tick_params(axis="both", which="both", color=st.tick_color or "none",
                       direction=st.tick_direction, width=st.tick_width_pt,
                       labelcolor=st.tick_label.color or "none", labelsize=st.tick_label.font.size_pt,
                       labelfontfamily=self._tick_families)
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
                self._artists[new.id].set_zorder(_ITEM_BASE + rank * _RANK_STEP)
            return
        self._apply(self._artists[new.id], new)

    def _remove(self, item: Item):
        artist = self._artists.pop(item.id, None)
        self._rank.pop(item.id, None)
        if artist is not None:
            artist.remove()

    def _reorder(self, order):
        # matplotlib z orders come from the position in the drawing order,
        # not from the scene's z_order values themselves: those can be huge
        # and would then lift items above the frame and the legend.
        self._rank = {item_id: i for i, item_id in enumerate(order)}
        for item_id, artist in self._artists.items():
            artist.set_zorder(_ITEM_BASE + self._rank[item_id] * _RANK_STEP)

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
        legend = self.ax.legend(handles, labels, prop=_font(style.text.font, self.strict_fonts),
                                labelcolor=style.text.color or "none",
                                frameon=style.background is not None or style.frame_color is not None,
                                facecolor=style.background or "none",
                                edgecolor=style.frame_color or "none", framealpha=1.0, **kwargs)
        legend.set_zorder(_LEGEND_Z)
        for text in legend.get_texts():
            _plain_text(text)

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
        artist.set_zorder(_ITEM_BASE + self._rank.get(item.id, len(self._rank)) * _RANK_STEP)
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
            # The offset is a shift in points after the data transform; it
            # does not change the angle computed by transform_rotates_text.
            from matplotlib.transforms import ScaledTranslation
            dx, dy = item.offset_pt
            transform = self.ax.transData
            if dx or dy:
                transform = transform + ScaledTranslation(dx / 72.0, dy / 72.0, self.figure.dpi_scale_trans)
            artist.set_transform(transform)
            artist.set_clip_on(item.clip)
            if item.clip:
                artist.set_clip_path(self.ax.patch)
            _apply_text_style(artist, s, self.strict_fonts)
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

    # Events ------------------------------------------------------------
    #: Points within this distance (in points) of a marker or line hit it.
    PICK_RADIUS_PT = 5.0

    #: A press that moves less than this (logical pixels) is still a click.
    CLICK_SLOP_PX = 4.0

    def _start_events(self):
        if getattr(self, "_event_ids", None) is not None:
            return
        canvas = self.figure.canvas
        self._press = None      # dict describing the pressed button, see _on_press
        self._buttons_reported = False
        self._last_view = self._view()
        # The view is reported when the figure is drawn, not on every limit
        # change: a zoom changes x and y one after the other, and reporting
        # both changes would redraw the diagram twice, once half zoomed.
        self._event_ids = [canvas.mpl_connect(name, handler) for name, handler in (
            ("motion_notify_event", self._on_motion), ("button_press_event", self._on_press),
            ("button_release_event", self._on_release), ("resize_event", self._on_resize),
            ("draw_event", self._on_draw))]

    def _toolbar_busy(self) -> bool:
        """True while the zoom or pan tool of the window is active."""
        toolbar = getattr(self.figure.canvas, "toolbar", None)
        return bool(toolbar is not None and getattr(toolbar, "mode", ""))

    def _hit(self, mouse_event):
        """(item_id, index) of the topmost visible marker or line under the pointer."""
        candidates = []
        for item_id, artist in self._artists.items():
            item = self._drawn.get(item_id)
            if not artist.get_visible() or isinstance(item, Text):
                continue
            artist.set_pickradius(self.PICK_RADIUS_PT)
            hit, details = artist.contains(mouse_event)
            if hit:
                indices = list(details.get("ind", []))
                candidates.append((artist.get_zorder(), item_id, int(indices[0]) if indices else None))
        if not candidates:
            return None, None
        _, item_id, index = max(candidates)
        return item_id, index

    def _data(self, mouse_event):
        """The pointer in data units; finite anywhere on the canvas, also outside the axes."""
        x, y = self.ax.transData.inverted().transform((mouse_event.x, mouse_event.y))
        return float(x), float(y)

    def _on_motion(self, event):
        press = self._press
        buttons = getattr(event, "buttons", None) or frozenset()
        if buttons:
            self._buttons_reported = True
        if press is not None and self._buttons_reported and not buttons:
            # No button is held any more, but the release was lost (outside
            # the window): end the press here. Only for canvases that report
            # held buttons at all; others send an empty set every time.
            self._end_press(*press["last"])
            press = None
        if press is None:
            if buttons and self._toolbar_busy():
                return   # panning or zooming with the toolbar
            if event.inaxes is self.ax:
                x, y = self._data(event)
                item_id, index = self._hit(event)
                self._emit(Hover(x, y, item_id, index))
            return
        x, y = self._data(event)
        press["last"] = (x, y)
        ratio = getattr(self.figure.canvas, "device_pixel_ratio", 1.0) or 1.0   # event pixels are physical
        slop = self.CLICK_SLOP_PX * ratio
        if not press["moved"] and math.hypot(event.x - press["x_px"], event.y - press["y_px"]) < slop:
            return   # jitter of a click
        press["moved"] = True
        if press["draggable"]:
            if not press["dragging"]:
                press["dragging"] = True
                self._emit(DragStart(press["item_id"], press["index"], x, y))
            self._emit(Drag(press["item_id"], press["index"], x, y))

    def _on_press(self, event):
        if event.inaxes is not self.ax or self._toolbar_busy():
            return
        item_id, index = self._hit(event)
        button = int(event.button or 1)
        # Only markers can be dragged, with the left button: their points are
        # the states of a process
        draggable = isinstance(self._drawn.get(item_id), Markers) and index is not None and button == 1
        self._press = dict(item_id=item_id, index=index, button=button, draggable=draggable,
                           x_px=event.x, y_px=event.y, last=self._data(event), moved=False, dragging=False)

    def _on_release(self, event):
        if self._press is not None:
            self._end_press(*self._data(event))

    def _end_press(self, x, y):
        press, self._press = self._press, None
        if press["dragging"]:
            self._emit(DragEnd(press["item_id"], press["index"], x, y))
        elif not press["moved"]:
            self._emit(Click(x, y, press["item_id"], press["index"], press["button"]))

    def _on_resize(self, event):
        size = self.plot_size_pt()
        self._emit(Resized(*size))

    def _view(self):
        return tuple(float(v) for v in self.ax.get_xlim()), tuple(float(v) for v in self.ax.get_ylim())

    def _on_draw(self, _event=None):
        if self._syncing:
            return
        view = self._view()
        if view != self._last_view:
            self._last_view = view
            self._emit(ViewChanged(*view))

    def sync(self, scene):
        report = super().sync(scene)
        if report.axes_changed and getattr(self, "_event_ids", None) is not None:
            self._last_view = self._view()   # the view sync set is not the user's
        return report

    # Simulated input, for tests and the conformance kit
    def simulate_pointer(self, kind: str, x: float, y: float, button: int = 1):
        """Feed a pointer event at (x, y) in data units: "move", "press" or "release"."""
        from matplotlib.backend_bases import MouseEvent
        self._start_events()
        if self.figure.stale:
            self.figure.draw_without_rendering()
        x_px, y_px = self.ax.transData.transform((x, y))
        name = {"move": "motion_notify_event", "press": "button_press_event",
                "release": "button_release_event"}[kind]
        if kind == "move":
            held = [self._press["button"]] if self._press is not None else None
            event = MouseEvent(name, self.figure.canvas, x_px, y_px, buttons=held)
        else:
            event = MouseEvent(name, self.figure.canvas, x_px, y_px, button=button)
        self.figure.canvas.callbacks.process(name, event)

    def simulate_view(self, x_limits, y_limits):
        """Change the visible limits as the zoom or pan tool would."""
        self._start_events()
        self.ax.set_xlim(*x_limits)
        self.ax.set_ylim(*y_limits)
        self._on_draw()   # the toolbar redraws the canvas after a change

    # Read back ---------------------------------------------------------
    def backend_object(self, item_id):
        return self._artists[item_id]

    def describe_item(self, item_id: str) -> dict:
        artist = self._artists[item_id]   # KeyError for unknown ids, as required
        item = self._drawn[item_id]
        out = {"visible": bool(artist.get_visible()), "clip": bool(artist.get_clip_on())}
        alpha = 1.0 if artist.get_alpha() is None else artist.get_alpha()
        if isinstance(item, Line):
            stroke = _stroke_effect(artist)
            offset, seq = getattr(artist, "_dash_pattern", (0.0, None))   # private: final dashes in points
            dash = tuple(seq) if seq else ()
            width = artist.get_linewidth()
            # A dashed line is drawn with the dash cap and join styles
            cap = artist.get_dash_capstyle() if dash else artist.get_solid_capstyle()
            join = artist.get_dash_joinstyle() if dash else artist.get_solid_joinstyle()
            out.update(kind="line", color=_hex_or_none(artist.get_color()) if _draws_itself(artist) else None,
                       alpha=alpha, width_pt=width, dash_pt=dash, cap=_CAPS_BACK[cap], join=join,
                       n_points=self._n_drawable(artist), drawn_points=self._drawn_points(artist))
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
                       n_points=self._n_drawable(artist), drawn_points=self._drawn_points(artist),
                       connected=artist.get_linestyle() not in ("None", "none", "", " "))
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
                       font_used=_font_file_family(artist)[0],
                       font_size_pt=artist.get_fontsize(), font_weight=weight,
                       font_style=artist.get_fontstyle(), color=_hex_or_none(artist.get_color()),
                       alpha=alpha, h_align=artist.get_horizontalalignment(),
                       v_align=artist.get_verticalalignment(),
                       halo_color=_hex_or_none(stroke._gc["foreground"]) if stroke else None,   # private
                       halo_width_pt=stroke._gc["linewidth"] / 2.0 if stroke else 0.0,
                       screen_angle_deg=angle)
            # Offset: where the text transform puts the anchor, compared with
            # the plain data transform, in points
            position = artist.get_position()
            drawn = artist.get_transform().transform(position)
            plain = self.ax.transData.transform(position)
            scale = 72.0 / self.figure.dpi
            out["offset_pt"] = (float(drawn[0] - plain[0]) * scale, float(drawn[1] - plain[1]) * scale)
            fx, fy = self.ax.transAxes.inverted().transform(drawn)
            out["drawn_points"] = [(float(fx), float(fy))]
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
        out.update(self._extra_axes_description(tick, spine))
        location = self._legend_location()
        if location is not None:
            out["legend_location"] = location
        if self.owns_canvas:
            out["figure_background"] = _hex_or_none(self.figure.get_facecolor())
        out.update(_font_description("x_label", ax.xaxis.label))
        out.update(_font_description("y_label", ax.yaxis.label))
        out.update(_font_description("title", ax.title))
        out.update(_font_description("tick_label", tick.label1, full=False))
        # Tick label texts as the axis formatters write them
        for name, axis, limits in (("x", ax.xaxis, x_lim), ("y", ax.yaxis, y_lim)):
            locations = [v for v in axis.get_majorticklocs() if limits[0] <= v <= limits[1]]
            texts = axis.get_major_formatter().format_ticks(locations)
            out[name + "_tick_labels"] = [(float(v), t) for v, t in zip(locations, texts) if t]
        return out

    # Read-back helpers -------------------------------------------------
    def _drawn_points(self, artist):
        """Where the artist's points end up, as fractions of the plot area."""
        xy = np.asarray(artist.get_xydata(), dtype=float).reshape(-1, 2)
        if not len(xy):
            return []
        with np.errstate(divide="ignore", invalid="ignore"):
            screen = artist.get_transform().transform(xy)
            fractions = self.ax.transAxes.inverted().transform(screen)
        return [(float(a), float(b)) for a, b in fractions if math.isfinite(a) and math.isfinite(b)]

    def _extra_axes_description(self, x_tick, spine) -> dict:
        """y-axis ticks, all frame sides, legend style, grid per axis, stacking."""
        ax = self.ax
        out = {}
        y_tick = ax.yaxis.get_major_ticks()[0]
        out.update(y_tick_direction=getattr(y_tick, "_tickdir", None),   # private: no public getter
                   y_tick_color=_hex_or_none(y_tick.tick1line.get_color()),
                   y_tick_length_pt=y_tick.tick1line.get_markersize(),
                   y_tick_width_pt=y_tick.tick1line.get_markeredgewidth())
        color, width = spine.get_edgecolor(), spine.get_linewidth()
        out["frame_sides"] = sum(1 for sp in ax.spines.values()
                                 if sp.get_visible() and _hex_or_none(sp.get_edgecolor()) == _hex_or_none(color)
                                 and sp.get_linewidth() == width)
        items_z = [a.get_zorder() for a in self._artists.values()]
        out["items_below_frame"] = not items_z or max(items_z) < min(sp.get_zorder() for sp in ax.spines.values())
        legend = ax.get_legend()
        if legend is not None:
            out["items_below_legend"] = not items_z or max(items_z) < legend.get_zorder()
            out["legend_background"] = _hex_or_none(legend.get_frame().get_facecolor())
            texts = legend.get_texts()
            if texts:
                out.update(_font_description("legend", texts[0], full=False))
        # matplotlib creates tick objects lazily and copies the first one's
        # properties, so the first gridline of each axis speaks for all
        if x_tick.gridline.get_visible():
            out["x_grid_lines"] = self._count_in_view(ax.xaxis.get_majorticklocs(), ax.get_xlim())
        if y_tick.gridline.get_visible():
            out["y_grid_lines"] = self._count_in_view(ax.yaxis.get_majorticklocs(), ax.get_ylim())
        return out

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
    def fonts_used(self) -> dict:
        """Family name -> font file of every font the visible texts use.

        These are the fonts matplotlib really draws with, after falling back
        through each family list: the place to check that a print font is
        there.
        """
        if self.figure.stale:
            self.figure.draw_without_rendering()
        return dict(_font_file_family(text) for text in _visible_texts(self.figure))

    def plot_size_pt(self):
        """Size of the plot area; lays out the figure first if it changed."""
        if self.figure.stale:
            # Constrained layout moves the axes only when the figure is drawn
            self.figure.draw_without_rendering()
        dpi = self.figure.dpi
        return self.ax.bbox.width * 72.0 / dpi, self.ax.bbox.height * 72.0 / dpi

    def save(self, path, pdf_fonts: str = "truetype", **kwargs):
        """Write the figure to a file; the format follows the file name.

        PDF, PS and EPS embed their fonts. ``pdf_fonts="truetype"`` (the
        default) embeds TrueType fonts, as print checks and journals expect;
        a text whose font is only installed as CFF OpenType then uses the
        next TrueType family of its list, with a warning. ``"type3"`` keeps
        every font but embeds it as Type 3. PDF, SVG and PNG files carry no
        date or version, so the same scene gives the same file, and a PDF
        gets the chart title as its title. Further keyword arguments go to
        matplotlib's savefig.
        """
        fmt = (kwargs.get("format") or os.path.splitext(str(path))[1].lstrip(".") or "png").lower()
        metadata = dict(kwargs.pop("metadata", None) or {})
        rc = {}
        if fmt == "png":
            metadata.setdefault("Software", None)
        elif fmt == "pdf":
            for key in ("Creator", "Producer", "CreationDate"):
                metadata.setdefault(key, None)
            if self._axes is not None and self._axes.title:
                metadata.setdefault("Title", self._axes.title)
        elif fmt == "svg":
            metadata.setdefault("Date", None)
            rc["svg.hashsalt"] = "coolplot"   # fixed ids instead of random ones
        if metadata:
            kwargs["metadata"] = metadata
        if fmt in _FONTTYPE_RC:
            rc[_FONTTYPE_RC[fmt]] = _fonttype(pdf_fonts)
        with matplotlib.rc_context(rc), self._truetype_fonts(fmt in _FONTTYPE_RC and pdf_fonts == "truetype"):
            self.figure.savefig(path, **kwargs)

    @staticmethod
    def save_pages(path, renderers, pdf_fonts: str = "truetype", metadata: dict = None):
        """Write the figures of several renderers into one PDF, one per page.

        Fonts and metadata as for :meth:`save`; the title is that of the
        first page with a title, unless ``metadata`` gives one.
        """
        from matplotlib.backends.backend_pdf import PdfPages
        metadata = dict(metadata or {})
        for key in ("Creator", "Producer", "CreationDate"):
            metadata.setdefault(key, None)
        titles = [r._axes.title for r in renderers if r._axes is not None and r._axes.title]
        if titles:
            metadata.setdefault("Title", titles[0])
        # The font type has to hold until the file is closed: fonts are written last
        with matplotlib.rc_context({"pdf.fonttype": _fonttype(pdf_fonts)}):
            with PdfPages(path, metadata=metadata) as pages:
                for renderer in renderers:
                    with renderer._truetype_fonts(pdf_fonts == "truetype"):
                        pages.savefig(renderer.figure)

    @contextlib.contextmanager
    def _truetype_fonts(self, active: bool = True):
        """Inside: every visible text uses a font with TrueType outlines.

        A context manager (a ``with`` block): texts get a replacement
        family on entry and their own families back on exit, so the figure
        on screen is unchanged.
        """
        if not active:
            yield
            return
        self.figure.draw_without_rendering()   # creates the tick labels
        changed = []
        tick_families = None
        for text in _visible_texts(self.figure):
            _, path = _font_file_family(text)
            if _has_truetype_outlines(path):
                continue
            families = list(text.get_fontfamily())
            used = _font_file_family(text)[0]
            rest = families[families.index(used) + 1:] if used in families else families
            replacement = _truetype_family(rest, text.get_fontweight(), text.get_fontstyle())
            if (used, replacement) not in _substituted:
                _substituted.add((used, replacement))
                warnings.warn("{0} is installed here only as CFF OpenType, which matplotlib cannot embed as "
                              "TrueType (the file would be damaged); the file uses {1} instead. Install the "
                              "TrueType (.ttf) files of {0}, or save with pdf_fonts='type3'.".format(used, replacement),
                              UserWarning, stacklevel=4)
            changed.append((text, families))
            text.set_fontfamily([replacement])
            if any(text in (tick.label1, tick.label2) for axis in (self.ax.xaxis, self.ax.yaxis)
                   for tick in axis.get_major_ticks() + axis.get_minor_ticks()):
                tick_families = [replacement]
        if tick_families is not None:
            # Ticks are created again while drawing: they take the family from tick_params
            self.ax.tick_params(axis="both", which="both", labelfontfamily=tick_families)
        try:
            yield
        finally:
            for text, families in changed:
                text.set_fontfamily(families)
            if tick_families is not None:
                self.ax.tick_params(axis="both", which="both", labelfontfamily=self._tick_families)

    def show(self):
        import matplotlib.pyplot as plt
        plt.show()


def _fonttype(pdf_fonts: str) -> int:
    if pdf_fonts not in ("truetype", "type3"):
        raise ValueError("pdf_fonts is 'truetype' or 'type3', not {0!r}.".format(pdf_fonts))
    return 42 if pdf_fonts == "truetype" else 3


def _safe_limits(limits, log):
    """Limits matplotlib can draw; the common rule of :func:`coolplot.scene.drawable_limits`."""
    return drawable_limits(limits, log)


def _upright(angle_deg: float) -> float:
    """Keep text readable: never upside down."""
    angle_deg = (angle_deg + 180.0) % 360.0 - 180.0
    if angle_deg > 90.0:
        angle_deg -= 180.0
    elif angle_deg <= -90.0:
        angle_deg += 180.0
    return angle_deg


def _central_tick_format(axis, log: bool, digits: int):
    """Write tick labels with the central number format.

    matplotlib keeps deciding where ticks go and, on a log axis, which
    minor ticks get a label (none over many decades, some over few); only
    the text of each label is replaced.
    """
    from matplotlib.ticker import FuncFormatter, LogFormatterSciNotation

    axis.set_major_formatter(FuncFormatter(lambda value, pos=None: format_number(value, digits)))
    if log:
        class MinorLabels(LogFormatterSciNotation):
            def __call__(self, value, pos=None):
                return format_number(value, digits) if super().__call__(value, pos) else ""
        axis.set_minor_formatter(MinorLabels(labelOnlyBase=False))
