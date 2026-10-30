// Mirrors tests/test_layout.py (number format) and tests/test_style.py.
#include <catch2/catch_all.hpp>
#include <limits>

#include "coolplot/core.h"
#include "coolplot/style.h"

using namespace coolplot;
using Catch::Matchers::WithinULP;

namespace {

// Exact element by element: the same size, and each element within 0 ulp.
void check_exactly(const std::vector<double>& got, const std::vector<double>& want) {
    REQUIRE(got.size() == want.size());
    for (size_t i = 0; i < got.size(); ++i) CHECK_THAT(got[i], WithinULP(want[i], 0));
}

}  // namespace

TEST_CASE("The central number format", "[core]") {
    CHECK(format_number(25.0) == "25");
    CHECK(format_number(0.1 + 0.2) == "0.3");
    CHECK(format_number(1e6) == "1e6");
    CHECK(format_number(2.5e-4) == "2.5e-4");
    CHECK(format_number(-20.0) == "-20");
    CHECK(format_number(100000.0) == "100000");
    CHECK(format_number(1.7976931348623157e308, 1) == "2e308");  // rounding overflows, the value decides
    CHECK(format_number(2.5, 1) == "2");                         // an exact tie goes to the even digit
    CHECK(format_number(0.125, 2) == "0.12");
    CHECK(fixed_text(1e21, 3) == "1000000000000000000000.000");
    CHECK(fixed_text(0.0625, 3) == "0.062");
    CHECK(text_length("caf\xc3\xa9 \xf0\x9f\x98\x80") == 6);
    CHECK(text_prefix("caf\xc3\xa9!", 4) == "caf\xc3\xa9");
    CHECK(format_number(0.0) == "0");
    CHECK(format_number(1e5, 6) == "100000");
    CHECK(format_number(273.15, 4) == "273.1");   // 273.15 is 273.1499... in binary, as in Python
    CHECK(format_number(std::nan("")) == "nan");
    CHECK(format_number(-std::numeric_limits<double>::infinity()) == "-inf");
    CHECK(repr_number(0.1) == "0.1");
    CHECK(repr_number(100.0) == "100.0");
    CHECK(repr_number(1e-5) == "1e-05");
    CHECK(repr_number(0.30000000000000004) == "0.30000000000000004");
    CHECK(repr_number(1e16) == "1e+16");
    CHECK(repr_number(25000.0) == "25000.0");
    CHECK(repr_number(9565121.031517146) == "9565121.031517146");
    CHECK_THAT(snap(253.14999999999998), WithinULP(253.15, 0));
}

TEST_CASE("Quantities and their aliases", "[core]") {
    CHECK(quantity_key("P") == "p");
    CHECK(quantity_key("Hmass") == "h");
    CHECK(quantity_key("x") == "Q");
    CHECK(quantity_key("RHO") == "rho");
    CHECK(get_quantity("p").log_scale);
    CHECK(get_quantity("h").label == "Specific enthalpy");
    CHECK_THROWS_AS(quantity_key("banana"), Error);
}

TEST_CASE("Symbols and units in unicode and ascii style, as in Python", "[core]") {
    // UTF-8 bytes, as in coolplot.core.symbols
    CHECK(symbol_text("rho", "unicode") == "\xcf\x81");
    CHECK(symbol_text("RH", "unicode") == "\xcf\x86");
    CHECK(symbol_text("Twb", "unicode") == "T_wb");
    CHECK(symbol_text("h", "unicode") == "h");
    CHECK(symbol_text("rho", "ascii") == "rho");
    CHECK(unit_text("deg C", "unicode") == "\xc2\xb0" "C");
    CHECK(unit_text("kg/m3", "unicode") == "kg/m\xc2\xb3");
    CHECK(unit_text("kJ/kg", "unicode") == "kJ/kg");
    CHECK(unit_text("deg C", "ascii") == "deg C");
    CHECK_THROWS_AS(check_symbol_style("latex"), Error);
}

TEST_CASE("Unit systems", "[core]") {
    const UnitSystem& eng = get_unit_system("engineering");
    CHECK(eng.at("T").from_SI(273.15) == Catch::Approx(0.0));
    CHECK(eng.at("p").from_SI(1e5) == Catch::Approx(1.0));
    CHECK(eng.at("T").difference_label == "K");
    CHECK_THROWS_AS(get_unit_system("EUR"), Error);                       // removed in 1.0
    CHECK(UnitSystem::from_json(json("EUR")).name == "engineering");     // a record saved by 0.4 still reads
    CHECK(get_unit_system("IP").at("T").from_SI(273.15) == Catch::Approx(32.0));
    // A line at 0 deg F, kept in K to 12 significant digits, is labelled 0, not -4e-10
    const Unit& fahrenheit = get_unit_system("IP").at("T");
    CHECK(fahrenheit.from_SI(255.372222222) != 0.0);
    CHECK(fahrenheit.label_value(255.372222222) == 0.0);
    CHECK(fahrenheit.label_value(273.15) == Catch::Approx(32.0));
    CHECK(eng.at("p").label_value(1e-12) > 0.0);   // no offset: a small value stays
    CHECK(eng.to_json() == json("engineering"));
    UnitSystem custom = eng;
    custom.name = "mine";
    custom.units["p"] = Unit{"MPa", 1e-6, 0.0, ""};
    json record = custom.to_json();
    CHECK(record.at("units").at("p") == json::array({"MPa", 1e-6, 0.0}));
    CHECK(record.at("units").at("T") == json::array({"deg C", 1.0, -273.15, "K"}));
    UnitSystem again = UnitSystem::from_json(record);
    CHECK_THAT(again.at("p").scale, WithinULP(1e-6, 0));
    CHECK(again.at("T").difference_label == "K");
    CHECK_THROWS_AS(get_unit_system("cgs"), Error);
}

TEST_CASE("Diagram types and families", "[core]") {
    DiagramType ph = DiagramType::parse("ph");
    CHECK(ph.y == "p");
    CHECK(ph.x == "h");
    CHECK(ph.y_log());
    CHECK_FALSE(ph.x_log());
    std::vector<std::string> keys;
    for (const Family& f : ph.families()) keys.push_back(f.key);
    CHECK(keys == std::vector<std::string>{"T", "s", "rho", "u", "Q"});
    CHECK(ph.family("p") == nullptr);
    CHECK(ph.family("Q")->on_boundary());
    CHECK(ph.family("Q")->is_boundary_value(1.0));
    CHECK_FALSE(ph.family("Q")->has_line(1.5));
    DiagramType wt = DiagramType::parse("psychrometric");
    CHECK(wt.kind == "humid_air");
    CHECK(wt.quantity_label("T") == "Dry-bulb temperature");
    CHECK_FALSE(wt.family("RH")->has_line(0.0));
    CHECK(wt.family("RH")->has_line(1.0));
    CHECK_THROWS_AS(DiagramType::parse("xy"), Error);
}

TEST_CASE("Colours are normalised", "[style]") {
    std::pair<Color, double> red = parse_color("Red");
    CHECK(red.first == Color::of("#ff0000"));
    CHECK_THAT(red.second, WithinULP(1.0, 0));
    std::pair<Color, double> grey = parse_color("#ABC");
    CHECK(grey.first == Color::of("#aabbcc"));
    CHECK_THAT(grey.second, WithinULP(1.0, 0));
    std::pair<Color, double> half = parse_color("#00ff0080");
    CHECK(half.first == Color::of("#00ff00"));
    CHECK(half.second == Catch::Approx(128.0 / 255.0));
    CHECK(parse_color("#0f08").second == Catch::Approx(0x88 / 255.0));
    CHECK_FALSE(parse_color("none").first.present);
    for (const char* bad : {"reddish", "#12345", "rgb(1,2,3)", ""}) CHECK_THROWS_AS(parse_color(bad), Error);
}

TEST_CASE("Styles normalise and validate", "[style]") {
    LineStyle line = LineStyle::from_json({{"color", "#ff000080"}, {"alpha", 0.5}});
    CHECK(line.color == Color::of("#ff0000"));
    CHECK(line.alpha == Catch::Approx(0.5 * 128.0 / 255.0));
    check_exactly(LineStyle::from_json({{"dash", {2, 1}}}).dash.lengths, {2.0, 1.0});
    for (json bad : {json{{"dash", "wavy"}}, json{{"dash", {1.0}}}, json{{"width_pt", -1}}, json{{"alpha", 2}}, json{{"cap", "pointy"}},
                     json{{"color", "blurple"}}, json{{"colour", "red"}}})
        CHECK_THROWS_AS(LineStyle::from_json(bad), Error);
    CHECK_THROWS_AS(MarkerStyle::from_json({{"shape", "*"}}), Error);
    CHECK_THROWS_AS(TextStyle::from_json({{"h_align", "middle"}}), Error);
    CHECK_THROWS_AS(Font::from_json({{"weight", "heavy"}}), Error);
    CHECK(Font::from_json({{"family", "serif"}}).family == std::vector<std::string>{"serif"});
    // A colour field without an alpha of its own refuses partial transparency
    CHECK_THROWS_AS(LineStyle::from_json({{"casing_color", "#ff000080"}}), Error);
    CHECK_FALSE(MarkerStyle::from_json({{"face_color", "none"}}).face_color.present);
}

TEST_CASE("Dash patterns scale with the width but not below one point", "[style]") {
    CHECK(dash_pattern_pt(Dash{"solid", {}}, 2.0).empty());
    check_exactly(dash_pattern_pt(Dash{"dashed", {}}, 2.0), {7.4, 3.2});
    check_exactly(dash_pattern_pt(Dash{"dashed", {}}, 0.5), {3.7, 1.6});
    check_exactly(dash_pattern_pt(Dash{"", {4.0, 1.0}}, 3.0), {4.0, 1.0});
}

TEST_CASE("Themes round-trip through JSON and give out colours per slot", "[style]") {
    for (const char* name : {"default", "dark", "print", "coolpack"}) {
        const Theme& theme = get_theme(name);
        json record = theme.to_json();
        Theme again = Theme::from_json(json::parse(record.dump()));
        CHECK(again.to_json() == record);
        CHECK(again.name == name);
    }
    CHECK_THROWS_AS(Theme::from_json({{"colour", "red"}}), Error);
    // Labels in the colour of their lines: "text" when not given (a 1.0 record), checked, kept
    json record = get_theme("default").to_json();
    CHECK(record.at("isoline_label_color") == "text");
    record.erase("isoline_label_color");
    CHECK(Theme::from_json(record).isoline_label_color == "text");
    record["isoline_label_color"] = "line";
    CHECK(Theme::from_json(json::parse(record.dump())).to_json().at("isoline_label_color") == "line");
    record["isoline_label_color"] = "family";
    CHECK_THROWS_AS(Theme::from_json(record), Error);
    record["isoline_label_color"] = nullptr;
    CHECK_THROWS_AS(Theme::from_json(record), Error);
    const Theme& base = get_theme("default");
    std::vector<std::string> ph = {"T", "s", "rho"}, hs = {"T", "p", "rho"}, ts = {"p", "h", "rho"};
    // Slots, for a theme without pinned colours: given out per diagram type
    Theme slots = base;
    slots.has_isoline_colors = false;
    slots.isoline_colors.clear();
    CHECK(slots.isoline_style("T", ph).color.hex == slots.categorical[0]);
    CHECK(slots.isoline_style("T", hs).color.hex == slots.categorical[0]);
    CHECK(slots.isoline_style("rho", ph).color.hex == slots.categorical[2]);
    CHECK(slots.isoline_style("rho", ts).color.hex == slots.categorical[2]);
    CHECK(slots.isoline_style("p", ts).color.hex == slots.categorical[0]);
    const Theme& print = get_theme("print");
    CHECK(print.isoline_style("T", ph).dash.name == "solid");
    CHECK(print.isoline_style("s", ph).dash.name == "dashed");
    CHECK(print.isoline_style("rho", ph).dash.name == "dotted");
    // The default themes pin one colour per quantity, the same on every chart
    CHECK(base.isoline_style("T", ph).color.hex == "#c72500");
    CHECK(base.isoline_style("p", ts).color.hex == "#621b40");
    CHECK(base.isoline_style("p", hs).color.hex == "#621b40");
    CHECK(base.isoline_style("h", ts).color.hex == "#ce52f9");
    CHECK(base.isoline_style("rho", ts).color.hex == base.isoline_style("rho", ph).color.hex);
    CHECK(get_theme("dark").isoline_style("Twb", {"RH", "Twb", "h", "v"}).color.hex == "#3a66d0");
    CHECK_FALSE(print.has_isoline_colors);
    CHECK_THROWS_AS(get_theme("classic"), Error);
    const Theme& coolpack = get_theme("coolpack");
    CHECK(coolpack.isoline_style("T", ph).color.hex == "#ff0000");
    CHECK(coolpack.isoline_style("s", ph).color.hex == "#0000ff");
    CHECK(coolpack.isoline_style("rho", ph).color.hex == "#008000");
    CHECK(coolpack.isoline_label_color == "line");
    CHECK(coolpack.axes.has_grid_minor);
    CHECK_FALSE(coolpack.axes.legend.visible);
    CHECK_THROWS_AS(Theme::from_json({{"categorical", {"nope"}}}), Error);
    CHECK_THROWS_AS(Theme::from_json({{"slot_dashes", {"wavy"}}}), Error);
    CHECK_THROWS_AS(AxesStyle::from_json({{"tick_direction", "sideways"}}), Error);
    CHECK_THROWS_AS(get_theme("neon"), Error);
    Theme scaled = base.scaled(2.0);
    CHECK_THAT(scaled.isoline_label.font.size_pt, WithinULP(15.0, 0));
    CHECK_THAT(scaled.axes.title.font.size_pt, WithinULP(22.0, 0));
    CHECK_THAT(scaled.isoline.width_pt, WithinULP(base.isoline.width_pt, 0));
}
