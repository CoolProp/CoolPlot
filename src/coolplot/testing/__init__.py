# -*- coding: utf-8 -*-
"""Tools for testing CoolPlot and its backends; nothing here runs when a chart is drawn.

* :mod:`coolplot.testing.kit`: the conformance kit for renderers
  (``run_conformance``, ``check_events``, ``check_pdf``) and the reference
  scene it draws (``conformance_scene``), see docs/contributing/writing_a_backend.md.
* :mod:`coolplot.testing.pdf_reader`: reads PDF files back (fonts, texts,
  colours) for ``check_pdf``, and rewrites the document information.
"""
from .kit import ALLOWED_LIMITATIONS, check_events, check_pdf, conformance_scene, run_conformance

__all__ = ["ALLOWED_LIMITATIONS", "check_events", "check_pdf", "conformance_scene", "run_conformance"]
