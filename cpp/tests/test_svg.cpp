// The SVG writer against the documents the Python writer makes of the same scenes.
#include <catch2/catch_all.hpp>

#include <clocale>
#include <cmath>
#include <fstream>
#include <sstream>

#include "coolplot/capi.h"
#include "coolplot/compose.h"
#include "coolplot/pdf.h"
#include "coolplot/svg.h"

using namespace coolplot;

namespace {

std::string read(const std::string& name) {
    std::ifstream in(std::string(COOLPLOT_TEST_DATA) + "/" + name);
    REQUIRE(in.good());
    std::stringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

json load(const std::string& name) {
    return json::parse(read(name));
}

/// The first line that differs, for a readable failure.
std::string first_difference(const std::string& a, const std::string& b) {
    std::istringstream sa(a), sb(b);
    std::string la, lb;
    int line = 0;
    while (true) {
        bool ga = static_cast<bool>(std::getline(sa, la)), gb = static_cast<bool>(std::getline(sb, lb));
        ++line;
        if (!ga && !gb) return "";
        if (la != lb) return "line " + std::to_string(line) + ":\n  made:     " + la.substr(0, 200) + "\n  expected: " + lb.substr(0, 200);
    }
}

void check_svg(const Scene& scene, const std::string& golden, const SvgOptions& options = SvgOptions()) {
    std::string made = scene_to_svg(scene, options);
    std::string expected = read(golden);
    std::string difference = first_difference(made, expected);
    INFO(golden << ": " << difference);
    CHECK(difference.empty());
    CHECK(made == expected);
}

}  // namespace

TEST_CASE("Ticks", "[svg]") {
    CHECK(ticks(0.0, 10.0, false) == std::vector<double>{0.0, 2.0, 4.0, 6.0, 8.0, 10.0});
    CHECK(ticks(0.1, 100.0, true) == std::vector<double>{0.1, 1.0, 10.0, 100.0});
    CHECK(ticks(1.0, 50.0, true) == std::vector<double>{1.0, 2.0, 5.0, 10.0, 20.0, 50.0});
    CHECK(ticks(1.5, 1.9, true).size() >= 3);  // a range inside one decade falls back to linear steps
    CHECK(ticks(0.1, 1.0, true, true).size() == 8);
    CHECK(ticks(5.0, 5.0, false) == std::vector<double>{5.0});
}

TEST_CASE("XML escaping as the Python writer does it", "[svg]") {
    CHECK(xml_text("a <b> & c") == "a &lt;b&gt; &amp; c");
    CHECK(xml_attr("plain") == "\"plain\"");
    CHECK(xml_attr("say \"hi\"") == "'say \"hi\"'");
    CHECK(xml_attr("it's \"both\"") == "\"it's &quot;both&quot;\"");
    CHECK(xml_attr("tab\there") == "\"tab&#9;here\"");
    CHECK(xml_text(std::string("bad\x01") + "char") == "badchar");
    CHECK(ascii_only("caf\xc3\xa9") == "caf&#233;");
    CHECK(ascii_only("\xe2\x80\x93") == "&#8211;");
}

TEST_CASE("The conformance scene renders byte for byte as in Python", "[svg]") {
    Scene scene = Scene::from_json(load("conformance_scene.json"));
    check_svg(scene, "conformance_scene.svg");
    SvgOptions small;
    small.width = 640;
    small.height = 480;
    small.margins[0] = 50;
    small.margins[1] = 10;
    small.margins[2] = 30;
    small.margins[3] = 40;
    small.id_prefix = "2 charts/one page";
    check_svg(scene, "conformance_scene_small.svg", small);
    for (const char* location : {"upper left", "lower right"}) {
        Scene moved = scene;
        moved.axes.style.legend.location = location;
        std::string name = std::string("conformance_legend_") + (std::string(location) == "upper left" ? "upper_left" : "lower_right") + ".svg";
        check_svg(moved, name);
    }
    CHECK(svg_plot_size_pt(scene).first > 0.0);
}

TEST_CASE("Autoscaled axes and a narrow log range", "[svg]") {
    Scene scene;
    scene.axes.y_log = true;
    Item a, b, hidden;
    a.id = "a";
    a.x = {1.0, 2.0, 3.0};
    a.y = {0.5, 5.0, 50.0};
    b.type = ItemType::Markers;
    b.id = "b";
    b.x = {4.0};
    b.y = {std::nan("")};
    hidden.id = "hidden";
    hidden.visible = false;
    hidden.x = {-100.0, 1000.0};
    hidden.y = {1e-6, 1e9};
    scene.items = {a, b, hidden};
    check_svg(scene, "autoscale.svg");
    Scene narrow;
    narrow.axes.y_log = true;
    narrow.axes.has_x_limits = narrow.axes.has_y_limits = true;
    narrow.axes.x_limits = narrow.axes.y_limits = {1.5, 1.9};
    Item line;
    line.id = "a";
    line.x = {1.5, 1.9};
    line.y = {1.5, 1.9};
    narrow.items = {line};
    check_svg(narrow, "narrow_log.svg");
}

TEST_CASE("The composed charts render as in Python", "[svg]") {
    for (const char* name : {"compose_r290_ph", "compose_r290_ph_sized", "compose_blend_ts_margin", "compose_r290_hs_inline", "compose_psychrometric"}) {
        json data = load(std::string(name) + ".json");
        Scene scene = Scene::from_json(data.at("scene_order"));  // the legend follows the scene order
        check_svg(scene, std::string(name) + ".svg");
        // The whole way: compose from the input record, then write
        Scene composed = Scene::from_json(json::parse(compose_json(data.at("input").dump())));
        check_svg(composed, std::string(name) + ".svg");
    }
}

TEST_CASE("The C ABI composes, writes SVG and reports errors", "[svg][capi]") {
    json data = load("compose_r290_ph.json");
    std::string input = data.at("input").dump();
    char* scene_json = nullptr;
    char* error = nullptr;
    REQUIRE(coolplot_compose(input.c_str(), &scene_json, &error) == 0);
    REQUIRE(scene_json != nullptr);
    CHECK(error == nullptr);
    json made = json::parse(scene_json);
    CHECK(made.at("items").size() == data.at("scene").at("items").size());
    char* svg = nullptr;
    double margins[4] = {80.0, 20.0, 40.0, 60.0};
    REQUIRE(coolplot_scene_to_svg(scene_json, 800, 600, margins, "coolplot", &svg, &error) == 0);
    CHECK(std::string(svg).rfind("<svg", 0) == 0);
    double w = 0.0, h = 0.0;
    REQUIRE(coolplot_svg_plot_size_pt(scene_json, 800, 600, margins, &w, &h, &error) == 0);
    CHECK(w > 0.0);
    coolplot_free(svg);
    coolplot_free(scene_json);
    CHECK(coolplot_compose("{not json", &scene_json, &error) == 1);
    REQUIRE(error != nullptr);
    CHECK(std::string(error).find("not valid JSON") != std::string::npos);
    coolplot_free(error);
    CHECK(coolplot_compose(nullptr, &scene_json, nullptr) == 1);
    CHECK(std::string(coolplot_version()) == "0.1.0");
}

TEST_CASE("The writers ignore the C locale", "[svg][pdf][locale]") {
    // A host application may set a locale whose decimal separator is a comma;
    // numbers in SVG, PDF and JSON have to keep the point
    const char* names[] = {"de_DE.UTF-8", "de_DE.utf8", "de_DE", "fr_FR.UTF-8", "fr_FR.utf8"};
    std::string old = std::setlocale(LC_NUMERIC, nullptr);
    const char* found = nullptr;
    for (const char* name : names)
        if (std::setlocale(LC_NUMERIC, name)) {
            found = name;
            break;
        }
    if (!found) SKIP("No locale with a decimal comma is installed");
    INFO("locale " << found);
    json data = load("compose_r290_ph.json");
    std::string svg, pdf, composed;
    // The PDF needs a TrueType font; without one only the SVG is compared
    auto pdf_of = [](const Scene& scene) {
        try {
            return scene_to_pdf(scene, PdfOptions());
        } catch (const Error&) {
            return std::string();
        }
    };
    try {
        composed = compose_json(data.at("input").dump());
        Scene scene = Scene::from_json(json::parse(composed));
        svg = scene_to_svg(scene, SvgOptions());
        pdf = pdf_of(scene);
        CHECK(format_number(0.5) == "0.5");
        CHECK(snap(253.14999999999998) == 253.15);
        CHECK(DiagramSpec::from_json(data.at("input").at("spec")).diagram.name() == "ph");
    } catch (...) {
        std::setlocale(LC_NUMERIC, old.c_str());
        throw;
    }
    std::setlocale(LC_NUMERIC, old.c_str());
    CHECK(svg == read("compose_r290_ph.svg"));
    std::string again = compose_json(data.at("input").dump());
    CHECK(composed == again);
    if (pdf.empty()) WARN("No TrueType font found: the PDF was not compared.");
    CHECK(pdf == pdf_of(Scene::from_json(json::parse(again))));
}
