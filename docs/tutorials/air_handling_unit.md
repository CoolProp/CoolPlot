# A psychrometric chart for an air handling unit

Outdoor air in summer is cooled and dehumidified on a cooling coil and
reheated to the supply temperature. Drawn on a psychrometric chart with
the air states read back.

## The chart

```python
from coolplot import PsychrometricChart

chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))   # deg C and g/kg, sea level
chart.title = "Air handling unit, summer"
chart.set_default_lines()      # RH every 10 %, Twb every 5 deg C, h every 10 kJ/kg, v every 0.02 m3/kg
chart.show()
```

A psychrometric chart shows humid air at one total pressure (`p=` in
bar, sea level by default): dry-bulb temperature over humidity ratio,
with lines of relative humidity, wet-bulb temperature, specific enthalpy
and specific volume, the last three per kg of dry air.

## The process

```python
chart.add_cycle("Summer", [
    {"T": 32.0, "RH": 50.0},     # outdoor air
    {"T": 13.0, "RH": 95.0},     # after the cooling coil
    {"T": 20.0, "W": 8.9},       # after the reheater, same humidity ratio
], closed=False)
chart.save("ahu_summer.png")
```

Air states are given by any two of T, W, RH, Twb, Tdp, h and v, in the
chart's units, and joined by straight lines; `closed=False` leaves the
chain open, because this is a process, not a cycle.

## Loads from the states

```python
states = chart.cycle_states("Summer", units="engineering")   # kJ/kg dry air, g/kg
h = {n: s["h"] for n, s in states.items()}
W = {n: s["W"] for n, s in states.items()}
m_dot_kg_s = 2.5                                              # dry air
Q_dot_cool_kW = m_dot_kg_s * (h[1] - h[2])
Q_dot_heat_kW = m_dot_kg_s * (h[3] - h[2])
m_dot_cond_kg_s = m_dot_kg_s * (W[1] - W[2]) / 1e3
```

## Winter, on the same chart

```python
chart.add_cycle("Winter", [{"T": -5.0, "RH": 80.0}, {"T": 20.0, "via": "isobaric"},
                           {"T": 20.0, "RH": 40.0}], closed=False)
```

Heating keeps the humidity ratio (a horizontal line), then a humidifier
raises it. The second process gets its own colour and legend entry.
