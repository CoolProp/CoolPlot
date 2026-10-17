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
    reason : str
        What is wrong with the request, in plain words, as far as the
        thermo layer can tell: a temperature outside the equation of
        state, a quality above the critical point, an input pair CoolProp
        does not solve for mixtures. Empty when it cannot tell. It may
        hold placeholders ``{0}``, ``{1}`` for the values in ``limits``.
    limits : tuple of (key, value_SI)
        The values the reason refers to, written in the message's units.
    """

    def __init__(self, fluid: str, inputs: Tuple[Tuple[str, float], ...], cause: str, where: str = "",
                 units=None, reason: str = "", limits: Tuple[Tuple[str, float], ...] = ()):
        self.fluid = str(fluid)
        self.inputs = tuple((str(k), float(v)) for k, v in inputs)
        self.cause = str(cause).strip()
        self.where = str(where)
        self.units = units
        self.reason = str(reason)
        self.limits = tuple((str(k), float(v)) for k, v in limits)
        super().__init__(str(self))

    def _copy(self, **changes) -> "PropertyError":
        fields = dict(fluid=self.fluid, inputs=self.inputs, cause=self.cause, where=self.where, units=self.units,
                      reason=self.reason, limits=self.limits)
        fields.update(changes)
        return PropertyError(**fields)

    def with_units(self, units) -> "PropertyError":
        """The same error, written in another unit system."""
        return self._copy(units=units)

    def with_where(self, where: str) -> "PropertyError":
        return self._copy(where=where)

    def with_reason(self, reason: str, limits=()) -> "PropertyError":
        """The same error with the plain-words diagnosis attached."""
        return self._copy(reason=reason, limits=limits)

    def __reduce__(self):
        # Rebuilt through the constructor, so the error travels between processes
        return (PropertyError, (self.fluid, self.inputs, self.cause, self.where, self.units, self.reason,
                                self.limits))

    def __str__(self) -> str:
        from .units import SI, get_unit_system
        units = get_unit_system(self.units or "SI")

        def describe(key, value):
            try:
                return units.describe(key, value, 6)
            except KeyError:   # a custom system without this quantity: say it in SI
                return SI.describe(key, value, 6)
        given = ", ".join("{0} = {1}".format(k, describe(k, v)) for k, v in self.inputs)
        text = "No state of {0} at {1}".format(self.fluid, given)
        if self.where:
            text = "{0}: {1}".format(self.where, text[0].lower() + text[1:])
        details = []
        if self.reason:
            # Formatted only for the limits, so a fluid name with braces in a
            # reason without limits cannot break the message
            reason = self.reason.format(*[describe(k, v) for k, v in self.limits]) if self.limits else self.reason
            details.append(reason)
        if self.cause:
            details.append(("CoolProp: " if self.reason else "") + self.cause)
        return "{0} ({1}).".format(text, "; ".join(details)) if details else text + "."


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
        wrapper.__doc__ = "Old name: {0}.\n\n{1}".format(replacement, func.__doc__ or "")
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
