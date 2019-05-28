# -*- coding: utf-8 -*-
from __future__ import print_function, division

from abc import ABCMeta
from six import with_metaclass
import warnings
import numpy as np

import CoolProp

from . import is_string, _get_index

class BaseQuantity(object):
    """A very basic property that can convert an input to and from a
    given unit system, note that the conversion from SI units starts
    with a multiplication. If you need to remove an offset, use the
    off_SI property.
    Examples with temperature:
    celsius = BaseQuantity(add_SI=-273.15)
    fahrenheit = BaseQuantity(add_SI=32.0, mul_SI=1.8, off_SI=-273.15)
    Examples with pressure:
    bar = BaseQuantity(mul_SI=1e-5)
    psi = BaseQuantity(mul_SI=0.000145037738)
    """

    def __init__(self, add_SI=0.0, mul_SI=1.0, off_SI=0.0):
        self._add_SI = add_SI
        self._mul_SI = mul_SI
        self._off_SI = off_SI

    @property
    def add_SI(self): return self._add_SI

    @add_SI.setter
    def add_SI(self, value): self._add_SI = value

    @property
    def mul_SI(self): return self._mul_SI

    @mul_SI.setter
    def mul_SI(self, value): self._mul_SI = value

    @property
    def off_SI(self): return self._off_SI

    @off_SI.setter
    def off_SI(self, value): self._off_SI = value

    def from_SI(self, value): return ((np.asanyarray(value) + self.off_SI) * self.mul_SI) + self.add_SI

    def to_SI(self, value): return (np.asanyarray(value) - self.add_SI) / self.mul_SI - self.off_SI


class BaseDimension(BaseQuantity):
    """A dimension is a class that extends the BaseQuantity and adds a
    label, a symbol and a unit label.
    """

    def __init__(self, add_SI=0.0, mul_SI=1.0, off_SI=0.0, label='', symbol='', unit=''):
        self._label = label
        self._symbol = symbol
        self._unit = unit
        super(BaseDimension, self).__init__(add_SI=add_SI, mul_SI=mul_SI, off_SI=off_SI)

    @property
    def label(self): return self._label

    @label.setter
    def label(self, value): self._label = value

    @property
    def symbol(self): return self._symbol

    @symbol.setter
    def symbol(self, value): self._symbol = value

    @property
    def unit(self): return self._unit

    @unit.setter
    def unit(self, value): self._unit = value


class PropertyDict(with_metaclass(ABCMeta), object):
    """A collection of dimensions for all the required quantities"""

    def __init__(self):
        self._D = None
        self._H = None
        self._P = None
        self._S = None
        self._T = None
        self._U = None
        self._Q = None

    @property
    def D(self): return self._D

    @D.setter
    def D(self, value): self._D = value

    @property
    def H(self): return self._H

    @H.setter
    def H(self, value): self._H = value

    @property
    def P(self): return self._P

    @P.setter
    def P(self, value): self._P = value

    @property
    def S(self): return self._S

    @S.setter
    def S(self, value): self._S = value

    @property
    def T(self): return self._T

    @T.setter
    def T(self, value): self._T = value

    @property
    def U(self): return self._U

    @U.setter
    def U(self, value): self._U = value

    @property
    def Q(self): return self._Q

    @Q.setter
    def Q(self, value): self._Q = value

    @property
    def dimensions(self):
        return {
      CoolProp.iDmass: self._D,
      CoolProp.iHmass: self._H,
      CoolProp.iP: self._P,
      CoolProp.iSmass: self._S,
      CoolProp.iT: self._T,
      CoolProp.iUmass: self._U,
      CoolProp.iQ: self._Q
    }

    def __getitem__(self, index):
        """Allow for property access via square brackets"""
        idx = _get_index(index)
        if idx == CoolProp.iDmass: return self.D
        elif idx == CoolProp.iHmass: return self.H
        elif idx == CoolProp.iP: return self.P
        elif idx == CoolProp.iSmass: return self.S
        elif idx == CoolProp.iT: return self.T
        elif idx == CoolProp.iUmass: return self.U
        elif idx == CoolProp.iQ: return self.Q
        else: raise IndexError("Unknown index \"{0:s}\".".format(str(index)))

    def __setitem__(self, index, value):
        """Allow for property access via square brackets"""
        idx = _get_index(index)
        if idx == CoolProp.iDmass: self.D = value
        elif idx == CoolProp.iHmass: self.H = value
        elif idx == CoolProp.iP: self.P = value
        elif idx == CoolProp.iSmass: self.S = value
        elif idx == CoolProp.iT: self.T = value
        elif idx == CoolProp.iUmass: self.U = value
        elif idx == CoolProp.iQ: self.Q = value
        else: raise IndexError("Unknown index \"{0:s}\".".format(str(index)))
