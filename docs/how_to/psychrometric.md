# Draw air processes on a psychrometric chart

A psychrometric chart shows humid air at one total pressure: humidity
ratio over dry-bulb temperature, with lines of relative humidity, wet-bulb
temperature, enthalpy and specific volume. Values are in the chart's units:
deg C, g/kg, % and kJ/kg with `units="engineering"` (the default).

```python
from coolplot import PsychrometricChart

chart = PsychrometricChart(T_range=(-10, 40), W_range=(0, 20))   # sea level
chart.set_default_lines()
```

`p=0.9` sets another total pressure (in bar with "engineering").

## The Mollier h,x chart

The chart used in Europe (DIN 1946, VDI 4670) puts the humidity ratio,
called x, across, and a temperature scale up:

```python
chart = PsychrometricChart(T_range=(0, 40), W_range=(0, 20), style="mollier")
chart.set_default_lines()
```

The scale is linear in the specific enthalpy, Thx = 0 deg C + (h - r0 x)
/ cp_a with r0 = 2500 kJ/kg and cp_a = 1.006 kJ/kg/K, so the lines of
constant enthalpy are straight and fall to the right, and a straight line
is still a mixing line. The isotherms rise slightly with x, since moist air
holds more enthalpy at the same temperature. For dry air the scale is the
dry-bulb temperature; `T_range` is its range. The relative humidity is
called phi. Everything else is as on the psychrometric chart: states,
processes, zones and labels take the same keys (`W` for x, `RH` for phi),
and every state also holds `Thx`. The default lines add isotherms.

## Processes

An air process is a cycle that does not close: `add_cycle(name, states,
closed=False)`. Each state is given by two of T, W, RH, Twb, Tdp, h and v,
or by one property and `"via"`, which keeps a property of the state before
it. Paths are drawn straight.

| Process | State after it |
|---------|----------------|
| Sensible heating or cooling (a coil above the dew point) | `{"T": 28, "via": "sensible"}`, same humidity ratio |
| Cooling and dehumidification | two properties, e.g. `{"T": 13, "RH": 95}` off the coil |
| Evaporative cooling, desiccant dehumidification | `{"T": 18, "via": "isenthalpic"}`, same enthalpy |
| Steam humidification | `{"RH": 50, "via": "isothermal"}`, same temperature |

`"via": "isobaric"` does not work for humid air: every state is at the
chart's total pressure, so the pressure does not fix a second property.

```python
cooling_states = [{"T": 32, "RH": 50},              # 1 outdoor air
                  {"T": 13, "RH": 95},              # 2 off the cooling coil
                  {"T": 20, "via": "sensible"}]     # 3 after reheating
chart.add_cycle("Cooling", cooling_states, closed=False)
states = chart.cycle_states("Cooling")    # StatePoints in SI units, by state number
```

## Mixing two air streams

`chart.mix(a, b, m_dot_a_kg_s, m_dot_b_kg_s)` gives the state after two
streams mix adiabatically, from the water and energy balances per kg of dry
air. Only the ratio of the dry-air flows matters. The result goes into
`add_cycle` as it is:

```python
outdoor, room = {"T": 32, "RH": 40}, {"T": 25, "RH": 50}
mixed = chart.mix(outdoor, room, m_dot_a_kg_s=0.6, m_dot_b_kg_s=1.4)
summer_states = {1: outdoor, 2: room, 3: mixed, 4: {"T": 13, "RH": 95}}
summer_loops = [[1, 3], [2, 3, 4]]     # outdoor and return air into the mix, then the coil
chart.add_cycle("Summer", summer_states, loops=summer_loops)
```

A mix that would hold more water than saturated air (fog) is refused.
`chart.state({"T": 13, "RH": 95})` gives a single state, for example to
compute a coil's apparatus dew point or a wet-bulb temperature.

## Several processes on one chart

Each `add_cycle` adds a process with its own legend entry. The default
theme has three line styles for processes and uses them in turn; give each
process its own `line_style` and `marker_style` when there are more, or to
colour them:

```python
from coolplot import LineStyle, MarkerStyle

red = dict(line_style=LineStyle(color="#c0392b", width_pt=2.0, casing_color="white", casing_width_pt=1.5),
           marker_style=MarkerStyle(size_pt=6.0, face_color="#c0392b", edge_color="white"))
chart.add_cycle("Summer", summer_states, loops=summer_loops, **red)
```

## Labels on states

`labels={number: text}` writes a text next to a state, after its number
("2: cooling coil -35.1 kW"); with `numbers=False` the label stands alone.
A label that uses computed states (a duty, a sensible heat ratio) comes from
`cycle_states`; adding the cycle again under its name replaces it:

```python
m_dot_kg_s = 1.0                       # dry air through the coil
states = chart.cycle_states("Cooling")
Q_dot_coil_kW = m_dot_kg_s * (states[2].h - states[1].h) * 1e-3
chart.add_cycle("Cooling", cooling_states, closed=False,
                labels={2: "cooling coil {0:.1f} kW".format(Q_dot_coil_kW)})
```

## Comfort zones

`chart.add_zone(name, T_range, RH_range)` outlines a region of temperature
and relative humidity, for example a comfort zone. Its humidity edges follow
the lines of constant relative humidity; it has no markers or numbers, and
`label` writes a text at its corner of lowest temperature and highest
humidity. It is a cycle like any other: `remove_cycle(name)` removes it, and
it is saved with the chart.

```python
chart.add_zone("Comfort zone", T_range=(20, 26), RH_range=(30, 60), label="comfort zone",
               line_style=LineStyle(color="#7f8c8d", width_pt=1.5, dash="dashed"))
```

The gallery ({doc}`../gallery/index`) has four worked examples: the basic
processes from one state, summer and winter operation of an air handling
unit, evaporative cooling in a dry climate, and an air handling unit on the
Mollier h,x chart.
