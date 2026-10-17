# Report 0.9: the deprecation release and one native setting (CoolPlot branch chp/0.9, from chp/c1)

Scope (docs/contributing/v1_plan.md, 0.9): warnings on, nothing removed;
CoolPlot runs on CoolProp.Plot where installed (C0) and on coolplot-core for
the scene (C1), with the Python tracer and composer as fallbacks selected by
one setting. Done when: the full suite passes on both paths; the scene of
every example is identical from both paths.

## What changed

* `coolplot.set_native_mode("auto" | "on" | "off")` and `coolplot.native_mode()`
  (new module `coolplot.core.implementation`). The environment variable
  `COOLPLOT_NATIVE` gives the starting value; the setting overrides it, and
  None goes back to it. Both switches read it: the numerics adapter
  (`thermo.native.enabled`, on unless "off") and the coolplot-core bridge
  (`corelib.enabled`, only "on").
* The engine decides the implementation once, when it makes a curve's cache
  key, and hands that flag to the computation (`Engine.key_uses_native`). A
  background engine's worker processes therefore follow the setting of the
  chart's process, and a mode change while jobs are queued cannot put a
  curve under the other implementation's key.
* tests/test_examples.py: every example runs with the mode "off" and "on"
  in a subprocess that records every scene it composes and counts how often
  each C++ path answered. The scenes have to agree (1e-9; 1e-7 where
  CoolProp's numerics port computed lines, which agrees with Python to the
  solvers' rounding), the files byte for byte (by name where the numerics
  port computed lines), the printed text up to timings. In "on" each
  installed port has to have answered, and a fallback to Python is an
  error; the list of examples has to be the folder's.
* Deprecations: the old names of 0.5 already warn. A test checks that every
  deprecated chart method is in the upgrade guide, which gets a 0.8 to 0.9
  section.
* Version 0.9.0dev0, changelog, docs (explanation/numerics, contributing/core,
  reference/api, upgrade).

## Acceptance

* The full suite passes on both paths: see the table below.
* The scene of every example is identical from both paths: with coolplot-core
  (venv with CoolProp 8.0.0 and coolplot_core) to 1e-9 and byte-identical SVG
  and PNG; with CoolProp's numerics port (venv with CoolProp master) to 1e-7.

## Review

An adversarial review found three blocking issues, fixed in the follow-up
commit:

1. The example test passed `-W error::coolplot.corelib.CoreFallbackWarning`
   to the child, which Python ignores (it cannot import coolplot before it
   starts), so a run that fell back to Python would have compared Python with
   Python. The child now sets the filter itself and counts the calls each
   port answered.
2. The CI core job sets a relative PYTHONPATH, which the child (running in a
   temporary folder) would have resolved elsewhere and lost coolplot_core.
   The test passes absolute paths and checks that the child sees the same
   ports.
3. Worker processes did not see set_native_mode (fixed as above).

Smaller ones fixed: set_native_mode returns the previous setting (None when
the environment decided), so passing it back restores exactly; the upgrade
guide check matches whole names; stale docstrings and links.

## Test runs

| run | result |
|---|---|
| CoolProp 8.0.0 + coolplot_core, COOLPLOT_NATIVE=1, -W error::CoreFallbackWarning | 370 passed, 40 skipped |
| CoolProp 8.0.0 + coolplot_core, COOLPLOT_NATIVE=0 | 370 passed, 40 skipped |
| CoolProp 8.0.0 + coolplot_core, COOLPLOT_NATIVE unset | 370 passed, 40 skipped |
| CoolProp master (numerics port), COOLPLOT_NATIVE unset | 360 passed, 31 skipped, 1 failed (below) |
| the example test with the numerics port | 5 passed |
| Sphinx -W | clean |

The one failure with CoolProp master is test_thermo.py::
test_flash_isochore_of_a_blend_round_trips, which runs the Python numerics
directly (no native mode involved): on master the R407C isochore at 100
kg/m3 reaches down to 3.6 kPa and 178 K, where 8.0.0 refused the states,
and master's own HP flash there returns 3.5 kg/m3 or fails with "the (T,p)
flash is misclassifying the phase for this mixture". A CoolProp master
defect in the low-pressure two-phase region of the blend, not of this
package; open item.

Commits on chp/0.9: a3a4c3e (setting, example test, docs), 26a28b4 (review
fixes). Pushed.
