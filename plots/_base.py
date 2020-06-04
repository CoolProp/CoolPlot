# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import CoolProp
from CoolPlot.Plot.Plots import PropertyPlot

class iso_props(dict):

    def __init__(self, *args, **kwargs):
        res = super().__init__(*args, **kwargs)
        self['iso_type']=None
        self['iso_range']=None
        self['num']=15
        self['rounding']=False
        self['points']=250
        return


def create_ph_plot(fluid : str, props : list = []):
    plot = PropertyPlot(fluid, 'ph', unit_system='EUR', tp_limits='ACHP')
    for prop in props:
        plot.calc_isolines(**prop)
    plot.show()
    input("Created ph-plot for {0}, press Enter to continue...".format(fluid))
    return plot


if __name__ == "__main__":
    plot = PropertyPlot('REFPROP::R455A.mix', 'ph', unit_system='EUR', tp_limits='ACHP')
    plot.calc_isolines(CoolProp.iQ, num=11)
    plot.calc_isolines(CoolProp.iT, num=25)
    plot.calc_isolines(CoolProp.iSmass, num=15)
    plot.savefig('R455A.png')
    plot.show()

    input("Press Enter to continue...")