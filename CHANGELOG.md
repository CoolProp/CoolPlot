Changelog
=========

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
* Works with CoolProp 6.8, 7.2 and 8. With CoolProp 6 and 7, lines of
  constant s, h, u or rho of a blend are skipped with a warning that says
  so (their flashes do not support mixtures there); isotherms, isobars
  and quality lines work.
* Every state CoolProp returns for a mixture is checked against the
  saturated densities at its temperature: CoolProp 8's T,rho flash
  answers some inputs inside the two-phase region with a "gas" at a
  wrong pressure, and such points are left out instead of drawn.
* Blends start at the highest triple-point temperature of their
  components, not at CoolProp's mole-weighted average, below which one
  component is solid.
* Incompressibles (`INCOMP::...`) plot with absolute limits; relative
  limits and quality lines give a clear error at once.
* Cache keys carry a fingerprint of CoolProp's version, configuration and
  reference state; a changed configuration rebuilds the states, and
  `diagram.refresh()` does the same after `set_reference_state`.
