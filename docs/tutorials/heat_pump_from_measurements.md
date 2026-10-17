# A heat pump from measured states

Measured pressures and temperatures from a test rig, drawn as a cycle
and evaluated.

## The measurements

Suction and discharge of the compressor, condenser outlet, evaporator
inlet, all in bar and deg C:

```python
measured = {
    1: {"p": 4.2, "T": 2.5},      # suction line
    2: {"p": 17.6, "T": 78.0},    # discharge line
    3: {"p": 17.3, "T": 42.0},    # condenser outlet, subcooled liquid
    4: {"p": 4.4, "via": "isenthalpic"},   # after the expansion valve: the enthalpy is kept
}
```

State 4 cannot be measured by p and T alone (it is two-phase: the
temperature is the saturation temperature), so it is given by the
pressure and the fact that throttling keeps the enthalpy of state 3.

## The chart

```python
from coolplot import PropertyDiagram

diagram = PropertyDiagram("R410A.mix", "ph", units="engineering", tp_limits="ACHP")
diagram.set_lines("T", num=10, rounding=True, labels=True)
diagram.set_lines("Q", num=11)
diagram.add_cycle("Test rig, 2026-03-14", measured)
diagram.save("test_rig.png")
```

R410A is a blend: the isotherms show its temperature glide inside the
dome, and the chart takes a few seconds because the lines of a blend are
traced point by point.

## Numbers from the states

```python
states = diagram.cycle_states("Test rig, 2026-03-14")          # SI units
h = {n: s.h for n, s in states.items()}
q_evap_kJ_kg = (h[1] - h[4]) / 1e3
q_cond_kJ_kg = (h[2] - h[3]) / 1e3
w_kJ_kg = (h[2] - h[1]) / 1e3
print("COP (heating) = {0:.2f}".format(q_cond_kJ_kg / w_kJ_kg))
```

The superheat at the suction line, in kelvin, is the measured
temperature minus the dew temperature at that pressure:

```python
from coolplot import Fluid
fluid = Fluid("R410A.mix")
T_dew_K = fluid.state_point("p", 4.2e5, "Q", 1.0).T
dT_sh_K = states[1].T - T_dew_K
```

## Compare with a model

The same cycle from the ready-made model, next to the measurement, in
the same chart:

```python
from coolplot.thermo.cycles import simple_compression
diagram.add_cycle(simple_compression("R410A.mix", T_evap_C=-3, T_cond_C=40, dT_sh_K=5,
                                     dT_sc_K=3, eta_is=0.65, name="Model"))
diagram.save("test_rig_vs_model.png")
```

Each cycle gets its own colour from the theme and its own legend entry.
