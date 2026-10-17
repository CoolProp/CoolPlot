# The pipeline

What happens between `diagram.set_lines(...)` and a picture, in five
steps, each a layer of the package that may only use the layers before
it:

1. **The spec** (`coolplot.spec`): what the chart shows, as plain data
   that saves to JSON: the fluid, the diagram type, the units, the region,
   the families of lines, the cycles, the settings. A chart method
   replaces the spec by a changed copy; nothing is changed in place.
2. **The plan** (`coolplot.engine`): which lines the spec needs, each a
   request with the quantity, the value in SI and the resolution. Two
   specs that need the same line produce the same request.
3. **The engine** (`coolplot.engine`, `coolplot.thermo`): computes the
   requested lines with CoolProp, in SI units, and caches them by fluid,
   region and request. A background engine computes them on worker
   threads or processes.
4. **Compose** (`coolplot.compose`): the computed lines, the spec and
   the theme become the scene, a list of items (lines, markers, texts)
   with ids, roles, concrete styles and coordinates in the chart's units.
   The label layout runs here.
5. **Render** (`coolplot.render`): a plotting library draws the scene.
   The renderer remembers what it drew under which id and, on the next
   picture, adds, updates or removes only the items that changed.

Everything that talks to CoolProp is in `coolplot.thermo`, everything
that talks to matplotlib in `coolplot.render.mpl`, so the package can be
used without either. The layer rules are checked by a test.
