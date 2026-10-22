# Labels

```python
diagram.set_lines("T", num=12, rounding=True, labels=True)
diagram.settings = diagram.settings.with_(labels={"mode": "edge"})
```

| mode | Where labels go |
|------|-----------------|
| `"rails"` (default, since 1.2) | the bare values of each family in a row along one edge: outside the frame at the top and on the right, with a tick where the line leaves, or just inside the frame, turned along the lines; symbol and unit are in the legend |
| `"edge"` | the full label ("T=20 deg C") just inside the frame where each line leaves the chart, rotated along the line (the default before 1.2) |
| `"margin"` | outside the frame like a second set of tick labels (vertical at the top), never touching the data |
| `"inline"` | at `position` along each line |

On rails each family takes the row where most of its labels fit, and
when not all fit it drops whole levels of values: a family stepped by 10
keeps the multiples of 100 longest, then those of 50 and 20, so the row
stays regular. Lines that leave through another edge
get a second row; lines that end inside the chart get a label near
their end. The legend reads "Temperature T / deg C", or "Specific
entropy s at T_sat / deg C" for lines labelled by their saturation
states. With legend
location "auto" (the default) it sits inside the plot area, in the corner
where it covers the fewest cycle points, then the fewest lines; on a small
page, where it would cover more than a quarter of the plot area, it goes
outside on the right.

In rails and edge mode every cycle keeps a zone of `keep_out_pt` points
free of labels, no two labels overlap, and a label that does not fit is
left out. Labels keep their place from one redraw to the next while it
stays free, so they do not jump while a cycle is dragged.

The look before 1.2, full labels and the legend outside:

```python
diagram.settings = diagram.settings.with_(labels={"mode": "edge"})
legend = diagram.theme.axes.legend.with_(location="outside right")
diagram.theme = diagram.theme.with_(axes=diagram.theme.axes.with_(legend=legend))
```

Other fields of `LabelSettings`: `edges` (the preferred frame edges per
family, e.g. `{"T": ("top", "right")}`), `fallback` (allow positions
further along the line when the edge is taken), `every` (label every
n-th line), `digits`, `show_units`, `tick_digits`.

Labels are drawn in the theme's label colour (ink). To match each label
to its family at a glance, draw it in the colour of its line instead:

```python
diagram.theme = diagram.theme.with_(isoline_label_color="line")
```

The label keeps its halo, and a colour set with `set_line_style` carries
over to the labels of that family. Light line colours, such as the yellow
of the fourth family in the default theme, are harder to read as text.

Labels are laid out for the size of the plot area. `diagram.draw()` and
`save()` take it from the plotting library; if you drive a renderer
yourself, pass it: `renderer.sync(diagram.update_scene(renderer.plot_size_pt()))`.
How positions are chosen is in {doc}`../explanation/label_placement`.
