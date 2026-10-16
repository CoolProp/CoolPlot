# CoolPlot 1.0: review and plan

Basis: branch `chp/release-0.3` (13,052 lines in `src/coolplot`, 3,771
lines of tests, 1,739 lines of docs), CoolProp 8.0.0, matplotlib 3.11,
plotly 7.1, Python 3.13, four cores. Three independent reviews (architecture
and API, documentation from a new user's view, numerics and thermodynamics)
plus measurements made for this document. Everything measured is
reproducible with the scripts named in the text.

## 1. Verdict in short

* The spine of the package is right and should stay: an immutable
  description of the chart (spec) -> a plan -> an engine with a cache ->
  composition into a backend-neutral scene -> renderers that only draw
  what changed, with SI units inside and display units at the edges, and
  a conformance kit that holds every backend to one contract.
* Everything around the spine has grown by accretion over three release
  cycles and is not yet 1.0 material: two parallel chart implementations
  (property diagrams and psychrometric charts), an inconsistent public
  vocabulary, two unit tables, scope that does not belong in a plotting
  library (a PDF parser, an HTTP server with inline JavaScript), 57 blanket
  `except Exception`, and a documentation set with no reference, no
  pictures and several wrong statements.
* Performance is CoolProp's, not CoolPlot's. For pure fluids a full chart
  takes 0.2 to 0.6 s, of which CoolPlot's own Python is 0.06 to 0.17 s.
  For blends a chart takes 42 s, of which 39 s are CoolProp mixture
  flashes at 3 ms each (108 ms for an h,p flash). Call overhead between
  Python and CoolProp is 0.09 us per call, below 3 % of any chart.
* A C++ rewrite of CoolPlot is therefore not worth it, and a standalone
  C++ CoolPlot would have to bundle its own copy of CoolProp. What does
  make sense, if reaching CoolProp's other 19 platforms is a real goal,
  is a small numerics core (isoline tracing, dome, cycle states, humid-air
  lines) inside CoolProp itself, reached through its existing wrappers,
  with CoolPlot staying the Python presentation layer. Section 6 sets
  this out with the numbers; the decision does not have to be taken
  before the Python consolidation, which is needed either way.

## 2. Numbers

### 2.1 Size and complexity

| Module | Lines | Maintainability (radon, A best) | Note |
|---|---|---|---|
| render/mpl.py | 1102 | C (0) | `describe_item` complexity D (26) |
| render/svg.py | 827 | C (0) | |
| render/testing.py | 825 | C (2) | the conformance kit, `run_conformance` 128 lines |
| thermo/tracer.py | 799 | A (25) | |
| render/web.py | 673 | A (25) | server, SSE, inline JavaScript |
| render/plotly.py | 647 | C (5) | |
| render/pdf_reader.py | 620 | B (12) | `_read_content` complexity F (49) |
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
| `render/pdf_reader.py` (PDF parser and writer) | 620 | a test-only module under a `coolplot.testing` extra; `replace_info` through pikepdf or pypdf behind an optional import. Today `render/plotly.py` imports the parser at module level, so every plotly user ships it. |
| `render/web.py`: `WebServer`, `CLIENT_JS`, `PAGE` | about 350 of 673 | an example or a `coolplot-web` package. `WebRenderer` and its patch protocol stay: the idea is sound and the browser read-back tests depend on it. |
| `render/testing.py` (conformance kit) | 825 | public, but as `coolplot.testing`, documented as the backend author's tool, not loaded by users. |
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

## 6. Should the core become a C++ library with Python bindings?

### 6.1 What native code would and would not change

Speed of pure-fluid charts: no. CoolPlot's own Python time is 0.06 to
0.17 s per chart, mostly the label layout, and the binding overhead is
0.09 us per CoolProp call (under 3 % of a chart). Native code could save
perhaps 0.1 s per chart.

Speed of blend charts: not by itself. 93 % of 42 s is CoolProp's mixture
flash. What helps is fewer and cheaper flashes: p,Q and T,rho inputs cost
0.35 ms and microseconds where h,p costs 108 ms, so tracing isolines in
the (T, rho) plane where the equation of state is explicit, with
saturation bounds from the phase envelope, is the lever. That is an
algorithm, not a language, and the numerics review (section 7) says how
far the Python tracer already goes. Native code adds one thing Python
cannot have today: parallel lines in threads, because CoolProp 8 holds
the interpreter lock during flashes. The cheapest fix for that is a
`gil_scoped_release` in CoolProp's own nanobind binding (one line
upstream), after which CoolPlot's thread pool parallelises blend charts
as it stands.

Reach: this is the real argument. CoolProp has wrappers for Android,
Delphi, EES, Excel, Fluent, Fortran, JavaScript, Julia, LabVIEW,
LibreOffice, Lua, MATLAB, MathCAD, Mathematica, Modelica, Python, Rust,
SMath and VB.NET. None of them can use a Python package. Users of MATLAB,
Excel or LabVIEW who want a log(p)-h diagram want the lines (polylines in
SI) to plot with their own tools; they do not want CoolPlot's layout,
themes or renderers, which are presentation and platform-specific anyway.

### 6.2 Three ways to do it

| | A. Python 1.0 (consolidation only) | B. Numerics core inside CoolProp | C. Standalone C++ CoolPlot |
|---|---|---|---|
| What moves to C++ | nothing | tracing, dome, cycle states, humid-air lines, about 2,700 Python lines today (thermo/, engine/plan.py) | all of it, including layout and renderers |
| Reach | Python; MATLAB, Julia and Excel through their Python bridges | every CoolProp wrapper, through `CoolPropLib.h` and the SWIG interfaces that exist | each platform would need a new wrapper for CoolPlot |
| CoolProp binary | the user's | the user's | a second copy bundled in CoolPlot's wheel (the Python wheel exports no linkable C++ symbols: 35 headers ship, 2 `AbstractState` symbols), version skew, fluids loaded twice, states not shareable |
| Parallel blends | processes only (or the upstream GIL fix) | threads, inside CoolProp | threads |
| Text, fonts, PDF | matplotlib, plotly, the SVG writer | unchanged, stays in Python | a TrueType subsetter and a PDF writer in C++, or platform libraries |
| Cost (estimate) | 3 to 4 release cycles of refactoring | plus about 5,000 lines of C++ with tests, SWIG interface changes, upstream review; CoolPlot gains a fallback path | the largest by far, and the hardest build matrix |
| Risk | low | medium: two implementations until the Python tracer is retired; coordination with CoolProp releases | high: duplicated CoolProp, no reach gained without wrapper work per platform |

Note that CoolProp 8 still ships `CoolProp.Plots` (the legacy module
CoolPlot was forked from, with `PsychChart.py` and `SimpleCycles.py`), so
the ecosystem already carries two implementations. Option B would also
settle that: `CoolProp.Plots` becomes a thin call into the numerics
core, or is retired in favour of CoolPlot.

### 6.3 Recommendation

1. Do the Python 1.0 (option A) first. It is needed under every option,
   and it produces the contract that any native core would have to
   implement: `(fluid, chart kind, line family, value, region, settings)
   -> polyline with diagnostics`. Keep that contract free of Python types
   (plain numbers, strings, arrays) from the start.
2. Decide option B on two facts, not on taste: whether reaching the
   non-Python platforms is a stated goal of the project, and the numerics
   review's verdict on the tracing algorithm (section 7). If both say
   yes, propose a `CoolProp::Plot` numerics module upstream with C entry
   points in `CoolPropLib.h`, port the tracer there, and let CoolPlot use
   it when the installed CoolProp has it and its own tracer otherwise.
   One sentence of the plan should go to CoolProp first: a
   `gil_scoped_release` in the Python binding, which costs nothing and
   helps every user.
3. Do not take option C.

## 7. Numerics and thermodynamics

(Section completed from the numerics review; see below.)

## 8. Roadmap

| Release | Scope | Removes |
|---|---|---|
| 0.4 | one `Chart` over a quantity table and property providers; psychrometry as configuration; one compose module; `Interaction` generic | `compose/psychro.py`, `spec/psychro.py`, the second unit table |
| 0.5 | frozen vocabulary and units model (section 4.2, 4.3); `PropertyError`; constructor validation; unit-aware state printing; IP units | old method names (with warnings) |
| 0.6 | scope split: `coolplot.testing` (kit, PDF check), web server to an example or its own package, PDF parser test-only; background engine and `compute_isoline` as state machines | `render/pdf_reader.py` from the runtime |
| 0.7 | numerics (section 7): tracing in (T, rho) for blends, fewer flashes, the open physics items | |
| 0.8 | documentation set (section 5), gallery, API reference, changelog with upgrade guide | |
| 0.9 | deprecation period: warnings on, nothing removed | |
| 1.0 | removals, stable API, release | |

Each release keeps the conformance kit green on all backends and the
test suite under five minutes. The C++ decision (6.3) can be taken at
0.6, when the curve contract is fixed; the upstream GIL request can go
now.

## 9. Open decisions for the maintainers

1. Is reaching MATLAB, Excel, LabVIEW and the other wrappers a goal of
   CoolPlot, or is Python the product? This decides option B.
2. What happens to `CoolProp.Plots` in CoolProp 8.x: retire it, point it
   at CoolPlot, or keep both?
3. Unit vocabulary: `"engineering"` or another name for the bar/deg C/kJ
   set that replaces `"EUR"`; and whether IP units are in 1.0.
4. Which of `set_process` (SI state points) and `add_cycle` (display
   units) survives; the recommendation is `add_cycle` with `units=`.
5. Whether `WebServer` lives on anywhere; if nobody uses it, drop it and
   keep `WebRenderer` with its tests.
