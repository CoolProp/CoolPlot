# Report: 0.6, scope and shape

Branch chp/0.6 (from chp/0.5).

| Criterion (docs/v1_plan.md) | State |
|---|---|
| `import coolplot.render.plotly` loads no PDF parser | yes; tests/test_architecture.py::test_importing_a_backend_loads_no_test_tooling |
| suite under five minutes on this machine | default suite 3 min 55 s (338 passed, 14 opt-in skipped); with --run-browser --run-kaleido 4 min 17 s (352 passed); CoolProp 7.2 and 6.8 subsets 118 passed each |
| radon cc -n C prints nothing | holds for src/coolplot outside coolplot/testing (test tooling) and the numerics that 0.7 rewrites (thermo/isolines.py, tracer.py, humid_air.py); those two groups are noted in open_items.md |

Also done: coolplot.testing package; WebServer to examples/web_app; BackgroundEngine,
Chart.draw and the renderers' read-back split into named steps; the private matplotlib
attribute off the drawing path (text angles kept by the renderer) and the read-back ones
fenced by a test; browser/kaleido markers; test_review_fixes.py folded into the modules;
the blend example cut down (fewer lines, 6 path steps: the cycle paths of a blend cost
about 0.1 s per flash, a 0.7 item).

Review: 4 behaviour differences found in the refactor (error wording and order of checks,
critical-point fallback, pressure steps computed for every path kind), all reverted to the old
behaviour in the follow-up commit; the web example now uses a public lock property and loads
its server by file. Full suite after the fixes: 352 passed (4 min 20 s with browser and
kaleido); 118 passed each on CoolProp 7.2 and 6.8.
