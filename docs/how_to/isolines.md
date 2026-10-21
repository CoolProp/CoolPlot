# Isolines

## Choose the lines

```python
diagram.set_lines("T", values=[-20, 0, 20, 40])        # explicit values, in the chart's units
diagram.set_lines("T", num=8)                          # 8 lines, evenly over the region
diagram.set_lines("T", num=8, rounding=True)           # round values: -50, 0, 50, 100 deg C
diagram.set_lines("s", num=6, range=(1.0, 2.5))        # 6 lines between 1.0 and 2.5 kJ/kg/K
diagram.set_default_lines()                            # every family the diagram offers
diagram.remove_lines("p")
diagram.line_sets()                                    # what is set
```

With `rounding=True` the values are round numbers in the chart's units
with an even step (25 deg C, or 1-2-5 per decade on a log axis), as
many as come close to `num`. Lines of a quantity that is an axis of the
diagram (isobars in a p-h chart) are not offered: they are the grid.

Which families a diagram offers, and in which quantity each is stepped,
is in {doc}`../reference/tables`.

## The saturation curve

A chart of a fluid with a critical point draws its saturation curve (the
lines of quality 0 and 1, the dome) whatever lines are set, also when the
lines of constant quality leave out 0 and 1 or are not set at all; a
psychrometric chart draws the line of 100 % relative humidity. Since 1.2:

```python
diagram.set_lines("Q", values=[0.2, 0.5, 0.8])   # the dome stays
diagram.show_saturation = False                  # hide the saturation curve
```

Incompressible liquids have no saturation curve. A chart saved before 1.2
reads with `show_saturation = None`: there the quality (or humidity)
values decide, as they did then.

## Place lines through saturation states

Engineers read a log(p)-h chart at round evaporating and condensing
temperatures. `at_saturation` places a family through saturation states
at an even step instead of at round values of its own:

```python
diagram.set_lines("s", at_saturation={"T": 10}, labels=True)           # isentropes through the saturated
                                                                       # vapour every 10 K: 0, 10, 20 deg C
diagram.set_lines("rho", at_saturation={"T": 20, "range": (-40, 60)})  # isochores every 20 K, -40 to 60 deg C
diagram.set_lines("T", at_saturation={"p": 2})                         # isotherms every 2 bar of saturation pressure
diagram.set_lines("s", at_saturation={"T": 10, "Q": 0})                # through the saturated liquid
diagram.set_lines("s", at_saturation={"T": 10, "label": "saturation"}) # labels "T_sat=0 deg C"
```

The steps are round in the chart's units (every 10 K in a deg C chart
gives 0, 10, 20 deg C; in an IP chart a step of 20 gives 0, 20, 40 deg F)
and stop just below the critical point. Each line is labelled with its
own value, like any other line (`s=2.321 kJ/kg/K`, four significant
digits, since the values are not round). `"label": "saturation"` names the
saturation state instead, `T_sat=0 deg C` for the vapour side,
`T_sat,liq=0 deg C` for the liquid side. For a blend, `"Q": 1` is the dew point and `"Q": 0`
the bubble point at that temperature. A line placed this way is the same
line, and the same cache entry, as one given by its value.

Only fluids with a saturation curve can place lines this way, not
incompressibles or humid air; `set_lines` says so at once, as it does for
a step that would give more than 200 lines. A saturation state CoolProp
cannot compute (a blend close to its critical point) has no line, with a
warning. The steps end at the critical point: for a blend, dew states
between the critical point and the highest dew temperature are left out.
The step is kept in SI units and rounded in the chart's units, so a spec
made in deg F and drawn in deg C places its lines on multiples of the
converted step.

## The region the lines cover

`tp_limits` is the temperature and pressure region in which lines are
computed: a preset (`"DEF"`, `"ACHP"` for refrigeration, `"ORC"`,
`"NONE"`), four SI values `[T_min_K, T_max_K, p_min_Pa, p_max_Pa]`, or a
`TpLimits` with bounds absolute or relative to the saturation range:

```python
from coolplot import TpLimits, Relative
diagram.tp_limits = TpLimits(T_min=233.15, T_max=Relative(1.2), p_min=1e5, p_max=Relative(2.0))
```

The axes show the ranges of the two axis quantities over that region.
`diagram.set_view(x_limits, y_limits)` zooms into it (in the chart's
units) without any new calculation; `set_view()` resets.

## Resolution

`Settings.calc.points` (250) sets the resolution of a line: a straight
line that crosses the whole chart gets about `points / 2` points, bends
get more, see {doc}`../explanation/numerics`.
`set_lines(..., points=...)` sets it for one family. For a chart that is
dragged interactively use the `"interactive"` settings preset (60 points)
and switch back for the final picture.

## Through the dome

Where a line enters or leaves the two-phase region, the saturation state
is part of the line, so the kink sits exactly on the dome. An isotherm or
isobar is followed through the dome in vapour quality: a straight tie
line for a pure fluid, the temperature glide for a blend.

## Style one family

```python
diagram.set_line_style("T", color="#000000", width_pt=1.0)
diagram.set_line_style("T")                                   # back to the theme
```
