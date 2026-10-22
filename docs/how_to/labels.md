# Labels

```python
diagram.set_lines("T", num=12, rounding=True, labels=True)
diagram.settings = diagram.settings.with_(labels={"mode": "edge"})
```

| mode | Where labels go |
|------|-----------------|
| `"edge"` (default) | just inside the frame where each line leaves the chart, rotated along the line, as printed refrigerant charts do |
| `"margin"` | outside the frame like a second set of tick labels (vertical at the top), never touching the data |
| `"inline"` | at `position` along each line |

In edge mode every cycle keeps a zone of `keep_out_pt` points free of
labels, no two labels overlap, and a label that does not fit is left out.
A label keeps its place from one redraw to the next while that place
stays free, so labels do not jump while a cycle is dragged.

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
