# CoolPlot 1.0: review and plan

Basis: branch `chp/release-0.3` (13,052 lines in `src/coolplot`, 3,771
lines of tests, 1,739 lines of docs), CoolProp 8.0.0, matplotlib 3.11,
plotly 7.1, Python 3.13, four cores. Three independent reviews (architecture
and API, documentation from a new user's view, numerics and thermodynamics)
plus measurements made for this document. Everything measured is
reproducible with the scripts named in the text.

The work plan that follows from this review, with the decisions it rests
on and what "done" means for each release, is in [v1_plan.md](v1_plan.md).

## 1. Verdict in short

* The spine of the package is right and should stay: an immutable
  description of the chart (spec) -> a plan -> an engine with a cache ->
  composition into a backend-neutral scene -> renderers that only draw
  what changed, with SI units inside and display units at the edges, and
  a conformance kit that holds every backend to one contract.
* The numerics review found wrong physics in released behaviour:
  blend isochores inside the dome drawn 20 to 30 % off when the flash
  solver is used (CoolProp 8 returns an inconsistent T,rho mixture state
  without raising, and CoolPlot accepts it), blend charts empty on
  CoolProp 6.8 and 7.2 for all but isotherms and quality lines,
  incompressibles not plottable although documented, and cache keys that
  ignore CoolProp's reference state. These go into a 0.3.1 before any
  1.0 work (section 7.1).
* Everything around the spine has grown by accretion over three release
  cycles and is not yet 1.0 material: two parallel chart implementations
  (property diagrams and psychrometric charts), an inconsistent public
  vocabulary, two unit tables, scope that does not belong in a plotting
  library (a PDF parser, an HTTP server with inline JavaScript), 57 blanket
  `except Exception`, and a documentation set with no reference, no
  pictures and several wrong statements.
* The C++ question is about reach, not speed: CoolProp has 19 wrappers
  besides Python and none of them can use a Python package. CoolProp's C++ library
  already contains `CoolProp::Plot` (a port of the old Python
  `PropertyPlot`), but it reaches no wrapper and uses the algorithm
  CoolPlot replaced. The way to "mirror all wrappers" is to put the
  numerics (isolines, dome, cycles, humid air) into `CoolProp::Plot` and
  expose it where every wrapper already looks (the SWIG interface,
  nanobind, `CoolPropLib.h`, emscripten), and to make the presentation
  (layout, styles, SVG, PDF) a C++ library that does not depend on
  CoolProp at all, so it links anywhere. CoolPlot's Python package then
  becomes one of several thin presentation layers. Section 6 sets out
  the design, the costs and the migration; it does not require the
  Python consolidation to be finished first, but it does require the
  contracts that the consolidation defines.
* Performance, for the record: CoolPlot's own Python is 0.06 to 0.17 s
  per pure-fluid chart; blends take 42 s of which 39 s are CoolProp
  mixture flashes. Native code changes neither; cheaper flash inputs
  and parallel lines do (section 2.2).

## 2. Numbers

### 2.1 Size and complexity

| Module | Lines | Maintainability (radon, A best) | Note |
|---|---|---|---|
| render/mpl.py | 1102 | C (0) | `describe_item` complexity D (26) |
| render/svg.py | 827 | C (0) | |
| testing/kit.py | 825 | C (2) | the conformance kit, `run_conformance` 128 lines |
| thermo/tracer.py | 799 | A (25) | |
| render/web.py | 673 | A (25) | server, SSE, inline JavaScript |
| render/plotly.py | 647 | C (5) | |
| testing/pdf_reader.py | 620 | B (12) | `_read_content` complexity F (49) |
| compose/layout.py | 552 | A (23) | `_candidates` C (20) |
| diagram.py | 539 | A (36) | `add_cycle` C (20) |
| compose/psychro.py | 127 | A (57) | `compose_psychro` E (34) |

Idioms that spread: 82 `object.__setattr__` calls in nine modules (frozen
dataclasses normalising themselves in `__post_init__`), 57 `except
Exception` (42 in `thermo/`), ten private matplotlib attributes (nine in
read-back, one on the drawing path: `halo.set_rotation(artist._rotation)`,
mpl.py:532).

### 2.2 Where the time goes

Measured with a timing proxy around every CoolProp call
(`scratchpad/prof/share.py`), SVG renderer, default settings:

| Chart | Total | In CoolProp | Calls | Per call | CoolPlot's Python |
|---|---|---|---|---|---|
| R290 ph, 31 lines with labels | 0.31 s | 0.14 s (43 %) | 30,204 | 4 us | 0.17 s |
| R290 ph, no labels | 0.22 s | 0.15 s (71 %) | 30,204 | 5 us | 0.06 s |
| Water Ts | 0.47 s | 0.37 s (79 %) | 26,943 | 14 us | 0.10 s |
| CO2 ph | 0.59 s | 0.46 s (77 %) | 27,480 | 17 us | 0.13 s |
| R410A (R32/R125) ph | 41.9 s | 39.4 s (93 %) | 12,265 | 3,212 us | 2.5 s |
| Psychrometric, default lines | 0.49 s | 0.43 s (87 %) | 6,333 | 68 us | 0.06 s |

Of CoolPlot's own time, the edge label layout is the largest part (a units
change, which lays out labels again and calculates nothing, takes 0.21 s
for R290 and 0.33 s for the blend).

Cost of single CoolProp calls (`AbstractState.update`, CoolProp 8):

| Call | R290 | R410A blend |
|---|---|---|
| binding overhead (`keyed_output` of a cached value) | 0.09 us | |
| p,T single phase | 7 us | 19,600 us |
| p,Q saturation | 0.7 us | 350 us |
| h,p flash (what isolines mostly need) | 3 us | 107,500 us |

Two conclusions. First, the mixture flash is the problem, and the choice
of inputs matters by a factor of 300 (p,Q against h,p). Second, CoolProp 8
holds the interpreter lock during a flash: two threads give 1.2x to 1.3x
on four cores, not 2x. Lines of a blend chart can only run in parallel in
processes (which `background="processes"` does) or in native code.
CoolProp's tabular backend does not help: `BICUBIC&HEOS::R290` was 4x
slower than HEOS for a first chart (table build) and the blend failed
with an empty error.

### 2.3 Tests

325 tests, 5 min 10 s on this machine. The ten slowest are the blend
example (37 s) and the plotly tests (7 to 10 s each, kaleido and
Chromium); the backend conformance tests take 3 to 5 s each. Browser
tests skip silently without Playwright. 51 tests plant a defect and check
that the kit catches it; those are the suite's best asset.

## 3. What is right and should stay

* The pipeline and its boundaries: `DiagramSpec` (plain data, JSON round
  trip) -> `plan()` (pure) -> `Engine` with `CurveCache` keyed by every
  input -> `compose` (pure) -> `Scene` with stable item ids ->
  `Renderer.sync` with a `SyncReport`. Property calculations happen in
  exactly one layer.
* SI inside, display units at the edges; `format_number` as the one number
  format; `Curve` carrying its diagnostics (`n_failed`, `n_gaps`, method).
* The styling layer: validated, immutable style values; themes resolved
  before a backend sees them; the three-hue rule checked for colour
  vision deficiency.
* `Settings` split by what a change costs (calc, look, labels, page).
* The cycle description: states by number, `via` relations, loops and
  paths. It is what an engineer writes on paper.
* The label layout as a pure function with keep-out zones.
* The backend contract (docs/backends.md) and the conformance kit as the
  acceptance test, including the planted-defect tests and the browser
  read-back of the web backend.
* The comments: unusually readable for non-programmers (tracer.py,
  mpl.py); the standard to keep.
* PDF output as a checked capability (fonts embedded as TrueType, texts
  kept as text, reproducible files).

## 4. What must change before 1.0

### 4.1 One chart model, not two

`PsychrometricChart` is a second implementation, not a second chart. It
owns its own cache (psychrometric.py:62), computes curves itself
(`_curves`), resolves states itself, has its own unit table
(spec/psychro.py:23) keyed by string, its own spec and compose modules
(`compose/psychro.py` copies the state-number placement of
`compose/builder.py`), and `Interaction` tells the two apart by id prefix
(`"air/"`, `"cycle/"`). A third chart (Mollier h-x, a compressor map, a
generic chart over any two properties) would be a third copy.

1.0 needs one `Chart`:

* a quantity table that covers T, p, h, s, rho, u, Q and W, RH, Twb, Tdp,
  v, with one unit model (4.3);
* a property provider interface in `thermo` (pure fluid or blend through
  `AbstractState`, humid air through `HAPropsSI`, later others);
* a registry of line families per chart kind, each knowing how it is
  sampled and where it ends (saturation, W = 0, the chart edge);
* one facade (`Chart`, with `PropertyDiagram` and `PsychrometricChart` as
  thin constructors or presets), one `Engine`, one compose module;
* processes and cycles as one concept: a sequence of states with
  relations between them, drawn the same way on every chart.

### 4.2 A frozen vocabulary

Today: `set_isolines` / `set_lines`, `set_default_isolines` /
`set_default_lines`, `add_cycle` / `add_process` / `set_process`,
`remove_process` meaning two different things, `points` as a constructor
argument on one chart and `settings.calc.points` on the other,
`simple_compression(T_evap_C, ...)` against `rankine(p_high_Pa, ...)`,
result keys like `q_evap_J_kg`, `settings="print"` (a page size) against
`theme="print"` (colours). An engineer cannot guess any of it.

1.0 freezes one verb per operation (`set_lines`, `add_cycle`,
`remove_cycle`, `set_view`, `save`), display units with an explicit
`units=` for every user-facing number (as `add_cycle` already does), the
project's quantity naming (`T_evap_C`, `dT_sh_K`, `Q_dot_cond_kW`) for
every model input and result, and a deprecation policy (one minor release
with warnings) for what changes after 1.0.

### 4.3 Units

`"EUR"` is a misnomer (it means bar, deg C, kJ/kg, g/kg) and `"KSI"` is
cryptic; both would be stuck for years. Custom systems round-trip through
an ad-hoc dict and are excluded from hashing (core/units.py:53). The US
HVAC audience has no IP units at all (psi, F, Btu/lb).

1.0: a `Units` value with one unit choice per quantity, presets with
descriptive names (`"SI"`, `"engineering"` for bar/deg C/kJ, `"IP"`),
the same object for every chart, unit-aware printing of `StatePoint` and
`AirState` (today SI only, examples convert by hand), and error messages
that use the chart's units ("p = 300000 bar; did you mean Pa?") instead
of CoolProp's internals ("unable to calculate melting line T(p) for Simon
curve for p=3e+10").

### 4.4 Scope: out of the core package

| Component | Lines | Where it belongs |
|---|---|---|
| `testing/pdf_reader.py` (PDF parser and writer) | 620 | a test-only module under a `coolplot.testing` extra; `replace_info` through pikepdf or pypdf behind an optional import. Today `render/plotly.py` imports the parser at module level, so every plotly user ships it. |
| `render/web.py`: `WebServer`, `CLIENT_JS`, `PAGE` | about 350 of 673 | an example or a `coolplot-web` package. `WebRenderer` and its patch protocol stay: the idea is sound and the browser read-back tests depend on it. |
| `testing/kit.py` (conformance kit) | 825 | public, but as `coolplot.testing`, documented as the backend author's tool, not loaded by users. |
| `engine/background.py` | 304 | keep, but as a small state machine (4.5). |
| `interaction.py` | 117 | keep, generic over charts (4.1). |

These are 15 % of the code and had the highest churn in the review
history.

### 4.5 Error handling and accretion

* Define one `PropertyError` that wraps CoolProp's `ValueError` with the
  fluid, the inputs and their values in display units; catch that where
  "CoolProp found no state" is the expected outcome (tracing, hover), let
  everything else propagate. Blanket catches today hide programming
  errors (tracer.py:69, fluid.py:396, interaction.py:83).
* Validate fluid names in the constructor: a misspelt fluid is accepted by
  `PropertyDiagram()` and fails at the first draw.
* Rewrite the accreted functions as small state machines with one test
  per branch: `BackgroundEngine` (ten mutable fields, suspects, retries,
  pool replacement, "notify from another thread when we are the submitting
  thread"), `PropertyDiagram.draw` (ten-round progress loop with two
  warnings), `compute_isoline` (tracer -> fallback flash -> guess ->
  saturation insertion in 80 lines), `psychro_line` (three search
  strategies and status strings).
* Replace the `object.__setattr__` idiom with explicit constructors
  (`IsolineSet.create(...)`) that normalise once over a plain frozen
  dataclass; `DiagramSpec.__post_init__` re-parses everything on every
  `with_` (spec/diagram.py:189-216).
* Remove the one private matplotlib attribute on the drawing path (store
  the data angle of a text yourself); the nine in read-back are
  acceptable for a test kit and should be fenced off with a version test.

### 4.6 Tests

* Mark browser and kaleido tests as opt-in markers instead of
  skip-on-missing, so CI cannot lose them silently; remove the hard-coded
  `/opt/pw-browsers` paths.
* Fold `test_review_fixes.py` (a changelog, not a module boundary) into
  the modules it covers.
* Cut the blend example in the test suite to a few lines (37 s today).
* Keep every planted-defect test.

## 5. Documentation

What a new user finds today (full list in the review log): four Markdown
files and a README with no picture, no API reference (about 40 exported
names and 164 public functions without a documented home; the docstrings
use Sphinx roles that nothing renders), wrong statements
(`INCOMP::MEG[0.3]` listed as a working fluid but every incompressible
chart fails at draw; `set_isolines("p")` in the ph example; `from
CoolPlot import` in the styling guide; a section cross-reference off by
one; backends.md naming two backends where there are four; a broken code
span in the changelog), computer-science vocabulary in the first screen
of the README and in the user guide ("backend", "scene", "sync",
"immutable"), and 30 lines of font-embedding detail in the tutorial.

1.0 documentation: Sphinx with MyST (keep the Markdown), numpydoc
docstrings with a linter, sphinx-gallery with the examples rendered and
tested at build time, Read the Docs, and the Diataxis split: getting
started with one picture and a ten-line chart; tutorials (first log(p)-h
chart, a heat pump from measured states, a psychrometric chart for an air
handling unit, figures for a paper); how-tos (units, isolines, labels,
cycles, blends, PDF and print, themes, embedding in a GUI, interactive
apps, troubleshooting with the real error texts); explanations (what a
change costs, colours, numerics, label placement, what is not
supported); the generated reference with tables of fluids, diagram types,
units, presets and aliases; contributing (pipeline and layer rules only;
the design log and the fix history move to a history page); a gallery;
and a changelog in Keep-a-Changelog form with an upgrade guide.

## 6. A C++ plotting library next to the C++ calculation library

### 6.1 The goal and what exists

The goal is reach: CoolProp is a C++ library with wrappers (the
`wrappers/` directory of CoolProp 8) for Android, Delphi, EES, Excel,
Fluent, Fortran, JavaScript (WebAssembly), Julia, LabVIEW, LibreOffice,
Lua, MATLAB, MathCAD, Mathematica, Modelica, Python, Rust, SMath and
VB.NET. A C++ CoolPlot built the same way would
give every one of them property diagrams. Today only Python has them
(MATLAB reaches them through `matpy.m`, which calls Python).

What already exists upstream, found while writing this document:

* `include/CoolProp/plotting/CoolPropPlot.h` and `src/CoolPropPlot.cpp`
  (about 1,000 lines with tests): `CoolProp::Plot::PropertyPlot` with
  `calc_isolines`, `isoline_range`, `value_at`, `supported_isoline_keys`,
  the seven diagram types and the `TPLimits` presets. It is a port of the
  old Python `CoolProp.Plots.PropertyPlot`: isolines are a fixed grid of
  x or y values with one flash per point, failures become NaN (and a
  line on `std::cerr`), the two-phase region is not treated, and
  `process_fluid_state` parses the fractions of a blend and then builds
  the state without setting them.
* It is wired to nothing: not in `src/CoolProp.i` (the SWIG interface
  behind the scripted-language wrappers), not in
  `nanobind_interface.cxx` (Python: `dir(CoolProp.CoolProp)` has no plot
  names), not in `emscripten_interface.cxx` (JavaScript), not in
  `CoolPropLib.h` (the C ABI with 81 exported functions that Excel,
  LabVIEW, MathCAD and the MATLAB DLL route use).
* `CoolProp.Plots` (the legacy Python module, with `PsychChart.py` and
  `SimpleCycles.py`) still ships in the CoolProp 8 wheel.

So the ecosystem has three implementations of isolines (legacy Python,
dormant C++, CoolPlot's tracer) and the one with the best algorithm is
the one that cannot reach the wrappers.

### 6.2 The design that mirrors the wrappers

Three parts, split by what they depend on:

1. **Numerics in CoolProp: `CoolProp::Plot`.** Everything that needs an
   `AbstractState`: isoline tracing (CoolPlot's tracer ported, with
   saturation bounds from the phase envelope, two-phase handling,
   saturation points inserted where a line meets the dome), the dome,
   quality lines, cycle state resolution (`via` relations, efficiencies,
   loops), humid-air lines (`HAPropsSI`), `value_at` for hover. Input:
   fluid string, chart kind, line family, values, region, calculation
   settings. Output: polylines in SI with diagnostics (points failed,
   gaps, method). No units, no text, no styles. This replaces the
   dormant code in place and keeps its name.
   Exposure, once each, in the places every wrapper already consumes:
   `%include "CoolProp/plotting/CoolPropPlot.h"` in `CoolProp.i` (all
   SWIG targets), a nanobind module (Python), the emscripten interface
   (JavaScript), and a handful of C functions in `CoolPropLib.h` in the
   style of `AbstractState_*` (a handle, `errcode`, `message_buffer`,
   arrays by pointer and length) for Excel, LabVIEW, MathCAD, Fortran and
   the MATLAB DLL route. The fluid, backend and REFPROP configuration
   stay the user's: there is no second copy of CoolProp.
2. **Presentation as a C++ library that does not depend on CoolProp.**
   `coolplot-core`: the chart description (today `DiagramSpec`, as JSON
   in and out, which already exists), units and number formatting, line
   values with rounding, the scene (items with ids, styles resolved from
   a theme), the edge label layout (it estimates text width from the
   character count and the font size, so it needs no font engine), an
   SVG writer, and a PDF writer with TrueType subsetting (the knowledge
   is in `testing/pdf_reader.py` today). Input: a spec and the polylines
   from part 1. Output: scene JSON, SVG, PDF. Because it links nothing
   but the C++ standard library, it compiles in CoolProp's wrapper
   builds, to WebAssembly, and into any application, and it can be
   wrapped with the same SWIG and nanobind machinery or used through a
   two-function C ABI (`coolplot_scene_json(spec_json, curves)`,
   `coolplot_svg(...)`). Rasters (PNG) are left to the platform or an
   optional dependency later.
3. **Native renderers per platform, where they add something.** Python:
   matplotlib, plotly and the browser backend, consuming scene JSON (the
   `Scene` -> `Renderer.sync` design stays as it is). MATLAB: a small
   `.m` that draws scene JSON with `plot` and `text`. JavaScript: a
   canvas or SVG renderer of scene JSON, which makes the browser backend
   server-free (today it needs a Python process and SSE). Excel,
   LabVIEW, Julia: the polylines of part 1 into their own charts, or the
   SVG and PDF of part 2 as files.

What each platform gets:

| Platform | Through | Gets |
|---|---|---|
| Python | nanobind (part 1) and the CoolPlot package (parts 2, 3) | everything, as today, with the tracer in C++ and threads that run in parallel |
| MATLAB, Julia | `matpy.m` (Python) or the C ABI; `ccall` | polylines for native plots; SVG and PDF files from part 2 |
| Excel, LibreOffice, LabVIEW, MathCAD, Fortran, Delphi, VB.NET | the C ABI (`CoolPropLib.h`) | polylines as arrays; SVG and PDF files from part 2 |
| JavaScript | emscripten | charts in the browser without a server |
| Lua, Rust, Android | SWIG or FFI | polylines; SVG and PDF |
| EES, Fluent, Modelica, Mathematica, SMath | their CoolProp interfaces | polylines where arrays can cross the interface; otherwise files |

### 6.3 Costs, risks and what it does not solve

* Size: part 1 replaces about 2,700 lines of Python (`thermo/`,
  `engine/plan.py`) and 1,000 lines of upstream C++; expect 4,000 to
  5,000 lines of C++ with Catch2 tests. Part 2 replaces about 3,500
  lines of Python (`spec/`, `style/`, `compose/`, `scene.py`,
  `render/svg.py`, `render/ticks.py`) plus a new PDF writer; expect
  5,000 to 7,000 lines. Together this is of the order of the Python
  package as it stands (13,000 lines over three release cycles), so one
  to two person-years including the wrapper work and documentation.
* Two implementations until the Python tracer and composer are retired.
  The mitigation is to make CoolPlot's Python tests the acceptance tests
  of the C++ code: the same spec must give the same curves (within
  tolerance) and the same scene, and the conformance kit must stay green
  with the C++ scene feeding the existing renderers.
* Coordination with CoolProp releases: part 1 ships with CoolProp, so a
  CoolPlot feature that needs a new line family waits for a CoolProp
  release. Keep the Python tracer as a fallback for one or two releases.
* Interactivity stays per platform: events, dragging states and the
  background engine are Python and browser code and will remain so; part
  2 only has to make a scene fast enough to re-lay out on every drag
  (0.2 to 0.3 s today in Python; C++ will be well under that).
* Text metrics: the layout estimates widths, as today; it does not
  measure fonts. That is a known approximation, acceptable because labels
  sit at the edges with keep-out margins.
* Performance is not the reason and should not be promised as one:
  the tracer in C++ removes CoolPlot's 0.06 to 0.17 s per chart and
  allows parallel lines (CoolProp 8 holds the interpreter lock in
  flashes, measured at 1.2x on two threads), but blend charts stay
  dominated by CoolProp's mixture flashes until the tracer uses cheaper
  inputs (p,Q and T,rho against h,p: a factor 300 per call, section
  2.2). That change belongs in part 1 regardless of language.
* What a standalone C++ CoolPlot with its own CoolProp inside would get
  wrong: the Python wheel exports no linkable C++ symbols, so it would
  bundle a second CoolProp (40 MB), with version skew, fluids loaded
  twice, states not shareable with the user's CoolProp, and each
  platform would need a new wrapper for it. Parts 1 and 2 avoid this:
  the numerics live where the wrappers are, and the presentation needs
  no CoolProp.

### 6.4 Recommendation

Yes, in this form: numerics into `CoolProp::Plot`, presentation as a
CoolProp-free `coolplot-core`, thin native layers per platform. Order of
work:

1. Fix the contracts in Python first, where change is cheap (sections 4.1
   to 4.3): one chart model, the spec JSON schema, the curve record
   (`family, value, x[], y[], diagnostics`), a scene JSON schema (the
   `Scene` is not serialisable today; the web backend serialises SVG
   elements instead), units and vocabulary. These are the interfaces of
   parts 1 and 2; getting them right in Python with the existing tests
   costs weeks, in C++ with wrappers it costs months.
2. Upstream, in parallel: a pull request that replaces the body of
   `CoolProp::Plot` with the tracer, fixes the blend fractions, adds the
   dome, quality lines and cycle states, and includes the header in
   `CoolProp.i`, nanobind and `CoolPropLib.h`; plus the one-line
   `gil_scoped_release` in the Python binding. CoolPlot uses
   `CoolProp.Plot` when the installed CoolProp has it.
3. `coolplot-core` (part 2) as its own repository with CMake, Catch2 and
   the SVG writer first (the PDF writer second), built in CoolProp's
   wrapper matrix as an optional component and published as a Python
   wheel for CoolPlot.
4. CoolPlot 1.0: the Python package keeps `PropertyDiagram`,
   `PsychrometricChart`, the matplotlib, plotly and browser renderers,
   interaction and the background engine, over the C++ core, and retires
   its own tracer and composer once the C++ passes the full suite.
   `CoolProp.Plots` in CoolProp is retired or re-pointed in the same
   step.

## 7. Numerics and thermodynamics

From the numerics review (scripts and logs under `scratchpad/numrev/`,
run on CoolProp 8.0.0, 7.2.0 and 6.8.0: every fluid of a set of awkward
ones, all seven diagram types, all line families, every point of every
ph line round-tripped through an h,p flash).

### 7.1 Wrong, fix in 0.3.1 before anything else

1. **Blend isochores inside the dome are drawn 20 to 30 % off with
   `solver="flash"`, and at every point where the tracer falls back to a
   flash.** CoolProp 8's T,rho mixture flash returns an inconsistent
   state without raising (it reports Q = -1 while p and h belong to
   another density: `AbstractState("HEOS", "R407C.mix").update(DmassT_INPUTS,
   100, 264.16)` gives p = 307067 Pa, h = 285269 J/kg, and the h,p flash
   at that point returns rho = 27.5 kg/m3, T = 258.6 K). `isolines.py:166`
   accepts it. On the R410A rho = 100 line, 66 of 242 flash points are
   wrong, the worst by a factor 14; the tracer gets the same line right.
   Fix: never accept a mixture T,rho flash unverified; check every
   accepted point with an explicit (T, rho) evaluation against the line's
   constant (one call), and report the CoolProp defect upstream.
2. **With CoolProp 6.8 and 7.2, which `pyproject.toml` declares
   supported, every blend isoline except isotherms and quality lines is
   empty** (`robust.py R410A.mix` on 7.2: s, rho and u lines with 0 valid
   points of 60). The h,s,u-p flash of a mixture needs the phase envelope
   built on the working state, and `fluid.py:208-219` only retries on the
   envelope-built guide state when Q is an input. Fix: build the envelope
   on the working state of every mixture.
3. **Incompressibles cannot be plotted at all**, although the user guide
   lists `INCOMP::MEG[0.3]`: `limits.py:31` asks for the saturation range
   unconditionally and `fluid.py:404` fails on the critical point. INCOMP
   reports T_min, T_max and all properties; only the dome and the
   crossings have to be skipped. Fix: resolve saturation-relative limits
   only for `Relative` bounds and give fluids a `has_critical_point`
   capability.
4. **Cache keys ignore CoolProp's global state.** After
   `set_reference_state("R134a", "NBP")` a cached isotherm is served
   unchanged while a new diagram computes h = 256 instead of 422, and an
   old `Engine` keeps the old reference even after `cache.clear()`. Fix:
   a CoolProp configuration fingerprint (reference states, configuration
   JSON, version) in the key, and a fresh working state after a change.
5. `_W_by_search` (humid_air.py:144) returns "ok" after 60 iterations
   without convergence; it has to return "failed".

### 7.2 Unverified and to be settled

6. Tracer isochores of R32/R1234yf 50/50 in a ph chart disagree with
   h,p round-trips at p < 300 Pa (worst by a factor 1400 on the
   rho = 1 line, 20 points on rho = 10), near the bottom of the default
   region (p_min = 1.01 p_triple = 24 Pa). Isentropes, isenthalps,
   u-lines and isotherms of the same blends round-trip to 2e-4 on all
   250 points, so it is specific to the T,rho pair there; either the
   tracer's unbracketed root (tracer.py:759-799) or CoolProp's h,p flash
   is wrong. To be decided with a third evaluation (T, rho explicit).

### 7.3 Robustness

7. Quality lines of zeotropes break 10 to 15 K below the critical point
   (R32/R1234yf, Q = 0.7: 58 of 250 points fail from 344 K to
   T_c = 357.7 K with 16 gaps; R407C Q = 0.3: 17 failures), because
   `compute_quality_line` does one Q,T flash per point while the dew and
   bubble lines come from the envelope and are fine. The default region's
   T_min = 1.01 T_triple is also too close for R410A at 100 bar (one NaN
   at 149.98 K).
8. Cycle models: the physics is right (a hand calculation of the R134a
   -10/40 deg C cycle matches to all digits, COP 2.89354; flash-tank and
   economiser balances close to 1e-8; dew and bubble conventions for
   blends verified). The messages are not: a condensing temperature above
   the critical point gives CoolProp's raw text, a huge superheat a raw
   flash error, `via="isothermal"` with key `"p"` silently returns the
   previous state, and h,T is unsupported for blends without a hint.
9. Humid air: no physics error; Twb, h and v lines round-trip through
   HAPropsSI to 1e-7 at 101.3, 80 and 60 kPa, start exactly on saturation
   and end at W = 0. The review measured the direct W(T, Twb) call as
   fast at its sample points; the search exists because of the gaps and
   slow calls near 0 deg C found earlier (humid_air.py docstring), so the
   choice should be made per CoolProp version with a table of measured
   failures, not by assumption.

### 7.4 The algorithm, and what a 1.0 core should do

Today every line is a fixed grid of 250 points in T (linear) or p (log)
with one flash or one traced solve per point, no adaptivity. The
consequences, measured: a 5 bar isobar of R407C in a Ts chart has 6 of
252 points inside the dome (glide 6.2 K against a step of 1.19 K), so the
curved two-phase part is a chord; ends outside the equation of state are
still paid for (Water s = 12500: 143 of 250 flashes wasted; Ammonia
s = 0: 62); blends rebuild the saturation bracket at every pressure (two
p,Q flashes per point) and run a regula falsi of p,Q flashes inside the
dome (R407C s = 1700 in ph: 738 p,Q and 681 T,rho updates for 100
points). The tracer itself is sound: where tracer and flash both converge
they agree to 1e-11, every pure-fluid line round-trips to 1e-9, CO2
isotherms and isobars within 0.05 K and 0.1 % of the critical point
trace cleanly, and quality lines close at the critical point.

A 1.0 core, in Python now and in `CoolProp::Plot` later (section 6):

* one continuation tracer for every line, pure or blend, parametrised by
  arc length in plot coordinates with curvature-controlled steps, never
  a per-point cold flash;
* the phase boundary handled once per fluid: build the envelope or
  saturation curve, intersect each line with it, trace the two-phase
  branch in quality (for pure fluids h, s, u and v are linear in Q: one
  secant step);
* clip the sweep to the domain box before tracing and stop lines at the
  limits with a reason, not NaN;
* validate every accepted point by an explicit (T, rho) evaluation
  against the line's constant;
* a fluid abstraction with explicit capabilities (critical point,
  envelope, supported input pairs), so incompressibles and tabular
  backends have a path and mixture states always carry an envelope;
* cheaper inputs for blends (p,Q and T,rho against h,p, section 2.2);
* an error taxonomy for cycles (above critical, outside the equation of
  state, unsupported pair) with messages in the user's units;
* units: add specific volume, temperature differences and gauge pressure
  (the latter needs care on log axes).

The label layout is deterministic and O(N^2) in the number of labels:
20 labels 0.02 s, 100 labels 0.18 s, 400 labels 1.5 s. Good enough for
interactive use up to about 100 labels; vectorise `Piece.project` and
`visible_pieces` beyond that.

## 8. Roadmap

| Release | Scope | Removes |
|---|---|---|
| 0.4 | one `Chart` over a quantity table and property providers; psychrometry as configuration; one compose module; `Interaction` generic; the curve record and the scene JSON schema written down | `compose/psychro.py`, `spec/psychro.py`, the second unit table |
| 0.5 | frozen vocabulary and units model (4.2, 4.3); `PropertyError`; constructor validation; unit-aware state printing; IP units | old method names (with warnings) |
| 0.6 | scope split: `coolplot.testing` (kit, PDF check), web server to an example or its own package, PDF parser test-only; background engine and `compute_isoline` as state machines | `testing/pdf_reader.py` from the runtime |
| 0.7 | numerics (section 7) in the Python tracer, and the same algorithm proposed upstream for `CoolProp::Plot` with the Python tests as acceptance tests | |
| 0.8 | documentation set (section 5), gallery, API reference, changelog with upgrade guide | |
| 0.9 | CoolPlot runs on `CoolProp.Plot` where available, `coolplot-core` feeds the renderers; deprecation period: warnings on, nothing removed | |
| 1.0 | removals, stable API, release; the Python tracer and composer retired when the C++ passes the full suite | `thermo/tracer.py`, `compose/` (kept only as fallback if the C++ is not released in time) |

Each release keeps the conformance kit green on all backends and the
test suite under five minutes. The upstream pull request for
`CoolProp::Plot` and the `gil_scoped_release` can start at 0.4, as soon
as the curve record is fixed.

## 9. Open decisions for the maintainers

1. Where `coolplot-core` (the presentation library) lives: its own
   repository built into CoolProp's wrapper matrix as an optional
   component (recommended: its own release cadence, no CoolProp
   dependency), or inside the CoolProp tree.
2. Which wrappers get a native renderer (part 3) in 1.0, and which get
   polylines and files only. The recommendation: Python and JavaScript
   native, MATLAB a small `.m`, everything else arrays, SVG and PDF.
3. What happens to `CoolProp.Plots` in CoolProp 8.x: retire it, point it
   at `CoolProp.Plot` plus CoolPlot, or keep it.
4. Unit vocabulary: the name for the bar/deg C/kJ set that replaces
   `"EUR"`, and whether IP units are in 1.0.
5. Which of `set_process` (SI state points) and `add_cycle` (display
   units) survives; the recommendation is `add_cycle` with `units=`.
6. Whether `WebServer` lives on anywhere; with a JavaScript renderer of
   scene JSON (6.2, part 3) it becomes unnecessary.
