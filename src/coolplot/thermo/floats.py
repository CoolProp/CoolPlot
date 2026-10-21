# -*- coding: utf-8 -*-
"""Exact tests on floats, without comparing two floats for equality.

Comparing two floats with ``==`` is fragile: two ways of computing the same
number can differ in the last bit. Where the numerics need an exact answer,
they ask a sharper question instead:

* :func:`is_zero` -- is this an exact root, or a denominator that vanished?
* :func:`sign_of` -- on which side of zero is this residual?
* :func:`same_bits` -- is this the same input as before (a cache key)?

The C++ port in CoolProp (``src/CoolPropPlot.cpp``) has the same helpers.
"""
import struct

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
