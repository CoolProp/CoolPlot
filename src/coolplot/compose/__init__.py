# -*- coding: utf-8 -*-
"""Turning computed curves and a diagram spec into a scene.

No property calculations happen here and no plotting library is used.
:func:`compose` is the entry point; it uses coolplot-core
(:mod:`coolplot.corelib`) when that module is installed and asked for, and
the Python composer in :mod:`coolplot.compose.builder` otherwise.
"""
import warnings

from .. import corelib
from .builder import compose as compose_python, label_text, scaled_theme

__all__ = ["compose", "compose_python", "label_text", "scaled_theme"]


def compose(spec, domain, curves, plot_size_pt=None, previous_labels=None, cycles=None, sources=()):
    """All scene items and the axes for a diagram, see :func:`coolplot.compose.builder.compose`.

    Composed by coolplot-core when it is installed and the native mode is
    "on" (see :func:`coolplot.corelib.enabled`), by the Python composer
    otherwise; both give the same scene. coolplot-core does not compose
    the branding (badge and watermark), so a branded chart always takes
    the Python composer.
    """
    branding = spec.settings.branding
    if corelib.enabled() and not (branding.has_badge or branding.watermark):
        try:
            result = corelib.compose(spec, domain, curves, plot_size_pt, previous_labels, cycles)
        except corelib.CoreRefusal as error:
            # Something the port does not know (yet). The Python composer is
            # the reference: it draws the chart, or raises the real error.
            warnings.warn("coolplot-core could not compose this chart ({0}); the Python composer "
                          "draws it instead.".format(error), corelib.CoreFallbackWarning, stacklevel=2)
            result = None
        if result is not None:
            return result
    return compose_python(spec, domain, curves, plot_size_pt, previous_labels, cycles, sources)
