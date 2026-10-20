# coolplot-core

The presentation side of CoolPlot as a C++17 library: chart spec and curve
records in, scene JSON, SVG and PDF out. No CoolProp, no plotting library.
The documentation is `docs/contributing/core.md`; in short:

```bash
cmake -B build -S . -DCMAKE_BUILD_TYPE=Release
cmake --build build -j4
./build/coolplot_core_tests
```

Third-party code: `third_party/nlohmann/json.hpp` (nlohmann/json 3.12,
MIT, see `third_party/nlohmann/LICENSE.MIT`); Catch2 3.8 is fetched for
the tests.
