# -*- coding: utf-8 -*-
"""Exact tests on floats, without comparing two floats for equality.

Comparing two floats with ``==`` is fragile: two ways of computing the same
number can differ in the last bit. Where the numerics need an exact answer,
they ask a sharper question instead:

* :func:`is_zero` -- is this an exact root, or a denominator that vanished?
* :func:`sign_of` -- on which side of zero is this residual?
* :func:`same_bits` -- is this the same input as before (a cache key)?
* :func:`same_number` / :func:`same_numbers` -- is this the very number (or
  numbers) set or copied earlier: a user setting, a limit, a position?
* :func:`is_zero_array` -- :func:`is_zero` for every element of an array.
* :func:`same_arrays` -- is this array a copy of that one, bit for bit
  (round trips in the tests; NaN gaps included)?

Not covered on purpose: the equality of value objects (the dataclasses of
specs and styles, StatePoint) and the caches keyed by them. Their generated
``__eq__`` and ``__hash__`` compare fields with ``==``; there exact equality
is the intent (the same configuration, a cache hit), and a near miss only
recomputes.

The C++ port in CoolProp (``src/CoolPropPlot.cpp``) and the C++ core under
``cpp/`` have the same helpers.
"""
import math
import struct

import numpy as np

_ALL_BUT_SIGN = 0x7FFFFFFFFFFFFFFF


def _bits_of(v: float) -> int:
    """The 64 bits of a float, as an integer."""
    return struct.unpack("<Q", struct.pack("<d", v))[0]


def is_zero(v: float) -> bool:
    """Whether v is exactly zero, of either sign: an exact root, or a denominator that vanished

    A classification of the bits (all zero but the sign), like C's
    fpclassify: NaN is not zero. It does not compare against the smallest
    subnormal, which reads as zero when an extension built with fast-math
    has set the processor to treat denormals as zero.
    """
    return (_bits_of(v) & _ALL_BUT_SIGN) == 0


def sign_of(v: float) -> int:
    """-1, 0 or +1: the sign of v, so that sign tests are integer comparisons."""
    return int(v > 0.0) - int(v < 0.0)


def same_bits(a: float, b: float) -> bool:
    """Whether two floats are the same input, bit for bit

    A cache keyed on an input value uses it: a tolerance would hand back the
    result of another input.
    """
    return _bits_of(a) == _bits_of(b)


def same_number(a: float, b: float) -> bool:
    """Whether a and b are the very same number: the same bits, or +0.0 and -0.0

    For a value set or copied earlier (a user setting, an axis limit, a
    position), not for two results of a calculation. NaN is no number, so
    it is never the same.
    """
    if math.isnan(a) or math.isnan(b):
        return False
    return same_bits(a, b) or (is_zero(a) and is_zero(b))


def same_numbers(a, b) -> bool:
    """:func:`same_number` element by element, for two sequences of the same length."""
    a, b = tuple(a), tuple(b)
    return len(a) == len(b) and all(same_number(x, y) for x, y in zip(a, b))


def is_zero_array(values) -> np.ndarray:
    """:func:`is_zero` for every element of an array: a boolean array of the same shape."""
    bits = np.ascontiguousarray(values, dtype=np.float64).view(np.uint64)
    return (bits & np.uint64(_ALL_BUT_SIGN)) == np.uint64(0)


def same_arrays(a, b) -> bool:
    """Whether two arrays have the same shape and the same bits in every element (NaN included)."""
    a = np.ascontiguousarray(a, dtype=np.float64)
    b = np.ascontiguousarray(b, dtype=np.float64)
    return a.shape == b.shape and bool(np.all(a.view(np.uint64) == b.view(np.uint64)))
