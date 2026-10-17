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

`Settings.calc.points` (250) sets the resolution of a line: about the
number of points a line gets that runs across the whole chart; bends get
more points and straight parts fewer, see {doc}`../explanation/numerics`.
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
