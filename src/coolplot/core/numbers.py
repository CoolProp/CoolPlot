# -*- coding: utf-8 -*-
"""How numbers are written on a diagram: tick labels and label values.

One function for every value shown, so that a backend cannot write
"1e+05" where another writes "100000", and the labels of a chart look the
same in matplotlib, SVG or a browser.

This module is plain Python; no CoolProp, no plotting library.
"""
from __future__ import annotations

import math

from .floats import is_zero

#: Values whose magnitude is in [SCI_BELOW, SCI_ABOVE) are written as plain
#: decimals, everything else in scientific notation such as 2.5e-4 or 1e7.
SCI_BELOW = 1e-3
SCI_ABOVE = 1e6


def format_number(value: float, digits: int = 6) -> str:
    """A number with at most ``digits`` significant digits, plain ASCII.

    Trailing zeros are dropped and rounding noise disappears:
    0.30000000000000004 becomes "0.3". Examples with the default digits:
    25 -> "25", 0.5 -> "0.5", 1e5 -> "100000", 1e6 -> "1e6",
    0.00025 -> "2.5e-4", -20 -> "-20". NaN and infinity are written as
    "nan", "inf" and "-inf".
    """
    value = float(value)
    if not math.isfinite(value):
        return "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
    if is_zero(value):
        return "0"
    rounded = float("{0:.{1}g}".format(value, digits))
    if not math.isfinite(rounded):   # rounding up the largest numbers overflows
        rounded = value
    if SCI_BELOW <= abs(rounded) < SCI_ABOVE:
        exponent = math.floor(math.log10(abs(rounded)))
        decimals = max(0, digits - 1 - exponent)
        text = "{0:.{1}f}".format(rounded, decimals)
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text in ("-0", "") else text
    mantissa, power = "{0:.{1}e}".format(rounded, digits - 1).split("e")
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    return "{0}e{1}".format(mantissa, int(power))
