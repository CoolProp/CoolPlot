# How labels are placed

Printed refrigerant charts write the value of a line at the edge of the
chart where the line leaves it, rotated along the line. CoolPlot does
the same by default (`"edge"` mode), and it has to do it again whenever
the lines, the window or a cycle change, without labels jumping about.

## The rules

1. The part of each line inside the frame is found, with the edge it
   enters and leaves through. Each family prefers two edges (isotherms
   the top and the right in a p-h chart, say); the preference is in the
   {doc}`../reference/tables`.
2. A label candidate sits just inside the frame at a preferred crossing,
   rotated along the line, and may slide inward three times if that spot
   is taken. With `fallback` on, positions at a quarter, a half and three
   quarters of the visible line come after that.
3. Labels are placed one family after another in order of importance
   (the first value of a family before the tenth), each taking its best
   free candidate. A candidate is free when its box does not overlap a
   placed label, the frame, or a keep-out zone around a cycle
   (`keep_out_pt` points on either side of the cycle's line and
   markers).
4. A label that stays free where it was keeps its place, and the
   renderer is told nothing about it: it is the same item as before.

Margin mode (`"margin"`) puts the labels outside the frame instead, like
a second set of tick labels, vertical at the top and the bottom so that
closely spaced lines still get one each. Inline mode writes labels along
the line at a given position, as older versions did.

## Why the layout needs the plot size

Whether two labels overlap depends on their size on the page, not on
the data. The layout therefore runs in points, for the plot area the
plotting library reports (`renderer.plot_size_pt()`); `draw()` and
`save()` ask for it, and if the area changes when the picture is drawn
the layout runs once more. A chart drawn into two windows of different
size gets two different layouts.
