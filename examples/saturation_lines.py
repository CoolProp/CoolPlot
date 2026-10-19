# -*- coding: utf-8 -*-
"""
Isentropes and isochores placed by saturation temperature
=========================================================


A log(p)-h chart of propane where the isentropes run through the
saturated vapour every 10 K of saturation temperature, and the isochores
every 20 K. A compressor that sucks saturated vapour at a round
evaporating temperature follows one of these isentropes. Each line is
labelled with its own entropy or density; "label": "saturation" would
name the saturation temperature instead ("T_sat=0 deg C").

Run with:  python examples/saturation_lines.py
Writes R290_saturation.svg.
"""
from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer
from coolplot.thermo.cycles import simple_compression

diagram = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
diagram.title = "R290, lines through the saturated vapour"
diagram.set_lines("Q", num=11, labels=True)
diagram.set_lines("s", at_saturation={"T": 10, "range": (-40, 60)}, labels=True)
diagram.set_lines("rho", at_saturation={"T": 20, "range": (-40, 60)}, labels=True)
diagram.add_cycle(simple_compression(diagram.fluid, T_evap_C=0.0, T_cond_C=40.0, dT_sh_K=0.0, dT_sc_K=2.0,
                                     eta_is=1.0))

for iso in diagram.line_sets().values():
    if iso.anchor is not None:
        print("{0}: through the saturated vapour every {1:g} K".format(iso.key, iso.anchor.step_SI))

svg = diagram.draw(SvgRenderer(width=1000, height=720))
svg.save("R290_saturation.svg")
