# Contracts: the data that crosses the layers

CoolPlot is a pipeline of plain data. Three records cross its layer
boundaries, and each one can be written as JSON and read back:

| Record | Written by | Read by | Python |
|---|---|---|---|
| the chart spec | the facade (`Chart`) | engine, compose | `DiagramSpec.to_dict` / `from_dict` |
| the curve record | thermo (a property provider) | engine cache, compose | `Curve.to_dict` / `from_dict` |
| the scene | compose | every renderer | `Scene.to_dict` / `from_dict` |

These are the contracts that a port of any part of the pipeline to
another language has to honour (contributing/v1_review.md, section 6): a C++
numerics library produces curve records, a C++ presentation library
turns a spec plus curve records into a scene, and a renderer in any
language draws a scene. `tests/test_contracts.py` checks that every
record round-trips through JSON without change.

All numbers are SI (K, Pa, J/kg, J/kg/K, kg/m3, kg water per kg dry air,
m3/kg dry air, fractions) except in the scene, whose coordinates are in
the display units the spec asked for. Non-finite values are written as
`null` and read back as NaN (an infinity does not survive the trip).
CoolPlot's own strings are ASCII; user texts (titles, cycle names) pass
through as given. Keys of quantities are those of
`coolplot.core.quantities`: `T`, `p`, `h`, `s`, `rho`, `v`, `u`, `Q` for
fluids, plus `W`, `RH`, `Twb`, `Tdp`, `v` for humid air.

## 1. The chart spec

One record describes a property diagram and a psychrometric chart alike;
`diagram` carries the chart kind.

```js
{
  "fluid": {"backend": "HEOS", "components": ["R32", "R125"], "fractions": [0.7, 0.3],
            "basis": "mole", "interactions": []},
  "diagram": "ph",
  "units": "engineering",
  "limits": {"T_min": {"relative": 1.01}, "T_max": {"relative": 2.25}, "p_min": 25000.0, "p_max": null},
  "settings": {"calc": {...}, "look": {...}, "labels": {...}, "page": {...}},
  "isolines": [{"key": "T", "values_SI": null, "num": 15, "range_SI": null, "rounding": true,
                "points": null, "labels": true}],
  "cycles": [{"name": "heat pump", "states": [[1, {"props": [["p", 300000.0], ["T", 273.15]]}],
                                              [2, {"props": [["p", 1500000.0]], "via": "compression",
                                                   "eta_is": 0.7}]],
              "loops": [[1, 2, 3, 4, 1]], "paths": [], "numbers": true, "steps": 20,
              "line_style": null, "marker_style": null}],
  "processes": [],
  "style_overrides": {"T": {"color": "#0000ff"}},
  "view_SI": [null, null],
  "title": ""
}
```

* `fluid`: a CoolProp fluid as above (kind "fluid"), or humid air at one
  total pressure, `{"model": "humid_air", "p_Pa": 101325.0}` (kind
  "humid_air").
* `diagram`: the name of a diagram type, vertical axis first: `ph`, `Ts`,
  `hs`, `ps`, `prho`, `Trho`, `pT` for fluids, `WT` (or `psychrometric`)
  for humid air. The kind of the diagram has to match the fluid.
* `units`: a name (`SI`, `KSI`, `engineering`, `IP`) or
  `{"name": ..., "units": {"p": ["bar", 1e-5, 0.0], ...}}` with
  `[label, scale, offset]` per quantity (display = SI * scale + offset),
  and an optional fourth element, the label of a difference in the
  quantity (`["deg C", 1.0, -273.15, "K"]`; the label itself if absent).
* `limits`: for fluids a T-p box, each bound a number, `null` (the limit
  of the equation of state) or `{"relative": f}` (f times the saturation
  range); for humid air absolute bounds on the axis quantities,
  `{"bounds": {"T": [263.15, 323.15], "W": [0.0, 0.03]}}`.
* `settings`: see `coolplot.spec.settings`; `look` is a theme name or a
  theme record (the how-to on themes).
* `isolines`: one entry per family, in drawing order. `values_SI` lists
  explicit values, otherwise `num` values are spread over `range_SI` (or
  the calculation domain), round values if `rounding`.
* `cycles`: numbered states, each given by a full state (`{"state":
  {"T": ..., "p": ..., ...}}`, holding every quantity of the chart's
  fluid or of humid air, in any order), two properties, or one property and
  `via` (`coolplot.core.cycle.VIA_KINDS`); `loops` are chains of state
  numbers, `paths` lists `[[from, to], kind]` for connections not drawn
  with "auto" (`PATH_KINDS`). Air processes on a psychrometric chart are
  cycles whose paths are straight.
* `processes`: lines through complete states, kept for `set_process`
  until it is retired (see contributing/v1_plan.md, D4).
* `style_overrides`: `LineStyle` field changes per family, on top of
  the theme.
* `view_SI`: `[x_limits, y_limits]`, each `null` or `[min, max]`.

## 2. The curve record

One line of constant value, in SI units, as the thermo layer computes it
and the engine caches it (`coolplot.thermo.isolines.Curve`).

| Field | Type | Meaning |
|---|---|---|
| `x`, `y` | arrays of float | the axis quantities of the chart; `null` (NaN) where a point could not be computed, which renderers draw as a gap |
| `n_failed` | int | points that could not be computed |
| `n_fallback` | int | points the tracer handed back to a plain flash |
| `n_inserted` | int | saturation states inserted where the line crosses the phase boundary |
| `method` | str | `"flash"`, `"tracer"` or `"envelope"` |
| `reason` | str | why a line could not be computed at all (then `x` and `y` are empty), or why it has fewer than two points |
| `n_evaluated` | int | states computed for the line (0.7) |
| `n_outside` | int | of those, states outside the area the axes show (0.7) |

The number of points is not fixed: lines are stepped with steps chosen
from their shape in plot coordinates (`coolplot.thermo.stepping`), so a
straight line has about `points / 2` points and a bent one more.

A curve is identified by the cache key `(fluid, fingerprint, diagram,
key, value_SI, points, ...)`: the fingerprint names the CoolProp version
and its configuration, so curves of one installation are never served
to another; the rest are the request (`coolplot.engine.planning.CurveRequest`)
and the calculation settings that affect the numbers.

## 3. The scene

What a renderer draws: one set of axes and a flat list of items in
drawing order, coordinates in display units. `coolplot.scene` is the
definition; contributing/writing_a_backend.md says how each field is rendered.

```js
{
  "axes": {"x_label": "Specific enthalpy h / kJ/kg", "y_label": "Pressure p / bar",
           "x_log": false, "y_log": true, "x_limits": [100.0, 700.0], "y_limits": [0.5, 60.0],
           "title": "", "style": {...}, "tick_digits": 6},
  "items": [
    {"type": "line", "id": "iso/T/273.15", "group": "iso/T", "role": "isoline",
     "legend": "Temperature", "visible": true, "z_order": 1.0, "style": {...},
     "x": [...], "y": [...]},
    {"type": "markers", "id": "cycle/heat pump/states", "group": "cycle/heat pump",
     "role": "state_points", "legend": "heat pump", "visible": true, "z_order": 6.0,
     "style": {...}, "x": [...], "y": [...]},
    {"type": "text", "id": "iso/T/273.15/label", "group": "iso/T/label", "role": "isoline_label",
     "legend": null, "visible": true, "z_order": 4.0, "style": {...},
     "x": 412.3, "y": 3.2, "text": "T=0 deg C", "direction": [1.0, 0.1],
     "offset_pt": [0.0, 0.0], "clip": true}
  ]
}
```

Item types: `line` (a polyline; `null` splits it), `markers` (points
without a line) and `text` (one label; `direction` is a direction in
data coordinates the text follows, `offset_pt` a shift on screen in
points with y up, `clip` whether it is cut at the plot area). The
`style` records are `LineStyle`, `MarkerStyle` and `TextStyle` of
`coolplot.style.values`, the axes style an `AxesStyle`.

Ids are stable across units, styles and redraws, so a renderer can update
an item in place:

| Id | Item |
|---|---|
| `iso/<key>/<value>` | a line of constant `<key>` at the SI value `<value>` (12 significant digits) |
| `iso/<key>/<value>/label` | its label |
| `cycle/<name>/loop/<i>` | the i-th chain of a cycle |
| `cycle/<name>/states` | the markers of all states of a cycle, in ascending state number |
| `cycle/<name>/number/<n>` | the number of state n |
| `process/<name>/line`, `process/<name>/points` | a legacy process |

Groups collect what is styled and toggled together (`iso/T`,
`iso/T/label`, `cycle/<name>`, `cycle/<name>/numbers`). Roles say what
an item means: `isoline`, `saturation` (the phase boundary: quality 0
and 1, relative humidity 100 %), `quality` (the other lines of the
boundary family), `isoline_label`, `cycle`, `process`, `state_points`,
`state_number`, `annotation`. Z order: isolines 1, saturation 2, labels
4, cycles and processes 5, state points 6, state numbers 7; backends
keep everything below 0 for grid and background.
