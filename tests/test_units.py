# -*- coding: utf-8 -*-

#from .context import CoolPlot
from CoolPlot.Util.Units import SIunits, KSIunits, EURunits


if __name__ == '__main__':

    for sys in [SIunits(), KSIunits(), EURunits()]:
        print(sys.H.label)
        print(sys.H.to_SI(20))
        print(sys.P.label)
        print(sys.P.to_SI(20))

    # # i_index, x_index, y_index, value=None, state=None)
    # iso = IsoLine('T', 'H', 'P')
    # print(iso.get_update_pair())

    # state = AbstractState("HEOS", "water")
    # iso = IsoLine('T', 'H', 'P', 300.0, state)
    # hr = PropsSI("H", "T", [290, 310], "P", [1e5, 1e5], "water")
    # pr = np.linspace(0.9e5, 1.1e5, 3)
    # iso.calc_range(hr, pr)
    # print(iso.x, iso.y)

    # iso = IsoLine('Q', 'H', 'P', 0.0, state)
    # iso.calc_range(hr, pr); print(iso.x, iso.y)
    # iso = IsoLine('Q', 'H', 'P', 1.0, state)
    # iso.calc_range(hr, pr); print(iso.x, iso.y)

    # # bp = BasePlot(fluid_ref, graph_type, unit_system = 'KSI', **kwargs):
    # bp = BasePlot('n-Pentane', 'PH', unit_system='EUR')
    # # print(bp._get_sat_bounds('P'))
    # # print(bp._get_iso_label(iso))
    # print(bp.get_axis_limits())

        # # get_update_pair(CoolProp.iP,CoolProp.iSmass,CoolProp.iT) -> (0,1,2,CoolProp.PSmass_INPUTS)
        # # other values require switching and swapping
        # # get_update_pair(CoolProp.iSmass,CoolProp.iP,CoolProp.iHmass) -> (1,0,2,CoolProp.PSmass_INPUTS)