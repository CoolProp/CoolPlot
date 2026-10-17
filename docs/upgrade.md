# Upgrade guide

## From 0.6 to 0.7

* CoolProp 8.0 or later is required.
* Lines have a different number of points: the resolution
  (`Settings.calc.points`) is about the number of points of a line that
  crosses the whole chart, bends get more and straight parts fewer. Code
  that relied on 250 points per line reads `len(curve.x)` instead.
* Lines are cut at the edges of the axes instead of continuing outside;
  a line whose value sits at the very edge of its range is left out.
* Fluid states carry `v` (specific volume); `STATE_KEYS` has eight
  entries. A state saved before 0.7 is completed when it is loaded.
* `Unit` has a fourth field, the label of a difference; the three-field
  form still reads.
* `PropertyError` has `reason` and `limits`; the message says what is
  wrong before CoolProp's own words.

## From 0.4 to 0.5

The chart vocabulary is one verb per operation. The old names warn and
go in 1.0:

| Old | New |
|---|---|
| `set_isolines`, `set_default_isolines`, `remove_isolines` | `set_lines`, `set_default_lines`, `remove_lines` |
| `isoline_sets`, `set_isoline_style` | `line_sets`, `set_line_style` |
| `set_process(name, line_states, marker_states)` | `add_cycle(name, states)`, which computes the paths between the states itself |
| `remove_process` | `remove_cycle` |
| psychrometric `add_process`, `move_process_state`, `process_states`, `remove_process` | `add_cycle(..., closed=False)`, `move_cycle_state`, `cycle_states`, `remove_cycle` |
| `savefig` | `save` |
| `units="EUR"` | `units="engineering"` |
| `rankine(eta_turbine=..., eta_pump=...)` | `rankine(eta_is_turbine=..., eta_is_pump=...)` |

## From 0.1 (the legacy API) to 0.2 and later

Version 0.2 replaced the legacy API (`from CoolPlot.Plot import
PropertyPlot`). The table gives the equivalents:

| Legacy | Now |
|---|---|
| `PropertyPlot("HEOS::R290", "ph", unit_system="EUR", tp_limits="ACHP")` | `PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")` |
| `plot.calc_isolines(CoolProp.iQ, num=11)` | `diagram.set_lines("Q", num=11)` |
| `plot.calc_isolines()` | `diagram.set_default_lines()` |
| `plot.draw_process(states)` | `diagram.add_cycle("name", states)` |
| `plot.show()`, `plot.savefig("x.png")` | `diagram.show()`, `diagram.save("x.png")` |
| `plot.axis`, `plot.figure` | `MatplotlibRenderer(ax=ax)` and `renderer.sync(diagram.update_scene())` |

If you depend on the legacy API, stay on the last legacy release with
`pip install "coolplot<0.2"`.
