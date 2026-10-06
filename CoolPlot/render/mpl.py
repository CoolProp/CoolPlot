# -*- coding: utf-8 -*-
"""Matplotlib backend.

This is the only module in CoolPlot that imports matplotlib. Existing
artists are updated in place (``set_data``, ``set_color``, ...) instead of
being recreated, and the canvas is asked for a repaint with ``draw_idle``,
which matplotlib coalesces in interactive GUIs.
"""
from __future__ import annotations

import numpy as np

from ..scene import AxesSpec, Item, Line, Markers, Text
from .base import Renderer, SyncReport

_DASHES = {"solid": "-", "dashed": "--", "dotted": ":", "dashdot": "-."}


class MatplotlibRenderer(Renderer):
    """Draw a scene into a matplotlib Axes

    Parameters
    ----------
    ax : matplotlib.axes.Axes, optional
        Draw into an existing Axes, for example one embedded in a GUI or
        one panel of a larger figure. If None, a new figure is created.
    use_pyplot : bool
        Only relevant when ``ax`` is None. If True (default) the new figure
        is created through pyplot so that :meth:`show` works. Set it to
        False in servers and GUIs, where pyplot's global state is unwanted.
    figsize : tuple
        Size of a newly created figure in inches.
    """

    def __init__(self, ax=None, use_pyplot: bool = True, figsize=(8.0, 6.0)):
        super().__init__()
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

    # Backend hooks -----------------------------------------------------
    def _set_axes(self, axes: AxesSpec):
        ax = self.ax
        ax.set_xscale("log" if axes.x_log else "linear")
        ax.set_yscale("log" if axes.y_log else "linear")
        ax.set_xlabel(axes.x_label)
        ax.set_ylabel(axes.y_label)
        ax.set_title(axes.title)
        ax.grid(axes.grid)
        if axes.x_limits is None:
            ax.autoscale(axis="x")
        else:
            ax.set_xlim(axes.x_limits)
        if axes.y_limits is None:
            ax.autoscale(axis="y")
        else:
            ax.set_ylim(axes.y_limits)

    def _add(self, item: Item):
        if isinstance(item, Line):
            (artist,) = self.ax.plot(item.x, item.y)
        elif isinstance(item, Markers):
            (artist,) = self.ax.plot(item.x, item.y, linestyle="none")
        elif isinstance(item, Text):
            artist = self.ax.text(item.x, item.y, item.text, rotation_mode="anchor",
                                  transform_rotates_text=True)
        else:
            raise TypeError("MatplotlibRenderer cannot draw {0}.".format(type(item).__name__))
        self._artists[item.id] = artist
        self._apply(artist, item)

    def _update(self, old: Item, new: Item):
        if type(old) is not type(new):
            super()._update(old, new)
            return
        self._apply(self._artists[new.id], new)

    def _remove(self, item: Item):
        artist = self._artists.pop(item.id, None)
        if artist is not None:
            artist.remove()

    def _finish(self, report: SyncReport):
        if report.changed and self.figure.canvas is not None:
            self.figure.canvas.draw_idle()

    # Helpers -----------------------------------------------------------
    def _apply(self, artist, item: Item):
        """Copy all properties of an item onto its artist."""
        artist.set_visible(item.visible)
        artist.set_zorder(item.z_order)
        if isinstance(item, Line):
            s = item.style
            artist.set_data(item.x, item.y)
            artist.set_color(s.color)
            artist.set_linewidth(s.width)
            artist.set_linestyle(_DASHES.get(s.dash, s.dash))
            artist.set_alpha(s.alpha)
        elif isinstance(item, Markers):
            s = item.style
            artist.set_data(item.x, item.y)
            artist.set_marker(s.shape)
            artist.set_markersize(s.size)
            artist.set_markerfacecolor(s.face_color)
            artist.set_markeredgecolor(s.edge_color)
            artist.set_alpha(s.alpha)
        elif isinstance(item, Text):
            s = item.style
            artist.set_position((item.x, item.y))
            artist.set_text(item.text)
            artist.set_color(s.color)
            artist.set_fontsize(s.size)
            artist.set_horizontalalignment(s.h_align)
            artist.set_verticalalignment(s.v_align)
            if s.background is not None:
                artist.set_bbox(dict(facecolor=s.background, edgecolor="none", pad=0.5))
            else:
                artist.set_bbox(None)
            # With transform_rotates_text, matplotlib interprets the rotation
            # as an angle in data coordinates and converts it to a screen
            # angle at every draw, so labels stay aligned after zooming,
            # resizing and on log axes.
            if item.direction is None:
                artist.set_rotation(0.0)
            else:
                dx, dy = item.direction
                artist.set_rotation(_upright(np.degrees(np.arctan2(dy, dx))))

    # Output ------------------------------------------------------------
    def save(self, path, **kwargs):
        self.figure.savefig(path, **kwargs)

    def show(self):
        import matplotlib.pyplot as plt
        plt.show()


def _upright(angle_deg: float) -> float:
    """Keep text readable: never upside down."""
    angle_deg = (angle_deg + 180.0) % 360.0 - 180.0
    if angle_deg > 90.0:
        angle_deg -= 180.0
    elif angle_deg < -90.0:
        angle_deg += 180.0
    return angle_deg
