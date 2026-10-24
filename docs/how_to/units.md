# Units

## Choose a unit system

```python
diagram = PropertyDiagram("R290", "ph", units="engineering")
diagram.units = "SI"        # later: no new property calculations, the lines are redrawn
```

| Name | Temperature | Pressure | Energy | Humid air |
|---|---|---|---|---|
| `"SI"` | K | Pa | J/kg, J/kg/K | kg/kg, fraction |
| `"KSI"` | K | kPa | kJ/kg, kJ/kg/K | kg/kg, fraction |
| `"engineering"` | deg C | bar | kJ/kg, kJ/kg/K | g/kg, % |
| `"IP"` | deg F | psi | Btu/lb, Btu/lb/R | grains/lb, % |

Every value you pass to a chart method is in the chart's units, and so
is every value a chart returns. `units=` on a call names another system
for that call only: `diagram.add_cycle("measured", states, units="SI")`.
`"EUR"`, the name of `"engineering"` before 0.5, is refused in calls
since 1.0; the constant `coolplot.EUR` still works with a warning until 2.0.

## Make your own

```python
from coolplot import ENGINEERING, Unit
units = ENGINEERING.with_unit("p", Unit("MPa", 1e-6), name="engineering-MPa")
diagram.units = units
```

A `Unit` is `Unit(label, scale, offset, difference_label)`: the shown
value is `SI * scale + offset`. The last field names the unit of a
*difference* of two values, which the offset does not apply to: a
superheat is 5 K, not 5 deg C. `ENGINEERING.describe_difference("T", 5.0)`
writes "5 K".

Labels stay plain ASCII in code ("deg C", "kg/m3"). Since 1.4 the chart
writes them with their own characters, "&deg;C" and "kg/m&sup3;", also in a
custom unit with the same label; `labels={"symbols": "ascii"}` keeps the
plain letters (the how-to on labels).

## Gauge pressure

```python
from coolplot.core.units import BAR_GAUGE, PSI_GAUGE
diagram.units = ENGINEERING.with_unit("p", BAR_GAUGE)   # bar(g), relative to 1.01325 bar
```

A pressure axis in a gauge unit is drawn linear: a logarithmic scale is
impossible when vacuum is negative.

## Read states in units

A fluid state holds T, p, h, s, rho, v (= 1/rho), u and Q, in SI.

```python
diagram.units = "engineering"                    # back from the examples above
state = diagram.state_at(400, 5)                 # h = 400 kJ/kg, p = 5 bar in the chart's units
state.describe("engineering")                    # "T = 1.729 deg C, p = 5 bar, h = 400 kJ/kg, ..."
state.in_units("IP")                             # a dict
diagram.cycle_states("Heat pump", units="engineering")   # every state of a cycle
```

A state can be given by v as well: `{"T": 20, "v": 0.05}`.

## In the gallery

A chart and a cycle in IP units: {doc}`../gallery/ip_units`.
