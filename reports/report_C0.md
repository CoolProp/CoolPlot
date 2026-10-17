# Report C0: CoolProp::Plot numerics upstream (coolprop/coolprop branch chp/plot-numerics, CoolPlot branch chp/c0)

Scope (docs/contributing/v1_plan.md, C0): replace the body of CoolProp's
src/CoolPropPlot.cpp with the 0.7 numerics keeping the class names, fix the blend
fractions, release the GIL in the nanobind update, expose the result through the
wrappers, and let CoolPlot use it when it is there. Acceptance: the Python
numerics tests pass against the C++ through nanobind. No PR, no issues (the
upstream texts are in scratchpad/upstream/).

## What changed in CoolProp (chp/plot-numerics, from master 022b63e)

* `include/CoolProp/plotting/CoolPropPlot.h`, `src/CoolPropPlot.cpp`: the fixed
  grid is replaced by a port of CoolPlot's `thermo/fluid.py`, `tracer.py`,
  `stepping.py` and `isolines.py` (2000 lines, names and order of steps kept so
  that the two can be read side by side): a `Detail::Fluid` with the guide state,
  the phase envelope, the critical point and the component-wise temperature
  limits; `IsoLineTracer` (Newton in T and rho with the phase imposed, the
  secant and regula-falsi quality solves, the dome checks); the `Walk` stepper
  (steps from the shape on the page, the scan outside the axes, the evaluation
  budget); `LineSolver`, `Line` (through and across the dome, crossings from the
  saturation solver or the phase envelope, merged and refined); the quality
  lines (pure grid plus the critical point; envelope branches for a mixture).
  The public API keeps `PropertyPlot`, `Isoline`, `Isolines`,
  `generate_values_in_range`, `TPLimits`, `Scale`, `Range` and adds
  `CalcSettings` (points, solver, critical margin, saturation spacing), the
  diagnostics of an `Isoline` (`n_failed`, `n_fallback`, `n_inserted`,
  `n_evaluated`, `n_outside`, `method`, `reason`, `n_valid()`, `n_gaps()`),
  `supported_isoline_keys()`, `sweep_key()`, `tp_box()`, `is_mixture()` and a
  constructor with absolute T and p limits. The old `include/CoolPropPlot.h`
  stays as the deprecated forwarding shim.
* Blend fractions: `Detail::Fluid` sets the mole fractions (mass fractions for
  INCOMP) of a fluid string, resolves a predefined blend such as `R407C.mix` to
  its components, and `process_fluid_state` goes through it.
* nanobind: `AbstractState.update` and `PropertyPlot.calc_isolines` release the
  GIL; the port is bound as the submodule `CoolProp.CoolProp.Plot` (enums,
  `Range`, `CalcSettings`, `Isoline`, `Axis`, `PropertyPlot`,
  `generate_values_in_range`). The committed stub `CoolProp.pyi` gains the
  submodule line stubgen writes; `Plot.pyi` is a new committed copy shipped by
  the wrapper's CMake; `test_stub.py` checks it against the runtime.
* SWIG: `src/CoolProp.i` includes the header (parse not verified here, swig is
  not installed).
* Catch2: 12 tests tagged `[Plot]` mirror CoolPlot's `tests/test_numerics.py`
  (isobar through the dome, isotherm kinks, isenthalp on the bubble line, tracer
  against flash on a blend, auto solver, mixture dome from the envelope, blend
  lines meeting the dome near the critical point, pure quality lines ending at
  the critical point, gaps, `value_at`, axes and keys, absolute limits and an
  incompressible). The old tests that compared a fixed grid with the legacy
  Python output are gone with the grid, as is the script that generated them
  (`dev/scripts/generate_Plot_test_data.py`).
* `dev/agent-notes.md`: a section on the port.

## What changed in CoolPlot (chp/c0, from chp/0.8)

* `coolplot/thermo/native.py`: when the installed CoolProp carries the port and
  `COOLPLOT_NATIVE` is not 0, `provider.compute_curve` sends every fluid line to
  `CoolProp.CoolProp.Plot.PropertyPlot` built with the chart's T-p box; the
  `Isoline` comes back as a `Curve` with the same diagnostics. Models the fluid
  string cannot carry (binary interaction parameters, mass fractions on a
  Helmholtz backend) and axes the port does not know go to the Python numerics,
  which stay the reference.
* `tests/test_native.py`: 14 tests, skipped without the port (CI runs CoolProp
  8.0.0): the numerics checks through the port, the fluid strings, the switch,
  the provider's choice, and a comparison of the port's lines with the Python
  lines (same insertions and method, same number of points within 5 %, every
  point of the port within 3 % of the axes of the Python line).
* `render/mpl.py`: a label next to the bottom of a log axis that starts close to
  zero got a NaN screen angle from matplotlib's `transform_rotates_text` (it
  moves the anchor a fixed 1e-5 in data units, which is below zero for an
  isotherm label at 2e-8 bar on R290's default p axis from 1.7e-9 bar) and
  saving the R290 p-h chart with labels raised "cannot convert float NaN to
  integer". Pre-existing, found by the C0 benchmark; such a label now gets its
  screen angle computed once from the data direction. Regression test in
  `tests/test_scene_render.py`.
* `tests/test_numerics.py`: the tracer-against-flash check compares only the
  pressures where CoolProp's H-p flash of the blend converges (CoolProp master
  refuses some two-phase states 8.0.0 solves; at least 5 of 7).
* Documentation: a paragraph in `explanation/numerics.md`; the changelog.

## Numbers

Default charts with labels, CoolProp master wheel (8.1.0.dev0 built from
chp/plot-numerics), the port against the Python numerics in the same process;
every chart has exactly the same number of points both ways (the port steps the
same way, point for point):

| chart | port | Python | points |
|---|---|---|---|
| R410A p-h | 3.6 s | 4.0 s | 7242 |
| R410A T-s | 3.3 s | 3.5 s | 7867 |
| R290 p-h | 0.1 s | 0.2 s | 7987 |
| R290 T-s | 0.1 s | 0.2 s | 7336 |
| R407C p-h | 9.4 s | 9.2 s | 7162 |
| R407C T-s | 8.1 s | 9.2 s | 7988 |
| R32/R125 (70/30) p-h | 3.5 s | 3.9 s | 7211 |
| R32/R125 (70/30) T-s | 3.3 s | 3.3 s | 7919 |

The time of a mixture chart is CoolProp's solvers (the tracer's Newton steps, the
flashes it hands back, the phase envelope), so the port saves the Python
overhead only. The first run of the benchmark showed the blend three times
slower through the port: the adapter built a PropertyPlot, with the phase
envelope, for every line. The plots are now kept per fluid, axes and T-p box
(`native._plot`), and the blend chart is 3.5 s.

Catch2 `[Plot]`: 12 cases, 893 assertions, 3.7 s. The full `~[slow]` suite of
CoolProp: 657 cases, 40 skipped, green. CoolPlot on the master wheel: 337 tests
with `test_native.py` (14) passing; on the 8.0.0 wheel the native tests skip.

Pictures: scratchpad/p07/c0/pics/<fluid>_<chart>_{port,python}.png (R410A, R290,
R407C, R32/R125; p-h and T-s).

## Verification

* CoolProp preflight (`dev/ci/preflight.sh`): clang-format (18.1.8 pin, 3 files),
  the Catch2 build, the `~[slow]` tests and semgrep pass. clang-tidy needs
  version 19 (18 installed); cppcheck is not installed; the shared-library
  configure of the json-symbols and installed-header gates downloads valijson,
  which the proxy refuses, so those two were run again with the shared build
  configured from the local sources (see preflight2.txt).
* The nanobind wheel built with `pip wheel .` (scikit-build-core, nanobind
  2.12.0, CPM cache of the catch build); the stub test of the wrapper passes with
  the regenerated `CoolProp.pyi` and the committed `Plot.pyi`; mypy resolves the
  types of `CoolProp.CoolProp.Plot` through the stubs.
* CoolPlot: flake8 on the touched files, `sphinx-build -W` clean (the new module
  has its reference page), the suite on both wheels.

## Review (CoolPlot, chp/c0)

Adversarial review of the diff; blocking findings fixed in the follow-up commit:

1. Quality lines of a tabular backend (BICUBIC, TTSE) went to the port with the
   tabular backend, losing the swap to the equation of state behind the tables
   that the Python path makes (`_base_backend_fluid`). `native.port_fluid_string`
   makes the same swap for Q lines; tested without the port.
2. The provider glue had no test that runs in CI (the whole module skipped
   without the port). The tests of the provider's choice, the switch, the fluid
   strings and the tabular rule now run everywhere, with a stand-in for the port
   (sentinel curve, spy on the calls, fallback when the port declines).
3. The agreement test measured nearest-point distances with a 3 % tolerance. The
   port reproduces the Python lines bit for bit (max relative difference 1e-15
   over 11 lines of R290 and the blend, same length, same gaps), so the test now
   demands equality within 1e-9, the same gaps and the same diagnostics.

Non-blocking findings taken: a mixture given as an AbstractState or a predefined
blend snapshots CoolProp's own binary interaction parameters, which kept every
such model out of the port; parameters equal to those of a fresh state of the
same components now count as unchanged. AttributeError and TypeError from a port
of another vintage fall back to Python (ValueError still propagates). The
engine's cache key carries `native.enabled()`. The ranges argument is explained
in a comment. The background engine's docstring says what the released GIL
changes. The "several times faster" claim is replaced by the measured numbers.

Found by the engine suite on the master wheel, not by the review: the adapter's
plot cache served a PropertyPlot made before `set_reference_state`, whose states
keep the old reference (the Python path rebuilds its Fluid when the fingerprint
changes). The cache key carries the fluid's fingerprint now;
`test_a_changed_reference_state_never_serves_old_curves` passes with the port.

Not changed: `test_thermo.py::test_flash_isochore_of_a_blend_round_trips` fails
on the master wheel because CoolProp master's H-p flash of R407C flashes a point
of the isochore back to another density (upstream text 4); it stays as the guard
it is and passes on 8.0.0, which CI pins. The label fix in `render/mpl.py` was
made after the review's diff was taken and is reviewed by hand only: a fallback
that triggers only when matplotlib's own angle is not finite, with the R290
chart as its test.

## Review (CoolProp, chp/plot-numerics)

Adversarial review of the diff (the reviewer also ran SWIG 4.5.1 for Python, Java
and C# on the new interface, compiled with -Wall -Wextra -Wshadow -Wpedantic,
regenerated the stub as the drift gate does, and probed the built module).
Blocking findings fixed in the follow-up commit:

1. `value_at` returned NaN for every incompressible fluid: `specify_phase` was
   called unconditionally and incompressible backends throw on it. The phase is
   imposed only when one is asked for; the incompressible test now checks a
   readout.
2. `Props1SI` reports a failure as an infinite value, not an exception, so a
   component HEOS cannot name made the outer saturation bound infinite and the
   "beyond any possible dome" checks never fired. The components' critical
   points are used only when every lookup succeeds, as the Python reference does.

Trade-off decided by default: the GIL release in `AbstractState.update` is kept
for every backend except REFPROP (not reentrant; its calls stay serialised), and
the binding's docstring states the one-state-per-thread rule; the release on
`calc_isolines` stays (its states are private to the plot).

Non-blocking findings taken: axes CoolProp has no flash for are refused at
construction (they silently gave NaN); `generate_values_in_range` with a count
of 0 or 1 returns the lower value instead of NaN; `points` is clamped to 2..1e6;
the tracer takes the fluid's highest stable critical temperature from the Fluid,
computed once per fluid instead of once per line (seconds to minutes for a blend
with a wide glide); the empty-region message carries the numbers.

Left as noted (open items): the SWIG warnings (nested Axis struct ignored by every
SWIG wrapper, `TPLimits::None` renamed by SWIG, the two `generate_values_in_range`
overloads shadow each other in SWIG, the vectors wrap opaquely); the anonymous
struct in Axis (pre-existing, -Wpedantic); the wall-clock check in the tracer test
(margin 40x); `value_at` not going through the guide-state retry; quality lines
of tabular backends on the port use the tables (CoolPlot's adapter swaps the
backend before calling).
