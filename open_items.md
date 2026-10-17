# Open items (session notes, not filed anywhere)

## Upstream (CoolProp), texts drafted in scratchpad/upstream/
- DmassT mixture flash returns an inconsistent state without raising
- (new, C0) master H-p flash of mixtures refuses or misplaces two-phase states 8.0.0 solves
- release the GIL in AbstractState.update (nanobind)
- CoolProp::Plot drops blend fractions; not exposed to any wrapper (both done on chp/plot-numerics)

## Decisions taken by default (plan D1-D10), to be confirmed or reverted
- D1 C++ split, D2 CoolProp 8 minimum at 1.0, D3 "engineering" units, D4 add_cycle only,
  D5 WebServer to examples, D6 one-release deprecation, D7 coolplot-core as cpp/ for now

## Found on the way (0.4)
- TpLimits (fluids, relative bounds) and Region (humid air, absolute bounds) are two classes in
  the same spec slot; one Region with optional Relative bounds could replace TpLimits in 0.5
  (JSON of TpLimits would change: T_min/T_max/p_min/p_max -> bounds).
- Psychrometric charts now take settings.calc.points (250) instead of their own 100; the default
  chart takes 0.9 s instead of 0.4 s. Pass points=100 to get the old speed.
- ProcessSpec / PropertyDiagram.set_process kept untouched (D4 retires it in 0.5 with a warning);
  it cannot be expressed as a CycleSpec exactly (markers on a subset of the line states).
- Lines of relative humidity carry role "quality" (the theme's quality style); backends that
  style by role see RH lines as quality lines. Documented in contracts.md.
- Settings.labels.edges default changed from the fluid table to (): saved settings JSON now
  shows "edges": []; old JSON with the full table still loads.
- Humid-air default line counts come from Family.default_num + nice rounding instead of fixed
  steps with a 3..15 clamp; for unusual ranges the step can differ from the old 5 K / 10 kJ/kg.

## Found on the way (0.5)
- Deferred from the 0.5 scope: replacing the object.__setattr__ normalisation in the frozen spec
  dataclasses by explicit constructors (churn in every spec class, no user-visible effect) and the
  blanket `except Exception` in tracer.py (CoolProp failures there are the expected outcome; a
  narrower catch needs the CoolProp exception types pinned per version).
- "KSI" kept as a name (kilo-SI); "print" is both a settings preset (page size) and a theme name.
- PsychrometricChart.points property kept as a shortcut to settings.calc.points.

## Found on the way (0.6)
- The complexity criterion ("radon cc -n C prints nothing") is met for the library outside
  coolplot/testing (the kit and the PDF parser: check_events F 41, _read_content F 49) and outside
  the numerics that 0.7 rewrites (compute_isoline D 23, psychro_line D 28, path crossings, the
  tracer). Both groups are listed by `radon cc -n C src/coolplot` and stay on the list until 0.7
  (numerics) and a later cleanup of the kit.
- examples/two_stage_cycles.py has module-level imports after a sys.path line (flake8 E402),
  pre-existing.
- The browser and kaleido tests are opt-in now; CI (.github/workflows/tests.yml runs plain
  pytest) no longer exercises them unless the workflow passes --run-browser --run-kaleido.

## Found on the way (0.7)
- The default line values of a fluid chart (linear grid without rounding) start and end on the
  range ends, so the first and last isentrope, isochore and isenthalp of a chart touch the axes'
  area at one corner only; they are now dropped silently (Curve.reason says so). Before 0.7 they
  were computed and drawn outside the axes, i.e. invisible. The plan could skip the range ends.
- Quality lines of pure fluids keep the fixed temperature grid with "critical" or "linear"
  spacing (Settings.calc.saturation_spacing); only the mixture lines of intermediate quality
  are stepped adaptively. The setting is meaningless for mixtures.
- A cold flash of a mixture from h,p or s,p costs 0.06 to 1 s in CoolProp 8 (p,T 5 ms, p,Q
  0.4 ms); every tracer refusal near the critical point still pays it. The R407C chart draws
  in 11 s mostly because its p,Q flashes (three components) cost twice R410A's.
- Isolines of constant v (specific volume) are not offered as a family; v is a state quantity
  only. A "pv" diagram type is not defined either.
- The run-time check that a traced point satisfies its constant is the Newton residual
  (RESIDUAL_RTOL 1e-9) and the secant tolerance (QUALITY_RTOL 1e-8 of the dome width); the
  review's "explicit (T, rho) evaluation of every accepted point" is done by the slow tests
  (tests/numerics, --run-slow), not at run time.
- Inverse flashes of pure fluids (T from h,p) agree with the forward state to about 1e-9, so
  the acceptance "round-trips to 1e-9" is checked at 1e-8 of the property range.
- Pre-existing flake8 findings outside the files 0.7 touched: core/cycle.py E127, render/plotly.py
  E303/E302, render/svg.py E128 (3), render/web.py E128, style/theme.py E128, testing/kit.py E128.
- CI now tests CoolProp 8.0.0 only (D2); the 6.8 and 7.2 venvs in the scratchpad are unused.
- Review of 0.7 (trade-offs kept): a stretch inside the axes shorter than 1/32 of the stepped
  range can be missed while the stepper scans outside (SCAN_MAX); the last segment before a
  line leaves the axes is a chord up to the attempted step (no case above 0.03 normalised seen);
  dome ends interpolated on the phase envelope near the critical point of a blend are coarse
  (R410A isotherm 2 K below Tc: dew end 0.6 % off, 2-3 px); in R407C's retrograde band every
  point of an isotherm is flashed (Tc + 0.05 K: 95 fallbacks, 9 s).
- Pre-existing: the axis ranges come from the four corners of the T-p box and a corner below
  the melting line does not contribute, so the CO2 p-h chart with DEF limits has no liquid
  region on its h axis (h from 432 kJ/kg; the saturated liquid at 300 K is at 283 kJ/kg). The
  lines there are now clipped at the axes, as every other line.
- Points the tracer hands to a cold flash carry CoolProp's mixture flash tolerance (s off by up to
  5e-4 relative seen on R32/R125); the sweep tests check them at 1e-3, the tracer's points at 1e-6.

## Found on the way (0.8)
- The documentation review's list of 24 findings was not kept as a file; the checklist in
  docs/contributing/review_checklist.md was reconstructed from docs/v1_review.md section 5 and
  the state of the documents.
- sphinx-gallery runs the examples in examples/ and leaves their output files there (ignored by
  git). The web application example is not in the gallery (it starts a server).
- The reference documents every module; a class's members are on its module page, not on a
  page of their own. "Every public name has a reference page" is met at module granularity.
- Read the Docs is configured (.readthedocs.yaml) but the project has to be imported on
  readthedocs.org by a maintainer; the README says the documentation is published there.
- Pre-existing flake8 findings outside the touched files remain (see 0.7).
- The documentation build (CI and Read the Docs) pins CoolProp 8.0.0 like the test matrix; a new
  CoolProp release changes gallery numbers only when the pin is moved.

## Found on the way (C0, CoolProp::Plot port on coolprop/coolprop chp/plot-numerics)
- Upstream text 4 drafted (scratchpad/upstream/4_mixture_HP_flash_on_master.md): CoolProp master
  (8.1.0dev, 022b63e) refuses or misplaces two-phase H-p states of mixtures that 8.0.0 solves
  (R32/R125 at 9.65 bar refused by the residual gate added after 8.0.0; R407C isochore point
  flashes back to another density). CoolPlot's tests/test_thermo.py round-trip test fails on
  master for that reason; CI pins 8.0.0. The tracer-vs-flash tests (Python and C++) compare only
  where the flash converges (at least 5 of 7 pressures).
- The port covers the isolines, the dome and the T-p box only. Not ported: the states of cycles
  and their process paths, humid-air lines, the labels, the Python-side Fluid API (diagnose,
  v, check_state). CoolPlot's Python numerics stay the reference and the fallback.
- The port is exposed as CoolProp.CoolProp.Plot (the nanobind core module); the package
  __init__ does not re-export it, so that the import-tree parity gate between the legacy and
  the nanobind package stays untouched. The old CoolProp.Plots package is unchanged.
- The stub of the submodule (wrappers/Python/_nanobind/Plot.pyi) is a committed copy that the
  CI drift gate does not regenerate (nanobind_add_stub writes one module per call); a binding
  change needs the stubgen command in wrappers/Python/CMakeLists.txt; test_stub.py checks its
  names against the runtime.
- The SWIG interface includes the new header; no SWIG wrapper was built here (swig not
  installed), so the parse of the header (enum class, unique_ptr member, deleted copy) is
  unverified.
- CoolPlot's curve cache keys do not say which implementation computed a curve; a process that
  toggles COOLPLOT_NATIVE after computing a chart keeps the earlier curves (documented in
  thermo/native.py, no CoolPlot setting beyond the environment variable).
- The C++ Fluid resolves a predefined blend ("R407C.mix") to its components as the Python
  Fluid does; binary interaction parameters set on a state cannot be given to the port (the
  adapter falls back to Python for them).
- The legacy fixture generator dev/scripts/generate_Plot_test_data.py (fixed-grid Python
  output of CoolProp.Plots) is deleted with the fixed grid it described.
- Acceptance "the Python numerics tests pass against the C++ through nanobind": met by
  tests/test_native.py (14 tests mirroring tests/test_numerics.py plus a port-vs-Python chord
  comparison) run on a wheel built from chp/plot-numerics; the full CoolPlot suite on that
  wheel: 335 passed, 2 failed, both the CoolProp master flash difference above (one of the
  two test changes landed in tests/test_numerics.py, the other test stays as the guard it is).
- CoolProp review, left as noted: SWIG ignores the nested PropertyPlot::Axis struct (xaxis/yaxis
  unusable from SWIG wrappers; needs accessors or a struct outside the class), renames
  TPLimits::None to _None, and the generate_values_in_range(parameters, ...) overload is
  shadowed by the Scale overload; std::vector<Isoline> and std::vector<parameters> are not
  %template'd. The anonymous struct in Axis is non-standard (pre-existing). The Catch2 tracer
  test keeps a wall-clock check (tracer 0.05 s vs flash 2 s). value_at does not retry on the
  guide state. Quality lines of a tabular backend on the port use the tables; CoolPlot's adapter
  swaps to the equation of state behind them before calling.
- GIL release (decided by default): AbstractState.update releases the GIL except for REFPROP
  states; one AbstractState per thread is the rule stated in the binding's docstring.

## Found on the way (C1, coolplot-core under cpp/, CoolPlot branch chp/c1)
- D7 (coolplot-core in its own repository, built into CoolProp's wrapper matrix) is not done:
  the library lives under cpp/ in CoolPlot, so that the Python reference, the golden files and
  the C++ change in one commit. Moving it out and adding it to CoolProp's wrapper matrix (plan
  C1 step 6) needs the new repository and a CoolProp-side change, both for a maintainer.
- The C++ composer takes the curves and cycle states from the caller; the engine (planning, the
  curve cache, cycle state resolution) stays in Python. A program in another language computes
  curves with CoolProp::Plot and hands them over in the compose record.
- The PDF writer is new (no Python reference to compare with byte for byte); it passes the
  conformance kit's PDF check (fonts embedded as TrueType, texts as written, only the scene's
  colours, title, reproducible). Its page layout follows the SVG writer in points (margins
  60/15/30/45 pt by default) and differs from the matplotlib PDF.
- Fonts for the PDF writer come from the platform's font directories (TrueType .ttf files
  only; .otf with CFF outlines and .ttc collections are not read) and the files of Font.files.
  Generic families map to DejaVu, Liberation, Arial/Helvetica/Times in that order.
- The JavaScript renderer draws a static page (scene_page); the interactive WebRenderer still
  needs Python for hit testing and events.
- CI: a "core" job builds the library, runs the Catch2 tests and the whole Python suite through
  the module (COOLPLOT_NATIVE=1). Not run here (GitHub Actions); the same steps ran locally.
- From Python the coolplot-core path is slower (p-h chart: 25 ms Python composer against 65 ms
  through C++, of which 12 ms are the C++ work and the rest the JSON crossing), so it is opt-in
  (COOLPLOT_NATIVE=1); unset, CoolPlot composes in Python and uses the numerics port. Plan 0.9
  assumed the C++ scene would be the default; a binary record (curves as buffers, scene items
  as arrays) would be needed for that. The 0.9 acceptance "the scene of every example is
  identical from both paths" holds (SVG byte-identical).
- Second C1 review, trade-offs left open:
  - Quantised label scores make C++/Python divergence rarer, not impossible: two bends one ULP
    apart can still straddle a half-millionth boundary (about 1e-9 per candidate).
  - Floating-point std::from_chars/to_chars need a recent standard library; older Apple clang
    and libc++ lack them, so a macOS build may fail. Nothing in CI builds on macOS.
  - text_length/text_prefix count lead bytes on invalid UTF-8. JSON input already rejects
    invalid UTF-8; only direct C++ callers can reach it. Precondition, or count with the SVG
    writer's next_code_point.
  - A legend font of size 0 passes the style checks and makes legend_chars cast inf to int
    (undefined behaviour in C++; Python raises). Refuse size_pt <= 0 for text styles.
  - The PDF legend cut uses width_pt, the SVG one whole pixels: one character apart when
    width_pt*4/3 is not whole.
  - TrueType: loca entries are not checked against the glyf length or order, the post table
    has no length check; subset() can raise std::out_of_range (IndexError from Python, not
    ValueError).
  - The keep-out sampling is capped at 1e7 points per segment in C++; Python has no cap.
  - A genuine user error on the native path warns (fallback) and then raises from Python.

## Found on the way (0.9, CoolPlot branch chp/0.9)
- CoolProp master (8.1.0dev): the R407C isochore at 100 kg/m3 reaches 3.6 kPa / 178 K, where
  CoolProp 8.0.0 refused the states; master's HP flash there gives 3.5 kg/m3 or fails ("the (T,p)
  flash is misclassifying the phase for this mixture"). test_thermo.py::
  test_flash_isochore_of_a_blend_round_trips fails on master only. Upstream (CoolProp) item;
  CoolPlot's own consistency check of mixture states does not catch these points.
- No CI job has CoolProp's numerics port (no released wheel has it), so the example comparison
  with the port and the port tests run only locally.
- set_native_mode is process-wide (all charts and threads); a per-chart choice would need it in
  the spec or the engine. Unknown COOLPLOT_NATIVE values mean "on" (set_native_mode refuses them).
- The example test covers the scripts in examples/; examples/web_app (a server) is covered by
  tests/test_web_server.py, not by the two-path comparison. interactive_cycle records its first
  scene only (no interaction runs under Agg).
- The upgrade-guide guard covers chart methods; keyword and module-level deprecations of 1.x would
  need their own entries.

## Found on the way (1.0 RC, CoolPlot branch chp/1.0)
- Final 1.0.0: set "Development Status :: 5 - Production/Stable" and VERSION (1, 0, 0, ''), after
  feedback on 1.0.0rc1 (PyPI release by a person).
- coolplot.EUR warns through 1.x and goes in 2.0 (it never warned before 1.0).
- The stability promise covers keyword names and documented submodules, but only package names and
  chart verbs/properties are frozen by tests; freezing keyword names would make it checkable.
- get_unit_system keeps a stacklevel parameter that does nothing (internal callers still pass it).
- Chart.__getattr__ re-runs a property whose getter raised AttributeError (to show the real error);
  a getter with side effects runs twice on that path.
- rankine's signature shows **removed (for the hint on the old keywords); a __signature__ could hide it.
- Pre-existing flake8 findings (continuation indents, blank lines) in core/cycle.py, render/plotly.py,
  render/svg.py, render/web.py, style/theme.py, testing/kit.py; CI does not run flake8.
