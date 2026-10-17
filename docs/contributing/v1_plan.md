# CoolPlot 1.0: work plan

Companion to [v1_review.md](v1_review.md). The review says what is wrong
and why; this plan says what gets done, in which order, what "done" means
for each package, and which decisions it rests on. Each work package is
one branch (`chp/<version>`), one or more commits per step, an adversarial
review of the diff before it counts as done, and a short report with
pictures at the end.

## 1. Decisions

Decisions that gate the work, each with the default the plan assumes when
nobody decides otherwise. A decision made later than its package starts
costs a rewrite of that package only.

| # | Decision | Default assumed | Gates |
|---|---|---|---|
| D1 | Direction: numerics into `CoolProp::Plot`, presentation as a CoolProp-free C++ library, thin native layers (review, 6.2) | yes | the shape of the curve record and scene schema in 0.4; the C++ packages |
| D2 | Minimum CoolProp for 1.0 | 8.0 (6.8 and 7.2 supported through 0.x only) | removes the pre-8 flash paths in 0.7; the tracer becomes the only path |
| D3 | Name of the bar / deg C / kJ unit set that replaces `"EUR"`; IP units in 1.0 | `"engineering"`, with `"EUR"` kept as an alias with a warning; IP units yes | 0.5 |
| D4 | One way to draw a path of states: `add_cycle` with `units=`; `set_process` goes | yes | 0.5 |
| D5 | `WebServer` and the inline JavaScript | move to `examples/web_app/`; `WebRenderer` and its tests stay | 0.6 |
| D6 | Deprecation policy | one minor release with `DeprecationWarning`, removal at 1.0, and a stable API from 1.0 to 2.0 | 0.9 |
| D7 | Where `coolplot-core` (the C++ presentation library) lives | its own repository, built into CoolProp's wrapper matrix as an optional component | C1 |
| D8 | Fate of `CoolProp.Plots` in CoolProp 8.x | retire at CoolProp 9 with a pointer to CoolPlot | upstream, not gating |
| D9 | Psychrometric chart orientation | ASHRAE (T over W) stays the default, Mollier (h over W) as a chart variant of the same model | 0.4 |
| D10 | Minimum Python | 3.10 (as today) | nothing |

## 2. Work packages

Acceptance criteria are checkable by the test suite or by a script in the
repository; "green" means the full suite on CoolProp 8 and the thermo
subsets on 6.8 and 7.2 until D2 removes them.

### 0.3.1 (done, branch `chp/0.3.1`)

Wrong physics from the numerics review: inconsistent mixture states
refused, mixture lower limits, blends on CoolProp 6 and 7 skipped with a
reason, incompressibles, cache fingerprint, wet-bulb search.

### 0.4: one chart model, the contracts written down

Scope:
1. A quantity table that covers T, p, h, s, rho, u, Q, W, RH, Twb, Tdp, v
   with one unit model (per-quantity units, presets), replacing the two
   tables.
2. A property-provider interface in `thermo`: `AbstractState` fluids and
   humid air implement the same small set of calls (state from two
   properties, line of a family, bounds, capabilities such as
   `has_critical_point`).
3. A line-family registry per chart kind: how a family is sampled, where it
   ends (saturation, W = 0, the chart edge), its default values.
4. One facade `Chart`, with `PropertyDiagram` and `PsychrometricChart` as
   constructors over it; one `Engine`; one compose module; processes and
   cycles as one concept; `Interaction` without id-prefix dispatch.
5. The curve record and the scene JSON schema written down in
   `docs/contracts.md` and round-tripped in tests (`Scene.to_dict` /
   `from_dict`), free of Python types.
Done when: `compose/psychro.py`, `spec/psychro.py` and the second unit
table are gone; every existing test passes unchanged or with a one-line
change; a psychrometric chart and a ph diagram are drawn by the same code
path; the conformance kit is green on all backends; the scene of every
example round-trips through JSON byte-identically.

### 0.5: vocabulary, units, errors

Scope: the frozen verbs (`set_lines`, `add_cycle`, `remove_cycle`,
`set_view`, `save`), display units with `units=` on every user-facing
call, the project's quantity naming on model inputs and results,
`"engineering"` and IP units, `PropertyError` with the inputs in the
user's units, constructor validation of fluids, unit-aware printing of
`StatePoint` and `AirState`, the `with_` overloads tidied, the
`object.__setattr__` idiom replaced by explicit constructors.
Done when: the old names warn and still work; `grep` finds no `EUR` in
examples and docs except the alias note; the ten error messages the docs
review listed read in the user's units; `tests/test_api_vocabulary.py`
checks the public names against a frozen list.

### 0.6: scope and shape

Scope: `coolplot.testing` (conformance kit, PDF check, PDF reader) as a
package users do not import; `WebServer` to `examples/web_app/`;
`BackgroundEngine`, `PropertyDiagram.draw` and `compute_isoline` as small
state machines with one test per branch; the private matplotlib
attribute on the drawing path removed; browser and kaleido tests as
opt-in markers; `test_review_fixes.py` folded into the modules; the
blend example cut down.
Done when: `import coolplot.render.plotly` loads no PDF parser; the suite
runs under five minutes on this machine; cyclomatic complexity of every
function in `src/coolplot` is below 15 (`radon cc -n C` prints nothing).

### 0.7: numerics

Scope (review, 7.4): continuation tracing parametrised by arc length with
curvature-controlled steps for every line; the phase boundary handled once
per fluid, two-phase branches traced in quality; the sweep clipped to the
domain before tracing; cheaper inputs for blends; capabilities for
tabular backends; quality lines of zeotropes to the critical point; the
cycle error taxonomy; specific volume, temperature differences and gauge
pressure as units; the layout vectorised. With D2: the pre-8 paths
removed.
Done when: every pure-fluid line round-trips to 1e-9 and every blend line
to 1e-6 on the review's sweep (`numrev/robust.py` and `verify_ph.py` moved
into `tests/numerics/` as slow tests); no line wastes more than 10 % of
its calls outside the domain; the default R410A ph chart draws in under
10 s on this machine; the 5 bar R407C isobar in Ts has at least 40 points
inside the dome.

### 0.8: documentation

Scope (review, 5): Sphinx with MyST, numpydoc with a linter, sphinx-gallery
from `examples/`, Read the Docs, the Diataxis structure, the generated
reference, the gallery, the changelog in Keep-a-Changelog form with the
upgrade guide, a picture in the README.
Done when: `sphinx-build -W` passes in CI; every public name has a
reference page; every example renders in the gallery and is run by the
docs build; the docs review's 24 findings are closed one by one in a
checklist committed with the branch.

### 0.9: deprecation period and the C++ core

Scope: warnings on, nothing removed; CoolPlot runs on `CoolProp.Plot` where
the installed CoolProp has it (C0 below) and on `coolplot-core` for the
scene (C1), with the Python tracer and composer as fallbacks selected by
one setting.
Done when: the full suite passes on both paths; the scene of every example
is identical from both paths.

### 1.0

Scope: removals, the stable API, the release. The Python tracer and
composer are removed when the C++ passes the full suite, otherwise they
stay for 1.x behind the same setting.

## 3. The C++ packages

Independent of the Python releases after 0.4 fixed the contracts.

### C0: `CoolProp::Plot` upstream (numerics)

Steps: (1) the three upstream items (the T,rho defect, the GIL release,
the fraction bug); (2) a pull request that replaces the body of
`src/CoolPropPlot.cpp` with the tracer, dome, quality lines, cycle state
resolution and humid-air lines, keeping the class names; (3) exposure in
`CoolProp.i`, nanobind and `CoolPropLib.h`; (4) CoolPlot uses it when
present. Acceptance: the Python numerics tests (0.7) pass against the C++
through nanobind.

### C1: `coolplot-core` (presentation)

Steps: (1) repository with CMake and Catch2; (2) spec JSON in, curve
records in, scene JSON out; (3) the SVG writer; (4) the PDF writer with
TrueType subsetting; (5) the C ABI and a nanobind module; (6) built in
CoolProp's wrapper matrix (D7); (7) a JavaScript renderer of scene JSON
as the first native layer (makes the browser backend server-free).
Acceptance: the conformance kit green with the C++ scene feeding the
existing matplotlib and plotly renderers; the SVG of every example
identical to the Python SVG writer's within numeric formatting.

## 4. Working unattended

What can proceed without anyone present, taking the defaults of section
1: everything in 0.4 to 0.8, in order, each on its own branch with its
review and report, and C0 step 2 as a branch on the CoolProp repository
(not a pull request). What needs a person: merging and tagging, releases
to PyPI, filing anything upstream, the decisions above if a default is
wrong, and a look at the pictures in each report.

Checkpoints: after each package a report with the charts it changed
(before and after), the test and timing numbers, and the open questions.
Work stops at a checkpoint when a decision is needed that the defaults
do not cover, or when the full suite cannot be made green on the package's
own scope.
