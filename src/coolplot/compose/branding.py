# -*- coding: utf-8 -*-
"""The badge and the watermark of a chart, from its branding settings.

:func:`branding` turns :class:`coolplot.spec.settings.BrandingSettings`
into the :class:`coolplot.scene.Badge` and :class:`coolplot.scene.Watermark`
of the axes, sized in points for the plot area the labels are laid out
for. It also returns the badge's box in the label layout's coordinates,
so that isoline labels keep clear of it.

With ``location="auto"`` the badge goes into the corner where its box
covers the fewest points of the drawn lines; a corner taken by a legend
inside the plot area is not used. Ties go to the first corner of
:data:`AUTO_ORDER`.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional, Sequence, Tuple

import numpy as np

from ..core.images import load_picture
from ..scene import Badge, Watermark
from ..spec.diagram import DiagramSpec
from ..style.theme import Theme
from ..style.values import Font, TextStyle
from .layout import Box, Frame

#: Corners tried by "auto", best first when several are equally free.
AUTO_ORDER = ("lower right", "upper left", "upper right", "lower left")
#: The watermark is never taller than this fraction of the plot area.
WATERMARK_MAX_HEIGHT = 0.8


def branding(spec: DiagramSpec, theme: Theme, frame: Frame,
             drawn: Sequence[Tuple[np.ndarray, np.ndarray]] = (),
             sources: Sequence[str] = ()) -> Tuple[Optional[Badge], Optional[Watermark], Optional[Box]]:
    """(badge, watermark, badge box) for the chart; None for what the settings do not ask for.

    ``theme`` is the theme with the page's font scale applied, ``frame``
    the plot area the labels are laid out in, and ``drawn`` the (x, y)
    display-unit lines whose points the automatic corner avoids.
    ``sources`` are the lines naming the sources of the properties and
    the versions, from :meth:`coolplot.engine.Engine.source_lines` (the
    composer does not ask CoolProp itself); the badge shows them above
    ``BrandingSettings.lines``.
    """
    settings = spec.settings.branding
    watermark = None
    if settings.watermark:
        pictures = tuple(load_picture(s) for s in settings.watermark)
        width = settings.watermark_width * frame.width_pt
        if width * pictures[0].aspect > WATERMARK_MAX_HEIGHT * frame.height_pt:
            width = WATERMARK_MAX_HEIGHT * frame.height_pt / pictures[0].aspect
        if width > 0.0:
            watermark = Watermark(picture=pictures, width_pt=width, opacity=settings.watermark_opacity)
    if not settings.has_badge:
        return None, watermark, None
    axes_style = theme.axes
    font_scale = spec.settings.page.font_scale
    text = TextStyle(font=Font(family=axes_style.tick_label.font.family, size_pt=settings.font_size_pt * font_scale),
                     color=axes_style.tick_label.color or "#000000", h_align="left", v_align="bottom")
    badge = Badge(location="lower right", logo=tuple(load_picture(s) for s in settings.logo),
                  logo_width_pt=settings.logo_width_pt, lines=tuple(sources) + settings.lines, text=text,
                  background=axes_style.background or "#ffffff", background_alpha=settings.background_alpha,
                  frame_color=axes_style.frame_color if settings.frame else None)
    if badge.empty:
        return None, watermark, None
    width, height = badge.size_pt()
    location = settings.location
    if location == "auto":
        location = _free_corner(frame, width, height, badge.inset_pt, drawn, axes_style.legend)
    badge = replace(badge, location=location)
    return badge, watermark, corner_box(frame, location, width, height, badge.inset_pt)


def corner_box(frame: Frame, location: str, width: float, height: float, inset: float) -> Box:
    """The box of a badge in the label layout's coordinates (points, y up)."""
    vertical, horizontal = location.split()
    cx = inset + 0.5 * width if horizontal == "left" else frame.width_pt - inset - 0.5 * width
    cy = inset + 0.5 * height if vertical == "lower" else frame.height_pt - inset - 0.5 * height
    return Box(cx, cy, 0.0, 0.5 * width, 0.5 * height)


def _free_corner(frame: Frame, width: float, height: float, inset: float, drawn, legend_style) -> str:
    """The corner whose badge box covers the fewest drawn points; see the module docstring."""
    taken = legend_style.location if legend_style is not None and legend_style.visible else None
    candidates = [c for c in AUTO_ORDER if c != taken] or list(AUTO_ORDER)
    if not frame.usable:
        return candidates[0]
    xs, ys = [], []
    for x, y in drawn:
        px, py = frame.to_pt(x, y)
        keep = np.isfinite(px) & np.isfinite(py)
        xs.append(px[keep])
        ys.append(py[keep])
    px = np.concatenate(xs) if xs else np.array([])
    py = np.concatenate(ys) if ys else np.array([])
    best, best_count = candidates[0], None
    for corner in candidates:
        box = corner_box(frame, corner, width, height, inset)
        inside = (np.abs(px - box.cx) <= box.half_w) & (np.abs(py - box.cy) <= box.half_h)
        count = int(np.count_nonzero(inside))
        if best_count is None or count < best_count:
            best, best_count = corner, count
    return best
