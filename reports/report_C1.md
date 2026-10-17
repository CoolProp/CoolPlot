# Report C1: coolplot-core (CoolPlot branch chp/c1, from chp/c0)

Scope (docs/contributing/v1_plan.md, C1): (1) a library with CMake and Catch2;
(2) spec JSON and curve records in, scene JSON out; (3) the SVG writer; (4) a PDF
writer with TrueType subsetting; (5) a C ABI and a nanobind module; (6) built in
CoolProp's wrapper matrix (D7); (7) a JavaScript renderer of scene JSON.
Acceptance: the conformance kit green with the C++ scene feeding the existing
matplotlib and plotly renderers; the SVG of every example identical to the Python
SVG writer's. Steps 1 to 5 and 7 are done; step 6 is not (see below).

## What changed

* `cpp/` (C++17, about 4500 lines with tests): `core.h` (number format, Python
  float repr, quantities, unit systems, diagram types and families), `style.h`
  (colours with the CSS names, line/marker/text/legend/axes styles, themes and
  the four presets, strict JSON reading as in Python), `scene.h` (items, axes,
  scene, JSON, drawing order, legend entries), `spec.h` (the parts of the spec
  the composer reads), `layout.h` (edge labels with candidates, keep-out zones,
  previous labels; margin labels; state numbers), `compose.h` (the scene of a
  chart from the compose record), `svg.h` (the SVG document), `truetype.h` and
  `pdf.h` (new: a TrueType reader and subsetter, a font index over the platform's
  font directories, one PDF page with CID fonts, ToUnicode maps, sRGB colours,
  ExtGState alpha, Flate streams when zlib is found, no dates), `capi.h` (JSON
  text in, JSON/SVG/PDF out, errors as text), `python/` (the nanobind module
  `coolplot_core`, GIL released while composing and writing).
* Tests: 33 Catch2 cases (436 assertions): the core, styles and themes (mirroring
  tests/test_style.py), scene JSON, layout (mirroring tests/test_layout.py), five
  composed charts against the Python composer (p-h with cycle and edge labels;
  the same laid out for another plot size with previous labels; a blend in T-s
  with margin labels and the print theme; inline labels with a style override,
  font scale and title; a psychrometric chart with an air process), eleven SVG
  documents byte for byte against the Python writer, the C ABI, the PDF writer.
  The golden files come from `cpp/tests/data/make_data.py`.
* Python: `coolplot.corelib` (the bridge, below compose and render),
  `coolplot.compose.compose` and `SvgRenderer.to_svg` use it with
  `COOLPLOT_NATIVE=1`; `coolplot.render.pdf.PdfRenderer` (PDF without
  matplotlib); `coolplot.render.static.scene_svg.js` and
  `coolplot.render.web.scene_page` (a page that draws a scene in the browser,
  no server); layer rules for the two new modules; tests/test_native_core.py
  and tests/test_scene_js.py.
* Documentation: docs/contributing/core.md, cpp/README.md, the changelog; CI job
  "core" (builds the library, runs its tests and the whole suite through the
  module).

## Acceptance

* Conformance kit through coolplot-core: the SVG backend writing through the
  module passes the kit; the PDF backend passes the kit including its PDF check
  (fonts embedded as TrueType with matching programs, every text as written, only
  the scene's colours, the title, the same file twice).
* The C++ scene feeds the existing renderers: the whole suite runs with
  `COOLPLOT_NATIVE=1`, so every chart test, the matplotlib, plotly, SVG and web
  backends and the examples draw scenes composed in C++.
* The SVG of every example (quickstart, psychrometric, refrigerant blend; the
  others write no SVG) is byte-identical between `COOLPLOT_NATIVE=0` and `=1`.
* The JavaScript renderer writes the same eleven golden SVG files byte for byte
  (Node), and a browser page made by `scene_page` holds the same items in the
  same order as the SVG backend's document (Playwright).

## Numbers

From Python, best of five, curves cached:

| chart | compose Python | compose through C++ | SVG Python | SVG through C++ |
|---|---|---|---|---|
| R290 p-h with labels and a cycle (102 items, 8472 points) | 24.8 ms | 65.3 ms | 13.4 ms | 24.0 ms |
| R407C T-s (99 items, 8089 points) | 19.2 ms | 47.1 ms | 12.5 ms | 22.6 ms |
| psychrometric (68 items, 4358 points) | 13.0 ms | 31.3 ms | 7.2 ms | 13.3 ms |

Of the 65 ms for the p-h chart, the C++ composer with its own JSON reading and
writing takes 12 ms; building the record (11 ms), writing it as JSON (9 ms),
reading the result (4 ms) and turning it into items (15 ms) take the rest. From
Python the port is therefore slower, and CoolPlot keeps its Python composer and
writer unless `COOLPLOT_NATIVE=1` is set; the library is for programs in other
languages. A binary record (arrays as buffers) would remove most of the crossing
(open item).

## Review

An adversarial review of the first C1 commit found seven blocking issues; all
are fixed in the follow-up commit, each with a test:

1. A diagram of any fluid axis pair (`DiagramType("T", "h")`, written "Th")
   failed on the native path, and its spec did not read back in Python
   either. Both sides now parse such names; when the port refuses a spec,
   compose warns and the Python composer draws the chart.
2. Text lengths counted bytes (C++) or UTF-16 units (JS) instead of
   characters, so legends and margins with non-ASCII text differed. All
   three count code points now.
3. Label spots whose scores differed only by rounding noise could be picked
   differently in C++ and Python. The bend now counts in whole millionths of
   a degree on both sides, so such spots tie and the first one found wins.
4. Numbers went through printf/strtod, which follow the C locale: a host
   program with a German locale would have got commas in SVG and PDF. Now
   std::to_chars/from_chars; a Catch2 test writes SVG, PDF and JSON under
   de_DE and compares them with the C locale output.
5. The TrueType reader trusted table lengths. Each table is now checked
   against the fields read from it.
6. The PDF page ignored the margins for labels outside the frame and did not
   cut long legend texts, so its plot size differed from the SVG writer's
   and text could leave the page. Ported; `PdfRenderer.plot_size_pt` comes
   from the core, and a test checks that every text starts and ends on the
   page.
7. `scene_page` and the SVG goldens used drawing order, so the legend order
   could differ from the SVG backend. They use scene order now
   (`Scene.to_dict(in_draw_order=False)`); the C++ test also composes from
   the input record and writes SVG, end to end.

Non-blocking ones fixed on the way: JS rounding of exact ties to the even
digit (Python and printf do that, toFixed does not) and of numbers from
1e21; a `format_number` crash on the largest doubles, found by the new
JS-versus-Python test and fixed in all three implementations; the C ABI
nulls its outputs on failure and catches everything; JSON errors from the
module are ValueError; duplicate ids found with a set; the fallback glyph
reads back as "?"; nanobind pinned in CI; PdfRenderer.save renders before
opening the file.

A second review of the fix commit found four more blocking issues, fixed in
a third commit:

1. The fallback caught every ValueError, so in the native CI job a port that
   refused every chart would still have passed through Python. Only the
   port's own error (`coolplot_core.Error`, raised as `CoreRefusal`) falls
   back now, with its own `CoreFallbackWarning`; CI turns that warning into
   an error, and the suite passes that way.
2. Parsing an overflowing number still went through strtod, which follows
   the locale: under de_DE, `format_number(DBL_MAX, 2)` gave "1" instead
   of "1.8e308". Overflow now returns infinity or zero directly; the locale
   test checks it.
3. The locale test skipped on CI runners (no de_DE). CI now generates the
   locale and sets `COOLPLOT_REQUIRE_LOCALE`, which turns the skip into a
   failure.
4. The C++ bend divided by pi/180 where Python's math.degrees multiplies by
   180/pi, one ULP apart in 11 % of cases. It multiplies now. The library is
   also compiled with `-ffp-contract=off`, so no platform fuses a*b+c.

The reviewer compared JS and C++ number formatting with Python on 6043
values (exact ties, subnormals, values from 1e21, random bit patterns):
no difference. Remaining trade-offs are in open_items.md.

## Test runs

| run | result |
|---|---|
| Catch2, with COOLPLOT_REQUIRE_LOCALE=1 | 33 cases, 436 assertions passed |
| pytest, COOLPLOT_NATIVE=1 | 361 passed, 40 skipped |
| pytest, COOLPLOT_NATIVE=0 | 361 passed, 40 skipped |
| pytest, COOLPLOT_NATIVE unset | 361 passed, 40 skipped |
| after the second fixes: COOLPLOT_NATIVE=1 with -W error::CoreFallbackWarning | 362 passed, 40 skipped |
| after the second fixes: COOLPLOT_NATIVE unset | 362 passed, 40 skipped |
| JS goldens (Node) and browser page (Playwright) | identical |
| Sphinx -W | clean |

Commits on chp/c1: 797572c (port), 722e069 (opt-in), f4598c4 (first review fixes), 9fed81f (second review fixes). Pushed.
