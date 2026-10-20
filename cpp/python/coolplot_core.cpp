// coolplot_core for Python: the composer and the SVG writer of coolplot-core.
//
// CoolPlot imports this module when it is installed (coolplot.compose.native)
// and uses it in place of its Python composer and SVG writer. The functions
// take and return JSON text, so the module needs nothing but nanobind.
#include <nanobind/nanobind.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

#include "coolplot/capi.h"
#include "coolplot/compose.h"
#include "coolplot/pdf.h"
#include "coolplot/svg.h"

namespace nb = nanobind;

namespace {

coolplot::SvgOptions options_of(int width, int height, std::pair<double, double> margins_lr, std::pair<double, double> margins_tb,
                                const std::string& id_prefix) {
    coolplot::SvgOptions options;
    options.width = width;
    options.height = height;
    options.margins[0] = margins_lr.first;
    options.margins[1] = margins_lr.second;
    options.margins[2] = margins_tb.first;
    options.margins[3] = margins_tb.second;
    options.id_prefix = id_prefix;
    return options;
}

coolplot::Scene scene_of(const std::string& scene_json) {
    coolplot::json data;
    try {
        data = coolplot::json::parse(scene_json);
    } catch (const coolplot::json::exception& e) {
        throw coolplot::Error(std::string("The scene is not valid JSON: ") + e.what());
    }
    return coolplot::Scene::from_json(data);
}

}  // namespace

NB_MODULE(coolplot_core, m) {
    m.doc() = "The presentation core of CoolPlot in C++: spec and curves in, scene and SVG out.";
    nb::exception<coolplot::Error>(m, "Error", PyExc_ValueError);
    // A record of the wrong shape (a string where a number belongs) surfaces
    // as an exception of the JSON library; it is bad input, so ValueError too
    nb::register_exception_translator([](const std::exception_ptr& p, void*) {
        try {
            std::rethrow_exception(p);
        } catch (const coolplot::json::exception& e) {
            PyErr_SetString(PyExc_ValueError, e.what());
        }
    });
    m.def("version", [] { return std::string(coolplot_version()); }, "The library version.");
    m.def(
      "compose", [](const std::string& input_json) { return coolplot::compose_json(input_json); }, nb::arg("input_json"),
      nb::call_guard<nb::gil_scoped_release>(),
      "The scene JSON of a chart from the compose record (spec, domain, curves, cycles, plot size, previous labels).");
    m.def(
      "scene_to_svg",
      [](const std::string& scene_json, int width, int height, std::pair<double, double> margins_lr, std::pair<double, double> margins_tb,
         const std::string& id_prefix) { return coolplot::scene_to_svg(scene_of(scene_json), options_of(width, height, margins_lr, margins_tb, id_prefix)); },
      nb::arg("scene_json"), nb::arg("width") = 800, nb::arg("height") = 600, nb::arg("margins_left_right") = std::make_pair(80.0, 20.0),
      nb::arg("margins_top_bottom") = std::make_pair(40.0, 60.0), nb::arg("id_prefix") = "coolplot", nb::call_guard<nb::gil_scoped_release>(),
      "The SVG document of a scene JSON, as coolplot.render.svg.SvgRenderer writes it.");
    m.def(
      "svg_plot_size_pt",
      [](const std::string& scene_json, int width, int height, std::pair<double, double> margins_lr, std::pair<double, double> margins_tb) {
          return coolplot::svg_plot_size_pt(scene_of(scene_json), options_of(width, height, margins_lr, margins_tb, "coolplot"));
      },
      nb::arg("scene_json"), nb::arg("width") = 800, nb::arg("height") = 600, nb::arg("margins_left_right") = std::make_pair(80.0, 20.0),
      nb::arg("margins_top_bottom") = std::make_pair(40.0, 60.0), "The (width, height) of the plot area in points.");
    m.def(
      "scene_to_pdf",
      [](const std::string& scene_json, double width_pt, double height_pt, std::pair<double, double> margins_lr,
         std::pair<double, double> margins_tb, const std::vector<std::string>& font_dirs, const std::vector<std::string>& font_files,
         bool compress) {
          coolplot::PdfOptions options;
          options.width_pt = width_pt;
          options.height_pt = height_pt;
          options.margins_pt[0] = margins_lr.first;
          options.margins_pt[1] = margins_lr.second;
          options.margins_pt[2] = margins_tb.first;
          options.margins_pt[3] = margins_tb.second;
          options.font_dirs = font_dirs;
          options.font_files = font_files;
          options.compress = compress;
          std::string bytes = coolplot::scene_to_pdf(scene_of(scene_json), options);
          return nb::bytes(bytes.data(), bytes.size());
      },
      nb::arg("scene_json"), nb::arg("width_pt") = 576.0, nb::arg("height_pt") = 432.0,
      nb::arg("margins_left_right") = std::make_pair(60.0, 15.0), nb::arg("margins_top_bottom") = std::make_pair(30.0, 45.0),
      nb::arg("font_dirs") = std::vector<std::string>(), nb::arg("font_files") = std::vector<std::string>(), nb::arg("compress") = true,
      "The PDF file of a scene JSON as bytes: one page, TrueType fonts embedded as subsets.");
    m.def(
      "pdf_plot_size_pt",
      [](const std::string& scene_json, double width_pt, double height_pt, std::pair<double, double> margins_lr,
         std::pair<double, double> margins_tb) {
          coolplot::PdfOptions options;
          options.width_pt = width_pt;
          options.height_pt = height_pt;
          options.margins_pt[0] = margins_lr.first;
          options.margins_pt[1] = margins_lr.second;
          options.margins_pt[2] = margins_tb.first;
          options.margins_pt[3] = margins_tb.second;
          return coolplot::pdf_plot_size_pt(scene_of(scene_json), options);
      },
      nb::arg("scene_json"), nb::arg("width_pt") = 576.0, nb::arg("height_pt") = 432.0,
      nb::arg("margins_left_right") = std::make_pair(60.0, 15.0), nb::arg("margins_top_bottom") = std::make_pair(30.0, 45.0),
      "The (width, height) of the plot area of the PDF page in points.");
}
