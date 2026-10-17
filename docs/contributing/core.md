# coolplot-core: the presentation side in C++

`cpp/` holds coolplot-core, a C++17 library that does what
{mod}`coolplot.compose`, {mod}`coolplot.scene`, {mod}`coolplot.style` and
the SVG writer do in Python: the chart spec and the computed curve records
go in, the scene and the SVG document come out. It adds a PDF writer that
embeds TrueType fonts as subsets. It knows nothing of CoolProp and of any
plotting library; the numerics live in CoolProp (`CoolProp::Plot`, see
{doc}`../explanation/numerics`).

It exists so that charts can be drawn by programs that are not Python,
and so that one implementation of the layout serves every language. The
Python code stays the reference: every result of the C++ library is
compared with it, number for number and byte for byte.

## What is in it

| File | Port of | What it does |
|---|---|---|
| `include/coolplot/core.h` | `coolplot.core` | number format, quantities, unit systems, diagram types and families |
| `include/coolplot/style.h` | `coolplot.style` | colours, line, marker and text styles, themes, their JSON |
| `include/coolplot/scene.h` | `coolplot.scene` | items, axes, the scene and its JSON (the contract) |
| `include/coolplot/spec.h` | `coolplot.spec` | the parts of the chart spec the composer needs |
| `include/coolplot/layout.h` | `coolplot.compose.layout` | edge labels, margin labels, state numbers |
| `include/coolplot/compose.h` | `coolplot.compose.builder` | the scene of a chart from spec, domain, curves and cycles |
| `include/coolplot/svg.h` | `coolplot.render.svg` | the SVG document of a scene |
| `include/coolplot/pdf.h`, `truetype.h` | (new) | one PDF page with TrueType subsets, ToUnicode maps, sRGB |
| `include/coolplot/capi.h` | | the C ABI: JSON text in, JSON, SVG or PDF out |
| `python/coolplot_core.cpp` | | the nanobind module `coolplot_core` |

`src/coolplot/render/static/scene_svg.js` is the same SVG writer in
JavaScript: {func}`coolplot.render.web.scene_page` writes a page that
draws a scene in the browser without a server.

## Building and testing

```bash
cmake -B cpp/build -S cpp -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build -j4
./cpp/build/coolplot_core_tests                 # Catch2, against the golden files

pip install nanobind
cmake -B cpp/build_py -S cpp -DCOOLPLOT_CORE_TESTS=OFF -DCOOLPLOT_CORE_PYTHON=ON \
      -DPython_EXECUTABLE=$(which python)
cmake --build cpp/build_py --target coolplot_core_py
PYTHONPATH=cpp/build_py/python python -m pytest tests   # the whole suite through coolplot-core
```

Catch2 is fetched by CMake; set `FETCHCONTENT_SOURCE_DIR_CATCH2` to a
checkout to build offline. The JSON reader (nlohmann/json 3.12, MIT) is
vendored in `cpp/third_party`. zlib is used for the PDF streams when CMake
finds it.

With `COOLPLOT_NATIVE=1` (and `coolplot_core` importable),
{func}`coolplot.compose.compose` composes there and
{class}`~coolplot.render.svg.SvgRenderer` writes there. Unset, CoolPlot
keeps its Python composer and writer: from Python they are faster, because
the records cross into C++ as JSON. For a p-h chart with labels:

| Step | Time |
|---|---|
| Python composer | 25 ms |
| C++ composer, including its own JSON reading and writing | 12 ms |
| building and parsing the JSON on the Python side | 38 ms |

The library is for programs in other languages, which hand it their
records directly. `COOLPLOT_NATIVE=0` also switches the numerics port off.
CI runs the suite on the Python path and with `COOLPLOT_NATIVE=1`.
{class}`~coolplot.render.pdf.PdfRenderer` writes PDF through coolplot-core
and needs the module; its page has the plot size of the SVG writer, with
the same margins for labels outside the frame and the same cut of long
legend texts.

When the C++ composer refuses a spec that Python accepts (something added
in Python and not ported yet), {func}`coolplot.compose.compose` warns with
a RuntimeWarning and the Python composer draws the chart.

Rules both sides keep, so that the outputs stay identical:

* Numbers are written without the C locale: `std::to_chars` and
  `std::from_chars` in C++, so a host program that sets a locale with a
  decimal comma gets the same documents (cpp/tests checks this under
  de_DE when that locale is installed). The JavaScript writer rounds an
  exact tie to the even digit, as Python and printf do.
* Text lengths count characters (Unicode code points), not bytes or
  UTF-16 units.
* Label spots whose bends differ by rounding noise tie: the bend counts in
  whole millionths of a degree, and the first spot found wins.
* Writers take the items in scene order (the legend follows it) and sort
  by z order themselves; `Scene.to_dict(in_draw_order=False)` gives that
  record.

## The golden files

`cpp/tests/data` holds compose inputs, the scenes the Python composer
makes of them and the SVG documents the Python writer makes of those
scenes. After a change to the Python composer or writer, write them again
and check the diff:

```bash
python cpp/tests/data/make_data.py
./cpp/build/coolplot_core_tests && node tests/js/check_scene_svg.js
```

A change has to land in both implementations; a scene or SVG that differs
between them fails the C++ tests, `tests/test_native_core.py` and
`tests/test_scene_js.py`.
