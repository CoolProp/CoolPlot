# coolplot-core: the presentation side of CoolPlot as a C++ library.
#
# Spec JSON and curve records in, scene JSON out; an SVG writer; a C ABI
# and (optionally) a nanobind module. No CoolProp, no plotting library.
#
#   cmake -B build -S cpp -DCMAKE_BUILD_TYPE=Release
#   cmake --build build
#   ./build/coolplot_core_tests
#
# Catch2 is fetched for the tests; set FETCHCONTENT_SOURCE_DIR_CATCH2 to a
# local checkout to build offline.
cmake_minimum_required(VERSION 3.16)
project(coolplot_core VERSION 1.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

option(COOLPLOT_CORE_TESTS "Build the Catch2 tests" ON)
option(COOLPLOT_CORE_PYTHON "Build the nanobind module (needs nanobind and a Python with headers)" OFF)

add_library(coolplot_core STATIC
    src/core.cpp
    src/style.cpp
    src/scene.cpp
    src/spec.cpp
    src/layout.cpp
    src/compose.cpp
    src/svg.cpp
    src/truetype.cpp
    src/pdf.cpp
    src/capi.cpp
)
# Flate compression of the PDF streams when zlib is there; the files are
# written uncompressed without it
find_package(ZLIB)
if(ZLIB_FOUND)
    target_link_libraries(coolplot_core PUBLIC ZLIB::ZLIB)
    target_compile_definitions(coolplot_core PRIVATE COOLPLOT_HAVE_ZLIB)
endif()
target_include_directories(coolplot_core
    PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/third_party
    PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/third_party>
)
set_target_properties(coolplot_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
# coolplot_version() reports the project version; the Python bridge refuses
# features a core older than the CoolPlot release does not know
target_compile_definitions(coolplot_core PRIVATE COOLPLOT_CORE_VERSION="${PROJECT_VERSION}")
if(MSVC)
    target_compile_options(coolplot_core PRIVATE /W4)
else()
    # No fused multiply-add: a*b+c has to round twice, as in Python, or
    # positions differ in the last bit (clang fuses by default on arm64)
    target_compile_options(coolplot_core PRIVATE -Wall -Wextra -Wshadow -ffp-contract=off)
endif()

if(COOLPLOT_CORE_TESTS)
    include(FetchContent)
    FetchContent_Declare(Catch2
        GIT_REPOSITORY https://github.com/catchorg/Catch2.git
        GIT_TAG v3.8.0
    )
    FetchContent_MakeAvailable(Catch2)
    add_executable(coolplot_core_tests
        tests/test_core.cpp
        tests/test_scene.cpp
        tests/test_layout.cpp
        tests/test_compose.cpp
        tests/test_svg.cpp
        tests/test_pdf.cpp
    )
    target_link_libraries(coolplot_core_tests PRIVATE coolplot_core Catch2::Catch2WithMain)
    target_compile_definitions(coolplot_core_tests PRIVATE COOLPLOT_TEST_DATA="${CMAKE_CURRENT_SOURCE_DIR}/tests/data")
    enable_testing()
    add_test(NAME coolplot_core_tests COMMAND coolplot_core_tests)
endif()

if(COOLPLOT_CORE_PYTHON)
    add_subdirectory(python)
endif()
