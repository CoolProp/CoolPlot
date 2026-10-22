# -*- coding: utf-8 -*-
"""A PDF backend without matplotlib: coolplot-core writes the page.

:class:`PdfRenderer` draws the scene of the SVG backend (it is an
:class:`~coolplot.render.svg.SvgRenderer`, so its read-back and the
conformance kit's checks of items work on the same geometry) and writes a
print-ready PDF page with :mod:`coolplot.corelib`: one page of the size
of ``Settings.page``, TrueType fonts embedded as subsets, sRGB colours,
every text as text, the same file for the same scene. It needs the
``coolplot_core`` module; the matplotlib backend writes PDF without it.
"""
from __future__ import annotations

from .. import corelib
from .svg import PX_PER_PT, SvgRenderer, check_suffix
from .base import warn_without_branding


class PdfRenderer(SvgRenderer):
    """Write a scene as one PDF page through coolplot-core

    Parameters
    ----------
    width_pt, height_pt : float
        The page size in points (72 pt = 1 inch).
    margins_pt : (left, right, top, bottom)
        Space around the plot area for ticks and labels, in points. An
        outside legend adds to the right margin.
    font_dirs : sequence of str
        Directories searched for TrueType fonts, the platform's when empty.
    """

    capabilities = frozenset({"file_output", "css_classes", "pdf_output"})
    default_suffix = ".pdf"
    text_output = False

    def __init__(self, width_pt: float = 576.0, height_pt: float = 432.0, margins_pt=(60.0, 15.0, 30.0, 45.0),
                 font_dirs=(), id_prefix: str = "coolplot"):
        if not (corelib.available() and corelib.has_pdf()):
            raise ValueError("PdfRenderer needs the coolplot_core module (cpp/); the matplotlib backend writes PDF "
                             "without it.")
        # The SVG geometry in pixels, the same page at 4/3 px per pt
        super().__init__(width=int(round(width_pt * PX_PER_PT)), height=int(round(height_pt * PX_PER_PT)),
                         margins=tuple(m * PX_PER_PT for m in margins_pt), id_prefix=id_prefix)
        self.width_pt = float(width_pt)
        self.height_pt = float(height_pt)
        self.margins_pt = tuple(float(m) for m in margins_pt)
        self.font_dirs = tuple(font_dirs)

    def _scene_items(self):
        """The items in scene order (the legend follows it), see SvgRenderer.to_svg."""
        return [self._items[i] for i in self._scene_ids if i in self._items]

    def plot_size_pt(self):
        """(width, height) of the plot area of the PDF page in points.

        Taken from the page coolplot-core writes, so that a chart composed
        for this size fills the page exactly. The SVG geometry of the base
        class agrees with it except for rounding the page to whole pixels.
        """
        return corelib.pdf_plot_size_pt(self._axes, self._scene_items(), self.width_pt, self.height_pt,
                                        self.margins_pt)

    def to_pdf(self) -> bytes:
        """The PDF file of the last synchronised scene (without badge and watermark, see BrandingSettings)."""
        warn_without_branding(self, self._axes)
        items = self._scene_items()
        font_files = []
        for item in items:
            style = getattr(item, "style", None)
            for f in getattr(getattr(style, "font", None), "files", ()):
                if f not in font_files:
                    font_files.append(f)
        return corelib.scene_to_pdf(self._axes, items, self.width_pt, self.height_pt, self.margins_pt,
                                    self.font_dirs, font_files)

    def save(self, path):
        """Write the PDF file; the file name has to end in ".pdf"."""
        check_suffix(path, (".pdf",), type(self).__name__, "PDF")
        data = self.to_pdf()   # before opening, so a font error leaves no empty file behind
        with open(path, "wb") as f:
            f.write(data)
