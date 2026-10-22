# -*- coding: utf-8 -*-
"""Several charts in one file.

:func:`save_pdf` writes property diagrams and psychrometric charts into one
PDF, one chart per page, e.g. for a report. Each page has the size of its
chart's ``settings.page`` and the fonts are embedded as for a single PDF
(see :meth:`coolplot.render.mpl.MatplotlibRenderer.save`).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Union

if TYPE_CHECKING:   # only for the type checker: matplotlib is imported when the file is written
    from .chart import Chart
    from .render.mpl import MatplotlibRenderer


def save_pdf(path: Union[str, os.PathLike], charts: Sequence[Chart], pdf_fonts: str = "truetype",
             metadata: Optional[Dict[str, str]] = None) -> List[MatplotlibRenderer]:
    """Write ``charts`` (PropertyDiagram, PsychrometricChart) into one PDF.

    ``metadata`` adds PDF fields such as {"Author": ..., "Subject": ...};
    the title is that of the first chart with a title unless given. Returns
    the renderers, one per page.
    """
    from .render.mpl import MatplotlibRenderer
    if not charts:
        raise ValueError("Give at least one chart for the PDF.")
    renderers = [chart.draw(MatplotlibRenderer(use_pyplot=False, figsize=chart.spec.settings.page.size_in))
                 for chart in charts]
    MatplotlibRenderer.save_pages(path, renderers, pdf_fonts=pdf_fonts, metadata=metadata)
    return renderers
