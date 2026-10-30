# Changelog

All notable changes to CoolPlot are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the upgrade
guide in the documentation says what to change in your code.

## [Unreleased]

### Changed
- `cycle_states`, `state`, `state_at` and `mix` say which way `units=`
  works: on `cycle_states` it converts the states returned (as dicts),
  on the others it only sets the units of the input and the StatePoint
  returned stays in SI units. The how-to on units explains why (#33).

## [1.5.0] - 2026-10-30

### Added
- coolplot-core 1.5 composes and writes the badge of the branding when it
  holds text lines only (references, versions, lines of your own): the
  compose record takes the source lines as `"sources"`, the scene record
  carries the badge, and the SVG and PDF writers draw it as the Python SVG
  writer does. A branded chart without logo or watermark therefore takes
  the native path; one with pictures still takes Python. The bridge
  refuses a badge for a core older than 1.5, so the Python composer draws
  it, with a warning.
- The plotly backend and the JavaScript writer (`scene_page`) draw the
  badge of text lines too; only a logo or a watermark is left out, with a
  warning. `PdfRenderer` draws it through coolplot-core 1.5, also on a
  chart with a logo or a watermark, which it leaves out with a warning.
- Theme "coolpack": the look of the log(p),h-diagrams of CoolPack (DTU,
  "Refrigeration Utilities", late 1990s). Times on white with a dense
  light grey grid (major and minor ticks), a black saturation curve, red
  isotherms, blue isentropes, green isochores and navy lines of constant
  quality in the colours of the 16 colour Windows palette, every label in
  the colour of its line, no legend. Purple isobars and magenta
  isenthalps for the other charts. coolplot-core has the same preset.
- Documentation: a theme catalog with every theme on a log(p)-h and a T-s
  chart, its isoline colours as seen with each kind of colour vision
  deficiency and in greyscale, contrast and separation numbers, and why
  its colours are what they are. Pictures and numbers are generated when
  the documentation is built.
- Documentation: "Colour and accessibility", the rules the themes are
  measured against (WCAG 2.2 AA, the colour science literature), who they
  are for, and how the default colours were chosen.
- Gallery example "A CoolPack chart, for old times' sake": the R290 chart
  of the CoolPack tutorial with its one stage cycle, in the new theme.

### Changed
- Every chart names the equation of state of its fluid by default:
  `BrandingSettings.references` is "short" instead of "none", so the
  badge shows a line such as "R290: Lemmon et al. (2009)" in the
  emptiest corner. `branding={"references": "none"}` removes it. Specs
  saved before 1.2 keep drawing without badge, specs saved since hold
  their setting. The picture on the landing page and in the README is
  drawn again with the badge (and the default colours of 1.5).
- One colour per quantity in the `default` and `dark` themes, the same on
  every chart: red isotherms, wine isobars, orchid isenthalps, blue
  isentropes, teal isochores and purple lines of constant u (`#c72500`,
  `#621b40`, `#ce52f9`, `#2d03cd`, `#0ba589`, `#87459f`; on the dark
  surface `#ee7a5a`, `#9a9ad8`, `#9f4e64`, `#3a66d0`, `#7ee6d2`,
  `#f6c919`). Up to 1.4 the colours went out by position, so the same
  colour meant pressure on one chart and temperature on another. The
  colours stay apart for every kind of colour vision deficiency (closest
  of all ten pairs 15.0 in OKLab x100) and every one reaches 3:1 contrast
  on its background (WCAG 2.2; the aqua isochores had 2.7:1). The slots,
  still used by themes without pinned colours, are `#c72500`, `#2d03cd`,
  `#0ba589`, `#87459f` (dark: `#ee7a5a`, `#3a66d0`, `#7ee6d2`, `#f6c919`).
  coolplot-core has the same colours.
- Documentation: the top bar lists the gallery right after Getting
  started and shows six pages before "More", so the gallery no longer
  hides behind it; the landing page shows thumbnails of four examples.
- The gallery example "A chart with a logo, references and a watermark"
  is gone: the company chart of Clean Heat Partners shows the same
  (logo, references, versions, a line of text and a watermark) on a real
  chart.

### Removed
- Theme "classic" (and `coolplot.style.CLASSIC`). Its idea, a colour per
  quantity, is now part of `default` and `dark`; `get_theme("classic")`
  raises ValueError. Charts saved before keep their whole theme.

## [1.4.0] - 2026-10-24

### Added
- Gallery example "A company chart: Clean Heat Partners": a theme with
  the company colours, the saturation line without casing, the company
  logo and brandmark (SVG files in `examples/data`, trademarks outside the
  MIT licence, see `examples/data/NOTICE`) on an R290 heat pump.
- `LabelSettings.symbols`: "unicode" writes symbols and units in axis
  titles, legends and labels with their own characters (the Greek rho
  and phi, the degree sign, m3 with a superscript 3), "ascii" with plain
  letters as before. The tables are in `coolplot.core.symbols`, and
  coolplot-core 1.4 writes the same texts. Every character is written as
  an escape, so the sources stay ASCII.
- The references of a mixture in the badge start with its name and
  composition: "R407C: R32 23 %, R125 25 %, R134a 52 % by mass". A
  mixture given by its fractions takes the name of the predefined blend
  of CoolProp within half a percent by mass, else "Mixture". Refrigerant
  blends are shown by mass, as their R number is defined; other mixtures
  in the basis of their fractions. Other backends show the fractions of
  a mixture or solution ("MEG 30 % by mass: CoolProp incompressible
  fluid"). New in `coolplot.thermo.references`: `blend_name` and
  `composition_text`.

### Changed
- "unicode" is the default of `LabelSettings.symbols`: new charts show
  "Density &rho; / kg/m&sup3;" for "Density rho / kg/m3", "&deg;C" for
  "deg C", T_wb and T_dp for Twb and Tdp, and &phi; for the relative
  humidity on the psychrometric chart as well (it was "RH"; ASHRAE
  Handbook and ISO 80000-5 write phi). A settings record without
  `symbols`, as every record before 1.4, reads as "ascii", so saved
  specs draw as before. `labels={"symbols": "ascii"}` gives the look of
  1.3 (the how-to on labels).
- coolplot-core 1.4.0. The Python bridge hands a chart with "unicode"
  symbols to the Python composer, with a warning, when the installed
  core is older.
- A new picture on the landing page and in the README, drawn by the code
  next to it (now with round values, `rounding=True`): labels on rails,
  the legend inside the plot and the symbols of 1.4.
- A chart compares a cycle's fluid with its own as a model
  (`Fluid.same_fluid`): the same mixture by mass, by mole or as a
  predefined blend (R32/R125 50/50 by mass and "R410A.mix"), with its
  components in the same order, and a pure fluid by an alias ("R290" and
  "Propane") count as one fluid. A mixture's fractions are compared to
  1e-9 and its interaction parameters to 1e-12. The message for a cycle
  of another fluid gives the basis of a mixture by mass ("(fractions by
  mass)"), and says "another model of" when both fluids print alike.

### Fixed
- A cycle was checked against its chart by the name of its fluid, which
  loses the basis of the fractions, interaction parameters set on a
  mixture and the fractions of an AbstractState. So a cycle of a mixture
  given by mass fractions (a `FluidSpec` with `basis="mass"`), with its
  own interaction parameters or as an AbstractState was refused by its
  own chart ("Cycle ... was computed for X, but this chart shows X"), and
  a cycle with other interaction parameters was taken by a chart without
  them. A cycle now keeps the model of its fluid (`Cycle.fluid_model`,
  `Fluid.model_key`, filled in by the cycle models), and the chart
  rebuilds the fluid from it (`Fluid.from_model`); a cycle with only a
  name is checked by the name, as before.

## [1.3.0] - 2026-10-22

### Added
- Type information: the package ships its annotations (the PEP 561
  marker `py.typed`), so type checkers such as mypy and pyright check the
  calls an application makes to CoolPlot. The chart API is fully
  annotated: `Chart`, `PropertyDiagram`, `PsychrometricChart`, `save_pdf`
  and the names importable from `coolplot`, which type checkers now see
  behind the lazy loading. `Chart.draw(renderer)` returns the renderer
  with its own type, and `Chart.cycle_states` returns StatePoints, or
  dicts of values when `units` is given. A misspelt name of a chart or of
  the package is reported by the checker; running code still gets the
  messages for the names removed in 1.0.
- Names for what the public functions take in several forms:
  `coolplot.core.units.UnitsLike`, `coolplot.core.limits.TpLimitsLike`,
  `coolplot.chart.Numbers`, `coolplot.chart.StateEntry` and
  `coolplot.diagram.FluidLike`; `coolplot.scene.SceneItem` for the three
  kinds of scene item; `DiagramType.require_family`.
- Type checks (`tests/test_typing.py`, `make typecheck`): mypy over the
  whole package, over the public API as an application sees it (strict
  mode, `tests/typing_checks/public_api.py`) and over the examples. The
  tests workflow runs them in a `typing` job and checks that the wheel and
  the sdist carry `py.typed`. The optional dependencies gain `typing`
  (mypy). The contributing guide has a page on type annotations.
- Gallery examples: a steam Rankine cycle on a T-s chart, a steam turbine
  on the h-s (Mollier) chart of water, an organic Rankine cycle with
  R245fa, a transcritical CO2 heat pump, one heat pump with R290, R32 and
  R1234yf side by side, an air conditioner in IP units, one chart in the
  four themes, the four label modes, and a chart with a logo, references
  and a watermark. The how-to guides point to them.
- `Unit.label_value`: the value a label shows for an SI value.
- The saturation curve can be restyled per chart:
  `set_line_style("saturation", casing_width_pt=0)` draws it without the
  casing (the band in the background colour along it) of the screen
  themes. Spec records take the key `"saturation"` in `style_overrides`.
  coolplot-core 1.3 draws it; with an older core, such a chart falls back
  to the Python composer with a warning.

### Changed
- A range that is not two values (`range=` of `set_lines`, `"range"` of
  `at_saturation`, `T_range` and `W_range` of `PsychrometricChart`) is
  refused with a ValueError that says so.
- The examples pass `line_style` and `marker_style` by name instead of
  unpacking a dict of both, so that they pass the type checker.

### Fixed
- About 390 places where mypy found the annotations and the code at odds,
  most of them values that may be None and return types of internal
  helpers. None of them changes what a chart draws.
- `add_cycle` numbers states given in a mapping other than a dict by its
  keys, as it does for a dict.
- `set_line_style("Q", ...)` (and `"RH"` on a psychrometric chart) was
  kept in the spec but not drawn; it restyles the lines of constant
  quality (relative humidity) now.
- A line at 0 in a unit with an offset other than deg C, such as the
  isotherm at 0 deg F, was labelled "-4e-10" (the noise of converting
  back from kelvin); it is labelled 0 by the Python composer and by
  coolplot-core 1.3. An older coolplot-core still writes the noise.

## [1.2.0] - 2026-10-22

### Removed
- Python 3.10, which reaches its end of life in October 2026:
  `requires-python` is ">=3.11", so pip on Python 3.10 keeps
  installing 1.1. coolplot-core's Python module also needs 3.11.

### Added
- Air processes on psychrometric charts:
  - `"via": "sensible"` keeps the humidity ratio of the state before
    (a heating coil, or a cooling coil above the dew point). Charts of a
    fluid refuse it.
  - `PsychrometricChart.mix(a, b, m_dot_a_kg_s, m_dot_b_kg_s)` gives the
    state after two air streams mix adiabatically, from the water and
    energy balances per kg of dry air; a mix that would form fog is refused.
  - `PsychrometricChart.add_zone(name, T_range, RH_range, label=...)`
    outlines a region of temperature and relative humidity, such as a
    comfort zone. Its humidity edges follow the lines of constant relative
    humidity.
- State labels: `add_cycle(..., labels={2: "ADP 11.2 deg C"})` writes a
  text next to a state, after its number, or alone with `numbers=False`.
  The cycle record gains an optional `labels` list; records of 1.1 read and
  write as before. coolplot-core 1.2 draws them. With an older core, a chart
  with labels falls back to the Python composer with a warning.
- The Mollier h,x chart of humid air (DIN 1946, VDI 4670):
  `PsychrometricChart(..., style="mollier")` draws the humidity ratio x
  across and the temperature scale Thx, linear in the enthalpy, up, with
  isotherms, lines of constant enthalpy falling to the right and the
  symbols x and phi. Diagram name `ThxW` (or `mollier`, `hx`). Humid-air
  states gain `Thx`; states saved by 1.1 get it computed when they are
  read. coolplot-core 1.2 composes it; with an older core, a Mollier
  chart falls back to the Python composer with a warning. Gallery example
  "An air handling unit on the Mollier h,x chart".
- `Chart.state(entry)` gives a full state from two properties in the
  chart's units.
- Label mode "rails" (`coolplot.compose.rails`): the bare values of each
  family in a row along one edge, outside the frame at the top and on
  the right with a tick where the line leaves, or just inside it on any
  edge, turned along the lines with the label boxes on a common rail.
  Each family takes the rail that fits the most labels, a second rail
  for lines that do not reach the first, and labels at the ends of lines
  that end inside the chart; whole levels of values are dropped when not
  all fit, so a row stays regular. The legend gives
  the symbol and unit of each family ("Temperature T / deg C"; for lines
  labelled by their saturation states "Specific entropy s at T_sat /
  deg C"). The scene
  gains the role `label_tick`. coolplot-core 1.2 lays rails out the same
  way.
- Legend location "auto": inside the plot area, in the corner where the
  legend covers the fewest points of cycles and processes, then of the
  isolines; outside on the right when it would cover more than a quarter
  of the page's plot area. The legend
  and the badge are given their corners together
  (`coolplot.compose.corners`), so an automatic one never takes the
  corner of the other, and rail and edge labels keep clear of both.
- Gallery examples: the basic air processes from one state; summer and
  winter operation of an air handling unit, with duties, the room's sensible
  heat ratio and a comfort zone; evaporative cooling in a dry climate. The
  how-to guide "Draw air processes on a psychrometric chart" explains the
  pieces.
- Branding: `Settings.branding` (`coolplot.BrandingSettings`) puts a badge
  in a corner of the plot area, with a logo (PNG or SVG), the references
  of the equation of state of the fluid ("short": "R290: Lemmon et al.
  (2009)", or "full" with journal, volume and pages), the CoolProp and
  CoolPlot versions and lines of your own, and a faint watermark picture
  behind the lines. The references come from CoolProp's BibTeX keys and
  the bibliography in its package: every component of a mixture plus the
  references of its mixture model, ASHRAE RP-1485 for humid air, the
  backend's name for REFPROP and cubic equations. `location="auto"` takes
  the corner where the badge covers the fewest points of the drawn
  lines; edge labels (the default label mode) keep clear of the badge.
  Drawn by the matplotlib and SVG writers, which give the badge the same
  size, the size the label layout keeps clear (logos in PDF keep all
  their pixels; PS and EPS leave the watermark out, with a warning, as
  PostScript has no transparent images); the web renderer draws it as
  the SVG writer does. The scene record carries it as `axes.badge` and
  `axes.watermark`. coolplot-core does not compose or draw it, so a
  branded chart uses the Python composer and SVG writer; the plotly
  backend, the coolplot-core PDF writer and the JavaScript writer of
  `scene_page` warn and leave it out.
  How-to page "Logo, references and watermark".
- `Chart.uncached_curves()`: how many lines the next update would
  calculate, counting the curve cache in memory and on disk; an
  application can tell a cheap request from an expensive one first.
- `SvgRenderer(unit="pt" | "mm")` writes the document size with a unit,
  and the size may be fractional.

### Changed
- Python 3.15 is supported and tested in CI (Python 3.11 to 3.15).
- New charts lay out their labels on rails and put the legend inside the
  plot area ("rails" and "auto" are the new defaults of
  `LabelSettings.mode` and `LegendStyle.location`). Specs saved by 1.1
  hold their label mode and their theme, so they draw as before.
  `labels={"mode": "edge"}` and the legend location "outside right" give
  the look of 1.1 (the how-to on labels).
- The saturation curve is drawn whatever lines are set: a chart of a fluid
  with a critical point shows the dome also when the quality values leave
  out 0 and 1 or no quality lines are set, and a psychrometric chart the
  line of 100 % relative humidity. `chart.show_saturation = False` hides
  it. Spec records gain a `show_saturation` field; a record of 1.1 reads
  without it and draws as before.
- `save("chart.svg")` writes the size of `settings.page` (in points)
  instead of 800 x 600 pixels; `width`, `height` and `unit` still
  override it. A size in points is not a whole number of pixels, so this
  document is written by the Python SVG writer, also with the native
  mode on; `SvgRenderer(native=True)` with whole pixels still uses
  coolplot-core.
- `save()` to PNG, PDF and other matplotlib formats draws into a figure
  outside pyplot unless `draw()` or `show()` made one before, so saving
  charts in a server or a loop no longer collects pyplot figures.
- CoolProp's pseudo-pure models of blends ("R407C", "R410A", "Air") give
  one warning that names the mixture to use ("R407C.mix") instead of one
  warning per missing line of constant quality.

## [1.1.0] - 2026-10-22

### Added
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

### Fixed
- The fingerprint of a fluid (part of every cache key) used Python's
  salted `hash()` of CoolProp's configuration, which differs between
  processes; it is a SHA-256 digest now, so keys mean the same in every
  run.
- `draw()` and `save()` with a background engine could stop waiting
  too early, with "Background work makes no progress, the drawing may
  be incomplete", when a line failed while the scene was being built:
  a worker process that crashes fails every job of its pool at once, and
  the retries queued next were taken for no progress. The lines they
  would have drawn were missing, and the line that crashed was not
  reported. Progress is now counted over the scene and the wait after it.

## [1.0.0] - 2026-10-22

The first release on PyPI since 0.1.7. It also holds the development
versions 0.2.0 to 0.9.0 below, which were not published on PyPI; coming
from 0.1.7, see the upgrade guide.

### Removed
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

### Deprecated
- The constant `coolplot.EUR` (an old name of `coolplot.ENGINEERING`,
  silent before 1.0) warns and goes in 2.0.

### Changed
- Python 3.14 is supported and tested in CI (Python 3.10 to 3.14).
- The public API is stable from 1.0 to 2.0 (upgrade guide, "Stability
  from 1.0"); deprecations in 1.x go in 2.0.
- The Python numerics and composer stay, behind `set_native_mode`: they
  are the reference, CoolProp's numerics port is not in a released
  CoolProp yet, and coolplot-core is slower from Python than the Python
  composer (plan, 1.0: they go only when the C++ passes the full suite as
  the default).
- No equality tests between floats in the numerics, the drawing code,
  the scene renderers and coolplot-core: exact zeros, settings and copied
  values are tested with the helpers of `coolplot.core.floats` (in C++,
  `core.h`; the core compiles clean with `-Wfloat-equal`). Every chart
  checked is bit-identical before and after. The same rewrite as in
  CoolProp's port of the numerics.
- The GitHub workflows run the Node 24 releases of the actions
  (checkout, setup-python and setup-node v7, upload-artifact v7,
  download-artifact v8); the runners warned about Node 20.

### Fixed
- A line where no state at all could be computed said nothing: failed
  looks while the stepping scans outside the axes count as outside, so
  the curve had no points, `n_outside` > 0 and an empty `reason`. It now
  says "none of the N states of the line could be computed". A line
  whose states were computed but lie outside the axes says so also
  when some of its evaluations failed (it used to say "only 0 point(s)
  of the line could be computed").
- The quality solver of the tracer no longer accepts a residual that is
  not a number (it compared as "same side" and passed the residual
  check, so the saturated liquid was reported as the point).
- The crossing of an isoline with the dome (a regula falsi on the
  saturation states) no longer returns its last iterate when it has not
  converged in 60 steps.  A mixture line then takes the phase-envelope
  crossing; a pure fluid's line goes on without a point at the dome.
- The trivial-solution check of a mixture's two-phase state fails
  closed: when the saturated outputs cannot be computed, the state is
  not taken as two distinct phases (a fallback flash or a gap instead).
- A saturation pressure or density that is not a number leaves the
  tracer's outside-the-dome check undecided; before, `max()` dropped a
  NaN pressure and a NaN density made the inside-the-dome test false.
- The bubble and dew ends of a pure fluid's isotherm or isobar, which
  have the same sweep value up to rounding, are ordered by quality, not
  by the rounding noise.
- A temperature or pressure limit that is NaN, also a relative limit
  with a NaN factor, is refused with a clear error (it ended in an
  "empty plotting region").
- A line of constant quality with fewer than two points says why in
  `reason`.
- All found in the review of CoolProp's port of these numerics; the
  port has the same fixes.

## Development versions, not published on PyPI

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
  matplotlib and made saving the chart fail; their angle is computed by
  CoolPlot instead, again after every zoom, pan or resize.

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
- `save()` writes SVG and HTML at the size of `settings.page`, as it
  does for matplotlib; `width` and `height` still override it.

#### Fixed
- Humid air refuses the total pressure as one of its two properties
  (CoolProp returned saturated air for it), so a `"via": "isobaric"`
  on a psychrometric chart raises instead of drawing a wrong state.

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
