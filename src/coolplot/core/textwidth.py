# -*- coding: utf-8 -*-
"""Width of a text line, estimated without a font engine.

The SVG writer cannot measure text: the viewer picks the font and draws
it. Boxes that hold text (the branding badge) are therefore sized from an
estimate. The estimate uses the advance widths of Helvetica, taken from
the Adobe font metrics file ``phvr8a.afm`` that ships with matplotlib, for
the printable ASCII characters. Common sans-serif fonts are a little wider
(DejaVu Sans and Poppins by 5 to 12 % on typical reference lines), so
:func:`text_width_pt` adds :data:`MARGIN`. Wide characters (East Asian
scripts) count as :data:`WIDE_EM`, every other character as :data:`OTHER_EM`.

This module is plain Python; no CoolProp, no plotting library.
"""
from __future__ import annotations

import unicodedata

#: Advance widths in 1/1000 em of the characters " " (32) to "~" (126), Helvetica.
HELVETICA_WIDTHS = (
    278, 278, 355, 556, 556, 889, 667, 222, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667,
    611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 278, 278, 278, 469, 556, 222, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500,
    222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)

#: Width of a character outside printable ASCII, in em (accented letters and the like).
OTHER_EM = 0.6
#: Width of a wide character (Chinese, Japanese, Korean, full-width forms), in em.
WIDE_EM = 1.0

#: Factor for fonts wider than Helvetica.
MARGIN = 1.15


def text_width_em(text: str) -> float:
    """Width of ``text`` in em of Helvetica, without margin."""
    total = 0.0
    for char in text:
        code = ord(char)
        if 32 <= code <= 126:
            total += HELVETICA_WIDTHS[code - 32] / 1000.0
        else:
            total += WIDE_EM if unicodedata.east_asian_width(char) in ("W", "F") else OTHER_EM
    return total


def text_width_pt(text: str, size_pt: float) -> float:
    """Estimated width of one line of ``text`` at ``size_pt``, with :data:`MARGIN`."""
    return MARGIN * size_pt * text_width_em(text)
