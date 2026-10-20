# -*- coding: utf-8 -*-
"""The one setting that chooses between the Python code and the C++ ports.

CoolPlot can compute and draw a chart with two implementations of the same
steps. Both give the same result; the Python code is the reference.

* The numerics (lines of a fluid) run in CoolProp's C++ port
  (``CoolProp.CoolProp.Plot``, see :mod:`coolplot.thermo.native`) or in
  Python.
* The composer and the SVG writer run in coolplot-core (``coolplot_core``,
  see :mod:`coolplot.corelib`) or in Python.

The mode decides which:

========  ==============================  ==============================
mode      numerics                        composer and SVG writer
========  ==============================  ==============================
"auto"    C++ port when installed         Python
"on"      C++ port when installed         coolplot-core when installed
"off"     Python                          Python
========  ==============================  ==============================

"auto" is the default because from Python the composer is faster in Python
(its records would cross into C++ as JSON). A port that is not installed is
never used, whatever the mode.

The environment variable ``COOLPLOT_NATIVE`` gives the starting mode:
unset or "auto" means "auto", "0" (or "off", "false", "no") means "off",
anything else means "on". :func:`set_native_mode` overrides it for the
running program.
"""
from __future__ import annotations

import os
from typing import Optional

#: The modes :func:`set_native_mode` accepts.
NATIVE_MODES = ("auto", "on", "off")

_OFF_WORDS = ("0", "off", "false", "no")

# The mode set from Python, or None to follow the environment variable
_mode: Optional[str] = None


def _mode_from_environment() -> str:
    value = os.environ.get("COOLPLOT_NATIVE", "").strip().lower()
    if value in ("", "auto"):
        return "auto"
    return "off" if value in _OFF_WORDS else "on"


def native_mode() -> str:
    """The current mode: "auto", "on" or "off" (see the module documentation)."""
    return _mode if _mode is not None else _mode_from_environment()


def set_native_mode(mode: Optional[str]) -> Optional[str]:
    """Choose the implementation for the rest of the program and return the previous setting.

    Parameters
    ----------
    mode : {"auto", "on", "off"} or None
        "off" uses the Python code everywhere, "on" the C++ ports wherever
        they are installed, "auto" (the default) the numerics port only.
        None goes back to the environment variable ``COOLPLOT_NATIVE``.

    Returns
    -------
    str or None
        The previous setting: a mode, or None if the environment variable
        decided. Passing it back restores exactly what was there before.
        The mode in effect is :func:`native_mode`.

    Notes
    -----
    The setting holds for the whole program (every chart and thread). A
    background engine with worker processes takes it from the chart's
    process, not from the workers' environment.

    Examples
    --------
    >>> previous = set_native_mode("off")   # the Python reference
    >>> native_mode()
    'off'
    >>> set_native_mode(previous)
    'off'
    """
    global _mode
    if mode is not None:
        mode = str(mode).strip().lower()
        if mode not in NATIVE_MODES:
            raise ValueError("Unknown native mode '{0}', expected one of {1} or None.".format(mode, NATIVE_MODES))
    previous = _mode
    _mode = mode
    return previous
