# A first log(p)-h chart

The chart engineers in refrigeration reach for first: pressure
(logarithmic) over specific enthalpy, with the saturation dome, lines of
constant temperature, entropy and quality, and a cycle on top.

## The fluid and the diagram

```python
from coolplot import PropertyDiagram

diagram = PropertyDiagram("R290", "ph", units="engineering", tp_limits="ACHP")
diagram.show()
```

That shows the dome of propane and nothing else: a chart starts empty
apart from the saturation curve. `units="engineering"` means that every
number you give or read is in deg C, bar and kJ/kg. `tp_limits="ACHP"`
is a region of temperature and pressure that fits refrigeration;
`"DEF"` is wider, `"ORC"` fits organic Rankine cycles.

## Lines

```python
diagram.set_lines("Q", num=11, labels=True)                 # quality 0, 0.1, ..., 1
diagram.set_lines("T", num=12, rounding=True, labels=True)  # isotherms at round temperatures
diagram.set_lines("s", num=10, rounding=True, labels=True)  # isentropes
diagram.show()
```

`num` is how many lines you would like; with `rounding=True` the values
are round in the chart's units (every 20 deg C, say) and the count comes
as close to `num` as round values allow. `labels=True` writes the value
of each line at the edge of the chart, where printed charts have it.
`set_default_lines()` would have added every family the diagram offers
in one go.

## A cycle

```python
diagram.add_cycle("Heat pump", [
    {"p": 3.0, "T": 0.0},                               # 1 compressor inlet
    {"p": 15.0, "via": "compression", "eta_is": 0.7},   # 2 compressor outlet
    {"p": 15.0, "Q": 0.0},                              # 3 condenser outlet
    {"p": 3.0, "via": "isenthalpic"},                   # 4 after the valve
])
```

State 1 is given by two properties. State 2 follows from state 1 by a
compression to 15 bar with an isentropic efficiency of 0.7; state 3 is
saturated liquid at the condenser pressure; state 4 follows from 3 by
throttling, which keeps the enthalpy. The condenser path 2 to 3 is an
isobar, so it bends where it meets the dome, and the markers are
numbered. `cycle_states` gives the numbers:

```python
for number, state in diagram.cycle_states("Heat pump", units="engineering").items():
    print(number, state)
```

## Save it

```python
diagram.title = "R290 heat pump"
diagram.save("R290_ph.png")      # or .pdf, .svg
```

The picture on the landing page was made this way, with
`set_default_lines(labels=True)` and a cycle from the ready-made model
`coolplot.thermo.cycles.simple_compression`.
