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

When `coolplot_core` can be imported, {func}`coolplot.compose.compose`
composes there and {class}`~coolplot.render.svg.SvgRenderer` writes there;
`COOLPLOT_NATIVE=0` switches both back to Python. CI runs the suite on
both paths. {class}`~coolplot.render.pdf.PdfRenderer` writes PDF through
coolplot-core and needs the module.

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
