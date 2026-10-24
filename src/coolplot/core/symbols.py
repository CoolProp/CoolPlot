# -*- coding: utf-8 -*-
"""How symbols and units are written in the texts of a chart.

CoolPlot keeps its symbols and unit labels in plain ASCII ("rho",
"deg C", "kg/m3"), so that they are easy to type, compare and store. The
texts a chart shows (axis titles, legends, line labels) use the proper
characters by default: rho becomes the Greek letter, deg C the degree
sign with C, m3 the cubed metre. ``LabelSettings.symbols = "ascii"``
keeps the plain spelling on the chart as well.

The characters are written as escapes ("\\u03c1"), so that this source
file stays ASCII. Only whole symbols and whole unit labels are replaced:
"rho" turns into the Greek letter, a label such as "rhoX" stays as it is.

This module is plain data and imports nothing of CoolPlot.
"""
from __future__ import annotations

#: The values of ``LabelSettings.symbols``: "unicode" (the default since
#: 1.4) writes rho, phi, deg C, m3 and the like with their proper
#: characters, "ascii" as plain letters (the look before 1.4).
SYMBOL_STYLES = ("unicode", "ascii")

#: Quantity symbols, as CoolPlot spells them in ASCII, and how they are
#: written in "unicode" style. Relative humidity is phi on both humid air
#: charts, as in the ASHRAE Handbook and ISO 80000-5.
UNICODE_SYMBOLS = {
    "rho": "\u03c1",    # Greek small letter rho, density
    "phi": "\u03c6",    # Greek small letter phi, relative humidity
    "RH": "\u03c6",
    "Twb": "T_wb",      # wet-bulb temperature, written like T_sat
    "Tdp": "T_dp",      # dew-point temperature
}

#: Unit labels of the unit systems in ASCII, and how they are written in
#: "unicode" style. The same texts in a custom unit are replaced too.
UNICODE_UNITS = {
    "deg C": "\u00b0C",            # degree sign
    "deg F": "\u00b0F",
    "R": "\u00b0R",                # degree Rankine
    "Btu/lb/R": "Btu/lb/\u00b0R",
    "kg/m3": "kg/m\u00b3",         # superscript three
    "m3/kg": "m\u00b3/kg",
    "lb/ft3": "lb/ft\u00b3",
    "ft3/lb": "ft\u00b3/lb",
}


def check_symbol_style(style: str) -> str:
    """``style`` if it is one of :data:`SYMBOL_STYLES`, else a ValueError."""
    if style not in SYMBOL_STYLES:
        raise ValueError("Unknown symbol style '{0}', expected one of {1}.".format(style, SYMBOL_STYLES))
    return style


def symbol_text(symbol: str, style: str) -> str:
    """A quantity symbol as the chart shows it, e.g. "rho" in "unicode" style is the Greek letter."""
    return UNICODE_SYMBOLS.get(symbol, symbol) if style == "unicode" else symbol


def unit_text(label: str, style: str) -> str:
    """A unit label as the chart shows it, e.g. "deg C" in "unicode" style is the degree sign and C."""
    return UNICODE_UNITS.get(label, label) if style == "unicode" else label
