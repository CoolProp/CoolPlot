# Report: 0.4, one chart model

Branch chp/0.4 (from chp/release-0.3). Done criteria of docs/v1_plan.md:

| Criterion | State |
|---|---|
| compose/psychro.py, spec/psychro.py, second unit table gone | gone |
| existing tests pass unchanged or with one-line changes | test_psychro: ids psy/ -> iso/, air/ -> cycle/, PsychroSpec -> DiagramSpec, default_values helper rewritten over plan(); test_architecture: chart layer added; everything else unchanged |
| psychrometric chart and ph diagram drawn by the same code path | Chart.update_scene -> Engine -> compose for both (tests/test_contracts.py::test_both_chart_kinds_share_the_pipeline) |
| conformance kit green on all backends | full suite green on CoolProp 8 (341 tests, 4.5 min), thermo subsets green on 7.2 and 6.8 (102 each) |
| scene of every example round-trips through JSON byte-identically | tests/test_contracts.py (both chart kinds, conformance scene) |

Pictures: scratchpad/psy_before.png and psy_after.png (the psychrometric
example before and after; same lines, 250 instead of 100 points per line,
labels placed by the shared layout).

Timings on this machine: default psychrometric chart 0.9 s (was 0.4 s at
100 points; points=100 restores it), ph chart unchanged.

Open questions are in scratchpad/open_items.md ("Found on the way").

Adversarial review: 3 blocking findings (StatePoint equality depended on
key order, swapped humid-air axes accepted, states of the other chart
kind accepted), all fixed in bc68d38 with tests; 8 trade-offs and 5
minor issues fixed or documented (see the commit message and the
CHANGELOG "Behaviour changes" bullet).
