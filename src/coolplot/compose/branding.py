# -*- coding: utf-8 -*-
"""The badge and the watermark of a chart, from its branding settings.

:func:`branding` turns :class:`coolplot.spec.settings.BrandingSettings`
into the :class:`coolplot.scene.Badge` and :class:`coolplot.scene.Watermark`
of the axes, sized in points for the plot area the labels are laid out
for. The badge is made in the corner of the settings (the lower right
one for "auto"); the composer then gives it its corner together with the
legend
(:func:`coolplot.compose.corners.place_corners`), so that the two never
share a corner and isoline labels keep clear of both.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from ..core.images import load_picture
from ..scene import Badge, Watermark
from ..spec.diagram import DiagramSpec
from ..style.theme import Theme
from ..style.values import Font, TextStyle
from .layout import Frame

#: The watermark is never taller than this fraction of the plot area.
WATERMARK_MAX_HEIGHT = 0.8


def branding(spec: DiagramSpec, theme: Theme, frame: Frame,
             sources: Sequence[str] = ()) -> Tuple[Optional[Badge], Optional[Watermark]]:
    """(badge, watermark) for the chart; None for what the settings do not ask for.

    ``theme`` is the theme with the page's font scale applied and
    ``frame`` the plot area the labels are laid out in. ``sources`` are
    the lines naming the sources of the properties and the versions, from
    :meth:`coolplot.engine.Engine.source_lines` (the composer does not ask
    CoolProp itself); the badge shows them above ``BrandingSettings.lines``.
    The badge sits in the corner of the settings, the lower right one for
    "auto", until the composer places it.
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
        return None, watermark
    axes_style = theme.axes
    font_scale = spec.settings.page.font_scale
    text = TextStyle(font=Font(family=axes_style.tick_label.font.family, size_pt=settings.font_size_pt * font_scale),
                     color=axes_style.tick_label.color or "#000000", h_align="left", v_align="bottom")
    location = "lower right" if settings.location == "auto" else settings.location
    badge = Badge(location=location, logo=tuple(load_picture(s) for s in settings.logo),
                  logo_width_pt=settings.logo_width_pt, lines=tuple(sources) + settings.lines, text=text,
                  background=axes_style.background or "#ffffff", background_alpha=settings.background_alpha,
                  frame_color=axes_style.frame_color if settings.frame else None)
    if badge.empty:
        return None, watermark
    return badge, watermark
