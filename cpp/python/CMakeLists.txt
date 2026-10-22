# The nanobind module coolplot_core: compose() and scene_to_svg() for Python.
#
# Built with -DCOOLPLOT_CORE_PYTHON=ON; needs nanobind (pip install nanobind)
# in the Python that CMake finds:
#   cmake -B build -S cpp -DCOOLPLOT_CORE_PYTHON=ON -DPython_EXECUTABLE=$(which python)
#   cmake --build build --target coolplot_core_py
# The module lands next to the library as coolplot_core.<abi>.so; put its
# directory on sys.path, or install it with the install target.
find_package(Python 3.11 COMPONENTS Interpreter Development.Module REQUIRED)
execute_process(
    COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
    OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE nanobind_DIR)
find_package(nanobind CONFIG REQUIRED)
nanobind_add_module(coolplot_core_py NB_STATIC coolplot_core.cpp)
target_link_libraries(coolplot_core_py PRIVATE coolplot_core)
set_target_properties(coolplot_core_py PROPERTIES OUTPUT_NAME "coolplot_core")
install(TARGETS coolplot_core_py LIBRARY DESTINATION .)
