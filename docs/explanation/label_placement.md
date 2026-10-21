# How labels are placed

Printed charts write the values of a family of lines in a row along an
edge, where the lines leave the chart, and say once what the numbers
are. CoolPlot does that by default (`"rails"` mode, since 1.2), and it
has to do it again whenever the lines, the window or a cycle change,
without labels jumping about. The older `"edge"` mode writes the full
label of each line where it leaves the chart.

## Rails

1. A rail is a row of labels along one edge. The outer rails sit outside
   the frame, at the top and on the right (the bottom and the left carry
   the tick labels): a tick on the frame marks the line, the bare value
   stands next to it, horizontal, or vertical at the top when that fits
   more labels. The inner rails sit just inside the frame on every edge;
   there a label is turned along its line and moved along it until the
   corner of its box nearest to the edge touches the rail, so that the
   row looks straight whatever the angles. A second inner rail lies a
   little further in.
2. Each family takes the rail where most of its labels fit; outer rails
   win a tie, and no two families share a rail. Lines of a family that
   do not reach its rail (relative humidity leaves a psychrometric chart
   at the top and on the right) may take a second free rail. A family
   that fits on no rail, because its lines end inside the chart, gets a
   label near the end of each line.
3. When not all labels of a family fit, whole levels of values go: the
   values that are multiples of ten steps of the family stay longest,
   then those of five and two steps. The same level holds for the whole
   row. Where even the coarsest level does not fit, because one of its
   labels is blocked, every second, third ... label along the row stays,
   so evenly spaced values stay evenly spaced (values that are not, such
   as 1, 2, 5, 10, 20, keep their coarsest ones).
4. Labels inside the frame keep clear of the cycles (`keep_out_pt`), of
   each other, of the ticks of the outer rails, of the legend and of the
   badge. The legend and the badge get their corners first: an automatic
   legend takes a corner where it covers no point of a cycle, the one
   that covers the fewest isoline points, and goes outside on the right
   when no corner is free or it would cover more than a quarter of the
   plot area; an automatic badge takes the emptiest of the corners left.
5. A rail that held labels of a family in the previous layout counts one
   label more for it, so a family keeps its rails unless another fits
   more than one label more, and a label that stays where it was is the
   same item as before, so the renderer redraws nothing.

## Edge labels

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
