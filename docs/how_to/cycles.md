# Cycles

## From states

```python
diagram.add_cycle("Heat pump", [
    {"p": 3.0, "T": 0.0},                               # 1 compressor inlet
    {"p": 15.0, "via": "compression", "eta_is": 0.7},   # 2 compressor outlet
    {"p": 15.0, "Q": 0.0},                              # 3 condenser outlet
    {"p": 3.0, "via": "isenthalpic"},                   # 4 after the valve
])
```

Each state is given by two properties in the chart's units, or by one
property and `"via"`, which takes the second property from the state
before it in the cycle:

| via | The state keeps or follows |
|-----|---------------------------|
| `"isenthalpic"` | the enthalpy (a throttling valve) |
| `"isentropic"`, `"isobaric"`, `"isothermal"`, `"isochoric"` | entropy, pressure, temperature or density |
| `"compression"`, `"expansion"` | the outlet pressure with the isentropic efficiency `eta_is` |

States can also be `StatePoint` values, or arrays of two properties:
`diagram.add_cycle("measured", p=[...], h=[...])`. `units="SI"` reads
the values in another system; `closed=False` leaves the chain open (a
process rather than a cycle).

The path between two states follows the process: equal pressure gives
an isobar that bends on the dome, equal enthalpy an isenthalp, equal
entropy an isentrope, anything else a polytropic path. Set a path
yourself with `paths={(1, 2): "straight"}`.

## Split and two-stage cycles

States are numbered (list order, or the keys of a dict); `loops` gives
chains of state numbers, each drawn as one line, and chains may share
states:

```python
states = {1: {"p": 1.5, "T": -25.0}, 2: {"p": 5.0, "via": "compression", "eta_is": 0.7},
          3: {"p": 5.0, "Q": 1.0},   4: {"p": 18.0, "via": "compression", "eta_is": 0.7},
          5: {"p": 18.0, "Q": 0.0},  6: {"p": 5.0, "via": "isenthalpic"},
          7: {"p": 5.0, "Q": 0.0},   8: {"p": 1.5, "via": "isenthalpic"}}
diagram.add_cycle("Two-stage", states)                                            # one split cycle
diagram.add_cycle("Two-stage", states, loops=[[1, 2, 7, 8, 1], [3, 4, 5, 6, 3]])  # two closed loops
```

## From models

```python
from coolplot.thermo.cycles import simple_compression, two_stage, rankine

cycle = simple_compression("R290", T_evap_C=-5, T_cond_C=45, dT_sh_K=5, dT_sc_K=2, eta_is=0.7)
cycle.result["COP_heating"]          # results in SI units
diagram.add_cycle(cycle)
diagram.add_cycle(two_stage("R290", -30, 45, intermediate="economizer"))
diagram.add_cycle(rankine("Water", p_high_Pa=40e5, p_low_Pa=0.1e5, T_live_C=400))
```

For blends the models take the evaporating and condensing temperatures
as dew points (EN 12900).

## Change, read, remove

`add_cycle` with the same name replaces the cycle and redraws only it.
`cycle_states(name, units=...)` returns the computed states,
`move_cycle_state(name, number, x, y)` moves one state (states that
follow it with `"via"` move along), `remove_cycle(name)` removes it.
Without a zoom window the axes grow so that every state is inside the
frame. `numbers=False` hides the state numbers; `line_style` and
`marker_style` override the theme.

States you computed yourself, for example with
`coolplot.thermo.process_path`, go into `add_cycle` as `StatePoint`
values. The older `set_process(name, line_states, marker_states)` still
works and warns; it goes in 1.0.
