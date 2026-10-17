# -*- coding: utf-8 -*-
"""Errors that name the fluid and the inputs, in the user's units.

CoolProp reports a failed calculation in its own words ("unable to
calculate melting line T(p) for Simon curve for p=3e+10"). A
:class:`PropertyError` adds what the user needs: which fluid, which two
inputs with their values, and where in the chart the request came from.
The thermo layer raises it with SI values; the chart facade attaches
the chart's unit system before it reaches the user, so the message
reads "p = 300000 bar", which shows the mistake at a glance.
"""
from __future__ import annotations

import warnings
from functools import wraps
from typing import Optional, Tuple


class PropertyError(ValueError):
    """No state could be computed from the given inputs

    Attributes
    ----------
    fluid : str
        The fluid (or "humid air at ... Pa").
    inputs : tuple of (key, value_SI)
        The quantities that were given.
    cause : str
        What CoolProp said.
    where : str
        What asked for the state, e.g. "State 2 of cycle 'heat pump'".
    units : UnitSystem or None
        The unit system the message is written in; SI if None.
    """

    def __init__(self, fluid: str, inputs: Tuple[Tuple[str, float], ...], cause: str, where: str = "",
                 units=None):
        self.fluid = str(fluid)
        self.inputs = tuple((str(k), float(v)) for k, v in inputs)
        self.cause = str(cause).strip()
        self.where = str(where)
        self.units = units
        super().__init__(str(self))

    def with_units(self, units) -> "PropertyError":
        """The same error, written in another unit system."""
        return PropertyError(self.fluid, self.inputs, self.cause, self.where, units)

    def with_where(self, where: str) -> "PropertyError":
        return PropertyError(self.fluid, self.inputs, self.cause, where, self.units)

    def __str__(self) -> str:
        from .units import get_unit_system
        units = get_unit_system(self.units or "SI")
        given = ", ".join("{0} = {1}".format(k, units.describe(k, v, 6)) for k, v in self.inputs)
        text = "No state of {0} at {1}".format(self.fluid, given)
        if self.where:
            text = "{0}: {1}".format(self.where, text[0].lower() + text[1:])
        return "{0} ({1}).".format(text, self.cause) if self.cause else text + "."


def deprecated(replacement: str, since: str = "0.5"):
    """Mark a method as an old name: it warns and calls the new one.

    Used for the names that 1.0 drops; the warning tells the user what
    to write instead. ``replacement`` is a short instruction such as
    "use set_lines".
    """
    def decorate(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn("{0}() is an old name since CoolPlot {1} and will go in 1.0; {2}.".format(
                func.__name__, since, replacement), DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)
        wrapper.__doc__ = "Old name, see {0}.\n\n{1}".format(replacement, func.__doc__ or "")
        wrapper.deprecated = True
        return wrapper
    return decorate


def check_old_keyword(kwargs: dict, old: str, new: str, func_name: str) -> Optional[object]:
    """Take an old keyword out of ``kwargs`` with a warning; returns its value or None."""
    if old not in kwargs:
        return None
    warnings.warn("{0}(): the keyword '{1}' is called '{2}' since CoolPlot 0.5; the old name will go in 1.0.".format(
        func_name, old, new), DeprecationWarning, stacklevel=3)
    return kwargs.pop(old)
