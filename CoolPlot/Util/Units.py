# -*- coding: utf-8 -*-
from __future__ import print_function, division

from .Quantities import PropertyDict, BaseDimension


class SIunits(PropertyDict):
    def __init__(self):
        self._D = BaseDimension(add_SI=0.0, mul_SI=1.0, off_SI=0.0, label='Density', symbol=u'd', unit=u'kg/m3')
        self._H = BaseDimension(add_SI=0.0, mul_SI=1.0, off_SI=0.0, label='Specific Enthalpy', symbol=u'h', unit=u'J/kg')
        self._P = BaseDimension(add_SI=0.0, mul_SI=1.0, off_SI=0.0, label='Pressure', symbol=u'p', unit=u'Pa')
        self._S = BaseDimension(add_SI=0.0, mul_SI=1.0, off_SI=0.0, label='Specific Entropy', symbol=u's', unit=u'J/kg/K')
        self._T = BaseDimension(add_SI=0.0, mul_SI=1.0, off_SI=0.0, label='Temperature', symbol=u'T', unit=u'K')
        self._U = BaseDimension(add_SI=0.0, mul_SI=1.0, off_SI=0.0, label='Specific Internal Energy', symbol=u'u', unit=u'J/kg')
        self._Q = BaseDimension(add_SI=0.0, mul_SI=1.0, off_SI=0.0, label='Vapour Quality', symbol=u'x', unit=u'')


class KSIunits(SIunits):
    def __init__(self):
        super(KSIunits, self).__init__()
        self.H.mul_SI = 1e-3
        self.H.unit = u'kJ/kg'
        self.P.mul_SI = 1e-3
        self.P.unit = u'kPa'
        self.S.mul_SI = 1e-3
        self.S.unit = u'kJ/kg/K'
        self.U.mul_SI = 1e-3
        self.U.unit = u'kJ/kg'


class EURunits(KSIunits):
    def __init__(self):
        super(EURunits, self).__init__()
        self.P.mul_SI = 1e-5
        self.P.unit = u'bar'
        self.T.add_SI = -273.15
        self.T.unit = u'deg C'


def get_unit_system_cls():
    return [SIunits, KSIunits, EURunits]
