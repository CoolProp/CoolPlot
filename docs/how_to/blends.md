# Refrigerant blends, mixtures and brines

## Blends

```python
PropertyDiagram("HEOS::R32[0.7]&R125[0.3]", "ph")     # mole fractions
PropertyDiagram("HEOS::R410A.mix", "ph")               # a predefined blend
```

A chart of a blend takes seconds rather than a fraction of a second:
R410A about five, R407C about ten for the default p-h chart. The bubble
and dew lines come from CoolProp's phase envelope, so the dome closes
through the critical region; isotherms and isobars show the temperature
glide inside the dome; lines of intermediate quality run up to the top
of the envelope. A blend chart starts at the highest triple-point
temperature of its components (R32 is solid below -137 deg C whatever it
is mixed with).

CoolProp solves a mixture state from p with any other quantity and from
T with p, rho or Q. A state given by T and h, say, raises a
`PropertyError` that says so; give p instead. Every state CoolProp
returns for a mixture is checked against the saturated densities at its
temperature, because CoolProp 8 answers some inputs inside the two-phase
region with a "gas" at a wrong pressure; such points are left out rather
than drawn.

For charts of blends in an interactive application use
`background="processes"`, see {doc}`web`; a blend chart then never blocks
the window.

## REFPROP

`"REFPROP::R32"` and `"REFPROP::R32[0.7]&R125[0.3]"` work where REFPROP
is installed and CoolProp finds it.

## Brines and other incompressibles

`"INCOMP::MEG[0.3]"` (ethylene glycol, 30 % by mass) and the other
incompressible fluids have no saturation curve. Give absolute limits,
`tp_limits=[T_min_K, T_max_K, p_min_Pa, p_max_Pa]`, and do not ask for
quality lines. Isotherms, isobars and lines of h, s and u work; an
isenthalp of a brine is short in a T-s chart, because h and s both
follow the temperature.

## CoolProp's global settings

Changing CoolProp's configuration (`set_config_bool` and friends) is
noticed: the next update computes with fresh states. A changed reference
state (`set_reference_state`) is not visible from outside: call
`diagram.refresh()` after it, otherwise the diagram keeps the enthalpy
and entropy offsets it started with. Lines are cached with a fingerprint
of CoolProp's version, configuration and reference state, so a line
computed under other settings is never shown.
