# Report 0.7: numerics (branch chp/0.7)

Scope (docs/v1_plan.md, 0.7): adaptive stepping of every isoline, the phase boundary
handled once per fluid with two-phase branches in quality, the sweep clipped to what
the axes show, cheaper inputs for blends, quality lines of zeotropes to the critical
point, the cycle error taxonomy, v / dT / gauge units, the layout vectorised, the
pre-8 paths removed (D2).

## What changed

* `thermo/stepping.py` (new): `trace(evaluate, metric, points, ...)` walks a parameter
  with steps chosen from the line's shape in normalised plot coordinates (max segment
  `2.5/points`, max turn 5 deg, the next step aimed at 80 % of both), bisects the
  axes' edges, scans outside in doubling steps, budget 8*points+100 evaluations.
* `thermo/isolines.py` rewritten around it: `_LineSolver` (tracer with flash fallback,
  or flash), `_Line.through_the_dome` (isotherms/isobars: single-phase parts up to the
  bubble/dew states, the dome stepped in quality), `_Line.across_the_dome` (crossings
  solved on the saturation curve or interpolated on the envelope), mixture quality
  lines stepped to the envelope top. `Curve` gained `n_evaluated`, `n_outside`.
* `thermo/tracer.py`: secant quality solve from the previous quality (2-3 saturation
  calls instead of 6), densities solved on v, roots near the critical point judged by
  the envelope's densities (`TOP_DENSITY_MARGIN` 1.5, `ABOVE_TOP_RTOL` 2e-4), a
  two-phase point as the Newton seed of last resort; `TRACER_AVAILABLE` gone.
* `PhaseEnvelope.closed` and `.top(key)`; `Fluid.get("v")`, states given by v,
  `Fluid.diagnose` (T/p outside the EOS, Q above the critical point, unsupported
  mixture pair) feeding `PropertyError.reason/limits`.
* `core/units.py`: `Unit.difference_label`, `Unit.difference`, `UnitSystem.difference`
  and `describe_difference`, `BAR_GAUGE`, `PSI_GAUGE`; `compose.builder.axis_scales`
  draws an offset unit's axis linear.
* `compose/layout.py`: `visible_pieces` and `Piece.project` in numpy.
* Engine: lines with < 2 points, nothing failed and points outside the axes are
  skipped silently (`Curve.reason` explains); the axis ranges are passed to the
  isoline code so the stepping is the same in every unit system.
* `tests/numerics/test_sweep.py` (slow, `--run-slow`): every line family of every
  diagram type for R290, CO2, R410A, R32/R125.
* CoolProp >= 8.0 in pyproject and CI; docs (user guide, architecture section 11,
  contracts, changelog 0.7.0); version 0.7.0.dev0.

## Measurements (this machine)

| | before (0.6) | after |
|---|---|---|
| R410A default ph chart | 22.7 s | 5.1 s (criterion < 10 s) |
| R407C default ph chart | 27.3 s | 11.3 s |
| R290 default ph chart | 0.3 s | 0.2 s |
| R407C Ts chart with labels (png) | 38.5 s | 12.4 s |
| R32/R125 ph chart with labels | 19.2 s | 5.8 s |
| R407C 5 bar isobar in Ts, points inside the dome | 5 | 44 (criterion >= 40) |
| points per default ph chart | 13830 | 7241 |
| isotherm 0.5 K above T_crit of R410A | 7.5 s (250 cold flashes) | 0.1 s |
| label layout after a view change, 54 lines | 0.08 s | 0.03 s |

Calls outside the axes: at most 12 per line on the default charts, under 10 % of the
evaluations over a sweep (slow tests). Round trip: pure-fluid points agree with
CoolProp's inverse flash to 1e-8 of the property range (the inverse flash's own
noise is ~1e-9); traced points of blends agree with an independent p,T or p,Q
flash to 1e-6.

Pictures: scratchpad/p07/pics/*_after.png against scratchpad/p07/pics_before/*_before.png
(R410A ph, R407C Ts, R290 Trho, R32/R125 ph). The charts look the same; the glide of
blend isobars through the dome is now drawn as a curve.

## Tests

Default suite 337 passed, 20 skipped (browser, kaleido, slow) in 4 min 20 s.
Opt-in browser and Kaleido modules (test_web, test_plotly, test_pdf, test_web_server): 71 passed in
1 min 57 s. Slow sweeps (tests/numerics, every family of every diagram type for R290, CO2,
R410A and R32/R125): 6 passed in 1 min 40 s. Full suite after the function splits: 337 passed.

## Review

The adversarial review found two blocking items, both fixed in the "Review fixes" commit:
the stepper's scan outside the axes doubled its step without a cap (a short re-entry could
be skipped and the line dropped silently; now capped at 1/32 of the range), and a line cut
short by the evaluation budget left no trace (now `Curve.reason`, with an engine warning).
Also taken from the review: the dome part of an isotherm or isobar is clipped to the T-p
box's range of the stepped quantity (an isobar in an h-s chart reached below T_min), a root
above the top of a closed envelope is accepted unchecked only when the envelope's densities
meet there to 5 percent, a density target that is not positive, braces in a reason, a model
cycle keeping its completed states, and the sweep tests now check every sample of the line
itself (by an explicit (T, rho) or saturation evaluation, with tolerances by the source of
the point). Trade-offs kept are listed in open_items.md. The CO2 p-h chart with the default
limits has no liquid region on its h axis (pre-existing, the corner at T_min, p_max lies
below the melting line); the sweep uses ACHP limits for CO2.

## Decisions taken

* "auto" still flashes pure fluids and traces mixtures: pure-fluid flashes are fast
  and exact, and the tracer's gains are in the mixture solves.
* Lines are clipped to the area the axes show (the bounding box of the T-p box in
  the diagram's quantities), not to the T-p box itself: the old code drew the parts
  of isochores and isenthalps beyond p_max at the top left of a T-s chart, and
  clipping to the box left that corner empty.
* The dome branch of a pure fluid is stepped like a blend's (the tie line gets
  points along it); exact, and the Trho / prho tie lines are curves anyway.
