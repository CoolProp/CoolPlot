# -*- coding: utf-8 -*-
"""Turning computed curves and a diagram spec into a scene.

No property calculations happen here and no plotting library is used.
:func:`compose` is the entry point; it uses coolplot-core
(:mod:`coolplot.corelib`) when that module is installed and asked for, and
the Python composer in :mod:`coolplot.compose.builder` otherwise.
"""
from .. import corelib
from .builder import compose as compose_python, label_text, scaled_theme

__all__ = ["compose", "compose_python", "label_text", "scaled_theme"]


def compose(spec, domain, curves, plot_size_pt=None, previous_labels=None, cycles=None):
    """All scene items and the axes for a diagram, see :func:`coolplot.compose.builder.compose`.

    Composed by coolplot-core when it is installed and ``COOLPLOT_NATIVE``
    is set (see :func:`coolplot.corelib.enabled`), by the Python composer
    otherwise; both give the same scene.
    """
    if corelib.enabled():
        result = corelib.compose(spec, domain, curves, plot_size_pt, previous_labels, cycles)
        if result is not None:
            return result
    return compose_python(spec, domain, curves, plot_size_pt, previous_labels, cycles)
