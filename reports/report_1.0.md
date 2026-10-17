# Report 1.0: release candidate 1.0.0rc1 (CoolPlot branch chp/1.0, from chp/0.9)

Scope (docs/contributing/v1_plan.md, 1.0): removals, the stable API, the
release. "The Python tracer and composer are removed when the C++ passes the
full suite, otherwise they stay for 1.x behind the same setting."

## What changed

* Removed (deprecated from 0.5 to 0.9, D6): the chart methods set_isolines,
  set_default_isolines, remove_isolines, isoline_sets, set_isoline_style,
  savefig, set_process, remove_process and the psychrometric add_process,
  move_process_state, process_states; the unit system name "EUR" in calls;
  the rankine keywords eta_turbine and eta_pump.
* Each removed name fails with a message that names its replacement: a
  removed chart method raises an AttributeError ("PropertyDiagram.set_process()
  was removed in CoolPlot 1.0; use add_cycle ..."), per chart kind; "EUR"
  a ValueError naming "engineering"; the old keywords a TypeError naming
  theirs. An AttributeError raised inside a property still surfaces as itself.
* Kept: the constant coolplot.EUR never warned before 1.0, so it stays through
  1.x with a DeprecationWarning and goes in 2.0. Specs saved with processes
  (set_process) still read and draw; a spec saved by 0.4 with "units": "EUR"
  reads as engineering, in Python and in coolplot-core (which now refuses the
  name in calls, like Python).
* The Python numerics and composer stay behind set_native_mode: CoolProp's
  numerics port is in no released CoolProp, and coolplot-core is slower from
  Python than the Python composer, so neither C++ path can be the default.
* Docs: the upgrade guide states what is stable from 1.0 to 2.0 and has a
  0.9 to 1.0 section; changelog 1.0.0rc1; how-to pages and contracts updated.
* Version 1.0.0rc1; classifiers "Development Status :: 4 - Beta" (to become
  "5 - Production/Stable" with the final 1.0.0) and "Intended Audience ::
  Science/Research".

## Review

The adversarial review found three blocking issues, fixed in the follow-up
commit: coolplot.EUR was removed without ever having warned (now deprecated
until 2.0); coolplot-core still accepted "EUR" while Python refused it (now
refused in both, and both read old records); a spec saved by 0.4 with
default units would no longer load (now read as engineering). Also fixed:
hints for names that never existed on a chart kind, property errors masked
by the hint mechanism, tests that checked the hints against the same table
the code uses or passed on the old 0.5 section of the guide, the rankine
hint, the classifier for a release candidate. Flagged and left: the
deprecation helpers' signature changed (they are internal, outside the
stability promise); get_unit_system keeps a stacklevel parameter that does
nothing; the stability promise is wider than what the tests freeze (package
names and chart verbs are frozen, keyword names and submodules are not).

## Test runs

| run | result |
|---|---|
| CoolProp 8.0.0 + coolplot_core, COOLPLOT_NATIVE=1, -W error::CoreFallbackWarning | 374 passed, 40 skipped |
| CoolProp 8.0.0 + coolplot_core, COOLPLOT_NATIVE=0 | 374 passed, 40 skipped |
| CoolProp 8.0.0 + coolplot_core, COOLPLOT_NATIVE unset | 374 passed, 40 skipped |
| Catch2 (coolplot-core), COOLPLOT_REQUIRE_LOCALE=1 | 33 cases, 437 assertions passed |
| Sphinx -W | clean |
| CoolProp master (numerics port), COOLPLOT_NATIVE unset | 364 passed, 31 skipped, 1 failed: the known CoolProp master HP-flash defect for R407C (report 0.9) |

Commits on chp/1.0: 293ea17 (removals, stability), 23585f7 (review fixes), then a short second review of
23585f7 (no blocking findings) and a commit for its doc and test points. Pushed.

## What a person has to do

* Merge the branches in order (chp/0.4 ... chp/0.8, chp/c0, chp/c1, chp/0.9,
  chp/1.0), tag v1.0.0rc1, publish the release candidate to PyPI, and after
  feedback set "Development Status :: 5 - Production/Stable", version 1.0.0.
* The CoolProp side (branch chp/plot-numerics on coolprop/coolprop) needs a
  pull request by a maintainer; until a CoolProp release carries
  CoolProp::Plot, CoolPlot computes lines in Python.

Second review, flagged and left: the property re-run in Chart.__getattr__ runs a failing getter
twice (a getter with side effects could hide its error, and chained failing properties double
the work per level); cached_property is not covered; rankine's signature shows **removed;
" EUR" with spaces reads in Python but not in C++.
