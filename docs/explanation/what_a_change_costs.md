# What a change costs

A chart keeps three things apart: the property calculations (slow, in
SI units, cached), the description of what is drawn (the "scene": every
line, marker and text with its style, in the chart's units), and the
drawing itself, done by a plotting library. A change to a chart touches
as little of that chain as it can:

| Change | Recomputed | Redrawn |
|---|---|---|
| another unit system | nothing | every item, in place |
| another theme, a line style | nothing | the restyled items |
| moving a cycle state | the cycle's path | the cycle, and labels it pushes away |
| zooming (`set_view`) | nothing | the labels, laid out for the new window |
| adding a family of lines | those lines | those lines and the labels |
| another region (`tp_limits`) | every line | every line |

The lines of a fluid are cached by fluid, region, quantity and value,
so a line computed once is never computed again in the same session,
whatever the units or the theme, and several charts of the same fluid
can share the cache (`engine=`). Cycles are cached in the same way.

The settings of a chart are grouped by what a change costs:

| Part | Examples | A change costs |
|------|----------|----------------|
| `calc` | `points`, `saturation_points`, `solver`, `critical_margin` | recalculating the affected lines |
| `look` | the theme | restyling only |
| `labels` | `mode`, `keep_out_pt`, `digits` | a new label layout only |
| `page` | `width_pt`, `height_pt`, `font_scale` | page layout only |

```python
diagram.settings = diagram.settings.with_(calc={"points": 100}, look="dark", page={"font_scale": 1.2})
diagram.settings = diagram.settings.with_(calc="interactive")   # few points while dragging, rest unchanged
```

Everything about a chart (fluid, axes, units, lines, cycles, settings)
is one record, `diagram.spec`, which saves to and loads from JSON
({doc}`../reference/contracts`). A chart made from the same record draws
the same picture.
