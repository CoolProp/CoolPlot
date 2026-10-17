# CoolPlot 1.0 work: session notes

Notes from the session that carried out docs/contributing/v1_plan.md
(packages 0.4 to 1.0 RC, C0 and C1). This branch holds notes only, no
code; the code is on the package branches.

## Branches

| Package | Repository | Branch |
|---|---|---|
| 0.4 one chart model | CoolProp/CoolPlot | chp/0.4 |
| 0.5 vocabulary, units, errors | CoolProp/CoolPlot | chp/0.5 |
| 0.6 scope and shape | CoolProp/CoolPlot | chp/0.6 |
| 0.7 numerics | CoolProp/CoolPlot | chp/0.7 |
| 0.8 documentation | CoolProp/CoolPlot | chp/0.8 |
| C0 CoolProp::Plot numerics (port) | CoolProp/CoolProp | chp/plot-numerics |
| C0 CoolPlot adapter | CoolProp/CoolPlot | chp/c0 |
| C1 coolplot-core (C++ under cpp/) | CoolProp/CoolPlot | chp/c1 |
| 0.9 deprecation release, one native setting | CoolProp/CoolPlot | chp/0.9 |
| 1.0.0rc1 removals, stable API | CoolProp/CoolPlot | chp/1.0 |

Each branch starts from the one before it, so merging them in this order
gives the whole history. No pull requests were opened.

## Contents

* `reports/`: one report per package (scope, changes, review findings,
  test runs, timings).
* `open_items.md`: everything left open, per package, and the user-side
  steps (merging, tagging, releases, upstream filing).
* `upstream/`: drafted texts for CoolProp issues, not filed.
* `pictures/`: charts referenced by the reports (before and after, themes,
  labels, cycles, conformance).
* `logs/`: summaries of the last full test runs of C1, 0.9 and 1.0, in the
  three native modes and with CoolProp's numerics port.
