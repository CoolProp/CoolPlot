# Changelog

All notable changes to CoolPlot are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the upgrade
guide in the documentation says what to change in your code.

## [Unreleased]

### 1.1.0

#### Added
- Lines placed through saturation states:
  `set_lines("s", at_saturation={"T": 10})` draws the isentropes through
  the saturated vapour every 10 K of saturation temperature (round values
  in the chart's units, up to the critical point), each labelled with its
  own value ("s=2.321 kJ/kg/K"). `"Q": 0` uses the saturated liquid (the
  bubble point of a blend), `"p": 2` steps the saturation pressure,
  `"range"` limits the states, `"label": "saturation"` labels the lines by
  their saturation state instead ("T_sat=0 deg C"). Stored
  as `IsolineSet.anchor` (`coolplot.spec.SaturationAnchor`); coolplot-core
  composes it the same way. Example `examples/saturation_lines.py`.
- Traced lines kept on disk between runs, the way CoolProp keeps its
  TTSE and BICUBIC tables: `CurveCache(directory=True)` (or the
  environment variable `COOLPLOT_CACHE_DIR`) writes one compressed file
  per line under `~/.CoolProp/CoolPlot/Curves`, one folder per fluid,
  with a revision and the full key in each file, a rebuild of anything
  unreadable, CoolProp's `ALTERNATIVE_TABLES_DIRECTORY` and
  `MAXIMUM_TABLE_DIRECTORY_SIZE_IN_GB`, and atomic writes so processes can
  share the folder (`coolplot.engine.store`). Off unless asked for. The
  stored key also holds CoolPlot's version and CoolProp's git revision,
  and with a disk cache the engine notices a changed reference state by
  itself before anything is written; background workers report the
  fingerprint they computed under, and a line from a worker that differs
  stays off disk. The source of the numerics modules is part of the stored
  key too, so development builds that share a version do not share lines.
- Labels in the colour of their lines:
  `diagram.theme = diagram.theme.with_(isoline_label_color="line")` draws
  each isoline label in its line's colour (with its halo), following
  `set_line_style` colours too; the default `"text"` keeps the ink colour.
  The same option in coolplot-core.
- coolplot-core reports its version from CMake (1.1.0); the bridge
  refuses a chart whose lines are labelled by their saturation state on an
  older core, which would label them by value, and the Python composer
  draws it.

#### Fixed
- The fingerprint of a fluid (part of every cache key) used Python's
  salted `hash()` of CoolProp's configuration, which differs between
  processes; it is a SHA-256 digest now, so keys mean the same in every
  run.

### 1.0.0rc1

#### Removed
- The names deprecated since 0.5: the chart methods `set_isolines`,
  `set_default_isolines`, `remove_isolines`, `isoline_sets`,
  `set_isoline_style`, `savefig`, `set_process`, `remove_process`, the
  psychrometric `add_process`, `move_process_state`, `process_states`;
  the unit system name "EUR" in calls; the `rankine` keywords
  `eta_turbine` and `eta_pump`. A removed chart method raises an
  AttributeError naming its replacement, "EUR" a ValueError naming
  "engineering" and the old `rankine` keywords a TypeError naming theirs.
  A spec saved by 0.4 with "EUR" still reads, in Python and in
  coolplot-core. See the upgrade guide.

#### Deprecated
- The constant `coolplot.EUR` (an old name of `coolplot.ENGINEERING`,
  silent before 1.0) warns and goes in 2.0.

#### Changed
- The public API is stable from 1.0 to 2.0 (upgrade guide, "Stability
  from 1.0"); deprecations in 1.x go in 2.0.
- The Python numerics and composer stay, behind `set_native_mode`: they
  are the reference, CoolProp's numerics port is not in a released
  CoolProp yet, and coolplot-core is slower from Python than the Python
  composer (plan, 1.0: they go only when the C++ passes the full suite as
  the default).

### 0.9.0

#### Added
- Fluid lines are computed by CoolProp's C++ port of the numerics
  (`CoolProp.CoolProp.Plot`, in CoolProp after 8.0.0) when the installed
  CoolProp has it: the same stepping, tracer and dome crossings, point
  for point, with the GIL released; a pure-fluid chart takes half the
  time, a blend's a tenth less (CoolProp's solvers take the rest).
  `COOLPLOT_NATIVE=0` keeps the Python numerics, which stay the reference
  and do the work for models the port cannot name
  (`coolplot.thermo.native`).
- coolplot-core (`cpp/`): the composer, the label layout, the styles and
  themes, the scene and the SVG writer in C++17, plus a PDF writer with
  TrueType subsets, a C ABI and the nanobind module `coolplot_core`, for
  programs in other languages. With `COOLPLOT_NATIVE=1` CoolPlot composes
  and writes SVG there too; scenes and documents are the same as from
  Python, point for point and byte for byte. Unset, the Python code does
  it, which from Python is faster (docs/contributing/core.md).
- `coolplot.render.pdf.PdfRenderer`: PDF without matplotlib, through
  coolplot-core; it passes the conformance kit's PDF check.
- `coolplot.render.web.scene_page`: a self-contained page that draws a
  scene in the browser with a JavaScript port of the SVG writer, no server.
- `coolplot.set_native_mode("auto" | "on" | "off")` and
  `coolplot.native_mode()`: one setting chooses between the Python code
  and the C++ ports, with `COOLPLOT_NATIVE` as the starting value
  (`coolplot.core.implementation`). Every example draws the same scene
  and writes the same files in "off" and "on" (tests/test_examples.py).
- `Scene.to_dict(in_draw_order=False)` writes the items in scene order,
  for writers that take the legend from that order.

#### Deprecated
- 0.9 is the deprecation release: nothing is removed, and the old names
  of 0.5 (listed in the upgrade guide) warn with a `DeprecationWarning`
  and go in 1.0.

#### Changed
- `COOLPLOT_NATIVE=auto` means the default mode; before, any value but
  "0" switched coolplot-core on.

#### Fixed
- A diagram of any pair of fluid axis quantities, such as
  `DiagramType("T", "h")`, is written as "Th" and now reads back from its
  spec; it failed to load before.
- `format_number` of the largest numbers (rounding up overflowed to
  infinity) raised; it now gives e.g. "2e308".
- Labels next to the bottom of a log axis that starts close to zero (the
  isotherm labels of R290 with the default limits) got a NaN angle from
  matplotlib and made saving the chart fail; they get their angle computed
  once instead.

### 0.8.0: documentation

#### Added
- Documentation built with Sphinx (MyST Markdown, numpydoc, pydata
  theme): getting started, four tutorials, how-to pages, explanations,
  the generated API reference, tables generated from the package, the
  gallery of the examples (run at build time), an upgrade guide and the
  checklist of the documentation review. `make docs` builds it with
  warnings as errors; CI and Read the Docs build it too.
- A picture in the README.
- Docstrings for every public name (108 added); the build checks that
  none is missing.

#### Changed
- `coolplot.engine.plan` is the function; the module is
  `coolplot.engine.planning`.
- The changelog is in Keep-a-Changelog form.

### 0.7.0: numerics

#### Added
- Adaptive stepping of every isoline (`coolplot.thermo.stepping`): the
  step is chosen from the shape of the line on the page, nothing is
  computed outside the area the axes show, and `Curve` records
  `n_evaluated` and `n_outside`.
- Isotherms and isobars followed through the dome in vapour quality,
  which draws the temperature glide of a blend (the 5 bar isobar of
  R407C in a T-s chart has 44 points inside the dome, before 5).
- Fluid states carry the specific volume `v` and can be given by it.
- `Unit.difference_label`, `UnitSystem.difference`, `describe_difference`;
  `BAR_GAUGE` and `PSI_GAUGE`, drawn on a linear axis.
- `PropertyError.reason` and `limits`: a temperature or pressure outside
  the equation of state, a quality above the critical point or an
  unsupported mixture pair is named, with the limit in the chart's units.
- The numerics sweeps in `tests/numerics` (`pytest --run-slow`).

#### Changed
- The tracer of blends finds the quality of a two-phase point by a
  secant iteration from the previous point, solves densities on the
  specific volume and judges roots near the critical point by the phase
  envelope. The default p-h chart of R410A draws in 5 s (before 23 s),
  of R407C in 11 s (before 27 s).
- Lines of intermediate quality of a blend run up to the top of the
  phase envelope.
- The number of points of a line is no longer fixed; `Settings.calc.points`
  is the resolution. Lines are cut at the edges of the axes.
- A line that lies outside the axes is left out without a warning;
  `Curve.reason` says so. A line cut short by the evaluation budget
  warns.
- The label layout clips lines with numpy, a few times faster.

#### Removed
- Support for CoolProp 6 and 7 (plan decision D2); CoolProp 8 is
  required.

### 0.6.0: scope and shape

#### Changed
- `coolplot.testing` holds the conformance kit and the PDF reader
  (before `coolplot.render.testing` and `coolplot.render.pdf_reader`); no
  backend imports it when a chart is drawn.
- The development web server moved to `examples/web_app/server.py`;
  `WebRenderer` stays in `coolplot.render.web`.
- Large functions split into small named steps (every function outside
  the test tooling and the numerics below a cyclomatic complexity of 11).
  Where two inputs are wrong at once the error named first can differ.
- The matplotlib backend keeps the data angle of a text itself instead of
  reading a private attribute.
- Tests that need a browser or Kaleido run only with
  `pytest --run-browser --run-kaleido`.

### 0.5.0: vocabulary, units and errors

#### Added
- Unit systems `"engineering"` (the old `"EUR"`, which warns) and `"IP"`
  (deg F, psi, Btu/lb, grains per lb); `units=` on every call.
- `PropertyError`, raised for a state that cannot be computed, naming the
  fluid, the inputs in the chart's units and where the request came from.
- `tests/test_api_vocabulary.py`, which freezes the public names.

#### Changed
- One verb per operation on every chart: `set_lines`, `set_default_lines`,
  `remove_lines`, `line_sets`, `set_line_style`, `add_cycle` (with
  `closed=False` for an open process), `remove_cycle`, `move_cycle_state`,
  `cycle_states`, `set_view`, `state_at`, `update_scene`, `draw`, `save`.
  The old names warn and go in 1.0.
- The fluid of a chart is checked when it is set, not when it is drawn.
- `rankine` takes `eta_is_turbine` and `eta_is_pump`.

### 0.4.0: one chart model

#### Added
- One `Chart` with `PropertyDiagram` and `PsychrometricChart` as its two
  constructors; property providers for fluids and humid air; a registry
  of line families per kind of chart; one quantity table and one unit
  table for fluids and humid air.
- `docs/contracts.md`: the chart record, the line record and the scene
  record, round-tripped in tests.
- `Scene.to_dict` and `from_dict`, `Curve.to_dict` and `from_dict`.

#### Changed
- Humid-air processes are cycles with straight paths.
- Psychrometric charts take `Settings.calc.points` (250) instead of their
  own 100.
- `Settings.labels.edges` defaults to empty (the family's own preference).

### 0.3.1

#### Fixed
- Mixture states CoolProp gets wrong (a single phase reported inside the
  dome) are refused instead of drawn.
- Blends start at the highest triple-point temperature of their components.
- Incompressible fluids plot with absolute limits.
- Lines are cached with a fingerprint of CoolProp's version, configuration
  and reference state.

### 0.3.0

#### Added
- Background calculation (threads or processes) with coarse previews.
- Events and `Interaction`: zoom, hover, dragging of cycle states.
- The plotly backend and the browser backend (`WebRenderer`).
- Psychrometric charts.
- PDF output with fonts embedded as TrueType, `save_pdf` for several
  charts in one file, a conformance check of the PDF.

### 0.2.0

#### Changed
- The package was rebuilt around a pipeline of spec, engine, scene and
  renderers; the legacy API (`CoolPlot.Plot.PropertyPlot`) was replaced.
  See the upgrade guide.

## [0.1.x]

The legacy releases, a fork of `CoolProp.Plots` from CoolProp 6.3.0.
