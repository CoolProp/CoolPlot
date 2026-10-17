# Interactive applications with matplotlib

A chart recomputes only what changed and redraws only what changed. The
loop of an application:

```python
from coolplot.render.mpl import MatplotlibRenderer
from coolplot.interaction import Interaction

renderer = MatplotlibRenderer(ax=ax)                  # your axes, or none for a new figure
Interaction(diagram, renderer, on_hover=lambda state, event: label.set_text(state.describe("engineering")))

def on_change(T_evap_C, T_cond_C):
    diagram.add_cycle(simple_compression(diagram.fluid, T_evap_C, T_cond_C, name="Heat pump"))
    report = renderer.sync(diagram.update_scene(renderer.plot_size_pt()))
    # report.added, report.updated, report.unchanged say what was touched
```

Moving a cycle recalculates no isoline and redraws only the cycle (and
the labels it pushes away). Changing units or the theme recalculates
nothing. `diagram.state_at(x, y)` gives the full state under the mouse.

`Interaction` handles the usual cases: zooming and panning with the
toolbar lay out the labels for the new window, and dragging a state
marker moves that state (it is then given by the two axis quantities;
states that follow it with `"via"` move along).
`diagram.move_cycle_state(name, number, x, y)` does the same from code.
For other behaviour, handle the events yourself: `renderer.connect(callback)`
delivers `Hover`, `Click`, `DragStart`, `Drag`, `DragEnd`, `ViewChanged`
and `Resized` from `coolplot.core.events`, in the units of the axes.

While a state is dragged, `diagram.settings = diagram.settings.with_(calc="interactive")`
draws with fewer points; `with_(calc="screen")` goes back to full
detail. Several charts of the same fluid share their cache with
`PropertyDiagram(..., engine=other.engine)`.

`examples/interactive_cycle.py` is a complete application with sliders;
see it in the {doc}`../gallery/index`.
