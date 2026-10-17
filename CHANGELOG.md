Changelog
=========

0.3.0
-----

* Background calculation: `PropertyDiagram(..., background="threads"` or
  `"processes")` never waits for a line; coarse previews first, then the
  final lines, with `on_ready`, `progress`, `wait()` and `close()`.
  Failed lines are tried again and then reported.
* Events from the backends (hover, click, drag, view changes, resizes)
  in the axes' units, and `Interaction` for zoom, hover and dragging the
  states of cycles, in matplotlib and in the browser.
* New backends: plotly, and a browser backend that streams small patches
  to a JavaScript client, with a dependency-free development server
  (localhost only, input checked).
* Psychrometric charts (`PsychrometricChart`): lines of relative
  humidity, wet-bulb temperature, enthalpy and specific volume cut at
  saturation, air processes on top, any total pressure.
* PDF as a first-class output: fonts embedded as TrueType, texts kept as
  text (labels with halos included), theme colours, the chart title as
  PDF title, reproducible files, `save_pdf` for several charts in one
  file, `Font(files=...)`, `strict_fonts` and `fonts_used()`. A PDF check
  in the conformance kit reads files back without external tools. plotly
  writes PDF through kaleido (extra "images").
* The wet-bulb search of psychrometric charts reports no convergence
  instead of returning the last estimate.
* The physics fixes of 0.2.0 (mixture states, mixture limits, blends on
  CoolProp 6 and 7, incompressibles, cache fingerprint) are part of this
  release as well.
* Texts are always plain text: "$5 or $6" is never typeset as math.

0.2.0
-----

A new package layout and API; the legacy API (`from CoolPlot.Plot import
PropertyPlot`) is gone. Stay on `pip install "coolplot<0.2"` if you need it.

* Layers with one job each: specs (what to plot), thermo (CoolProp
  calculations), engine (caching), compose (styles, texts and label
  layout) and render (plotting backends). `tests/test_architecture.py`
  enforces the import rules.
* matplotlib is one backend among several: a dependency-free SVG backend
  is included, and backends follow a written contract
  (docs/backends.md) checked by a conformance kit.
* Interactive applications redraw only what changed: a backend-neutral
  scene with item ids, synchronised selectively; changing units or the
  theme recalculates nothing.
* `PropertyDiagram`: log(p)-h, T-s, h-s, p-s, p-rho, T-rho and p-T
  diagrams for pure fluids and blends, with one `Settings` value for
  point counts, margins, labels and page size, and JSON round trips of
  the whole diagram.
* Styling is first class: themes ("default", "dark", "print",
  "classic"), validated style values and a styling guide.
* Isoline labels sit at the edges of the chart and keep clear of cycles
  (keep-out zones); one central number format for all labels.
* Cycles on diagrams, given state by state in the diagram's units or from
  cycle models, including split and two-stage cycles.
* Works with CoolProp 6.8, 7.2 and 8.
