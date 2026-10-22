// The composer against the scenes the Python composer makes of the same input (tests/data).
#include <catch2/catch_all.hpp>

#include <cmath>
#include <fstream>

#include "coolplot/compose.h"

using namespace coolplot;

namespace {

json load(const std::string& name) {
    std::ifstream in(std::string(COOLPLOT_TEST_DATA) + "/" + name);
    REQUIRE(in.good());
    return json::parse(in);
}

bool close(double a, double b, double rel) {
    if (std::isnan(a) && std::isnan(b)) return true;
    return std::fabs(a - b) <= rel * std::max({std::fabs(a), std::fabs(b), 1e-300}) || std::fabs(a - b) < 1e-12;
}

/// Compare two JSON values, numbers within a relative tolerance; returns the first difference.
std::string compare(const json& a, const json& b, const std::string& path, double rel) {
    if (a.is_number() && b.is_number()) return close(a.get<double>(), b.get<double>(), rel) ? "" : path + ": " + a.dump() + " vs " + b.dump();
    if (a.type() != b.type()) return path + ": " + a.dump().substr(0, 60) + " vs " + b.dump().substr(0, 60);
    if (a.is_object()) {
        for (auto it = a.begin(); it != a.end(); ++it) {
            if (!b.contains(it.key())) return path + "." + it.key() + ": missing on the right";
            std::string d = compare(it.value(), b.at(it.key()), path + "." + it.key(), rel);
            if (!d.empty()) return d;
        }
        for (auto it = b.begin(); it != b.end(); ++it)
            if (!a.contains(it.key())) return path + "." + it.key() + ": missing on the left";
        return "";
    }
    if (a.is_array()) {
        if (a.size() != b.size()) return path + ": " + std::to_string(a.size()) + " vs " + std::to_string(b.size()) + " entries";
        for (size_t i = 0; i < a.size(); ++i) {
            std::string d = compare(a[i], b[i], path + "[" + std::to_string(i) + "]", rel);
            if (!d.empty()) return d;
        }
        return "";
    }
    return a == b ? "" : path + ": " + a.dump() + " vs " + b.dump();
}

void check_case(const std::string& name) {
    json data = load(name);
    Scene scene = compose(data.at("input"));
    json made = scene.to_json();
    const json& expected = data.at("scene");
    INFO(name << ": " << made.at("items").size() << " items made, " << expected.at("items").size() << " expected");
    // Same items in the same order
    std::vector<std::string> made_ids, expected_ids;
    for (const json& i : made.at("items")) made_ids.push_back(i.at("id"));
    for (const json& i : expected.at("items")) expected_ids.push_back(i.at("id"));
    CHECK(made_ids == expected_ids);
    std::string difference = compare(made, expected, "scene", 1e-9);
    INFO(difference);
    CHECK(difference.empty());
}

}  // namespace

TEST_CASE("A p-h chart with labels and a cycle composes as in Python", "[compose]") {
    check_case("compose_r290_ph.json");
}

TEST_CASE("The same chart laid out for a renderer's size keeps its previous labels", "[compose]") {
    check_case("compose_r290_ph_sized.json");
}

TEST_CASE("A blend in a T-s chart with margin labels and the print theme", "[compose]") {
    check_case("compose_blend_ts_margin.json");
}

TEST_CASE("Inline labels, a style override, a scaled theme and a title", "[compose]") {
    check_case("compose_r290_hs_inline.json");
}

TEST_CASE("A psychrometric chart with an air process", "[compose]") {
    check_case("compose_psychrometric.json");
    check_case("compose_r290_ph_anchored.json");
    check_case("compose_r290_ph_line_labels.json");
}

TEST_CASE("State labels after the numbers, and alone with the numbers hidden", "[compose]") {
    check_case("compose_psychrometric_labels.json");
}

TEST_CASE("The Mollier h,x chart with isotherms, x and phi", "[compose]") {
    check_case("compose_mollier.json");
}

TEST_CASE("The saturation curve without lines of constant quality", "[compose]") {
    check_case("compose_r290_ts_saturation_only.json");
}

TEST_CASE("Labels on rails, with the legend in the emptiest corner", "[compose][rails]") {
    check_case("compose_rails_r290_ph.json");
    check_case("compose_rails_r290_ph_narrow.json");
    check_case("compose_rails_r290_ph_outside_legend.json");
    check_case("compose_rails_r290_ph_anchored.json");
}

TEST_CASE("Rails keep their labels and families when a state moves", "[compose][rails]") {
    check_case("compose_rails_r290_ph_moved.json");
}

TEST_CASE("Rails on psychrometric and Mollier charts", "[compose][rails]") {
    check_case("compose_rails_psychrometric.json");
    check_case("compose_rails_mollier.json");
}

TEST_CASE("Malformed state labels are refused, a null list reads as none", "[compose]") {
    json input = load("compose_psychrometric_labels.json").at("input");
    for (const char* bad : {R"([[2.5, "x"]])", R"([[2, 3]])", R"([[2]])", R"([[2, "a"], [2, "b"]])", R"({"2": "x"})"}) {
        json changed = input;
        changed["spec"]["cycles"][0]["labels"] = json::parse(bad);
        INFO(bad);
        CHECK_THROWS_AS(compose_json(changed.dump()), Error);
    }
    json none = input;
    none["spec"]["cycles"][0]["labels"] = nullptr;
    Scene scene = Scene::from_json(json::parse(compose_json(none.dump())));
    int found = 0;
    for (const Item& item : scene.items)
        if (item.id == "cycle/Air conditioning/number/2") {
            ++found;
            CHECK(item.text == "2");
        }
    CHECK(found == 1);
}

TEST_CASE("Label texts and axis titles", "[compose]") {
    json data = load("compose_r290_ph.json");
    DiagramSpec spec = DiagramSpec::from_json(data.at("input").at("spec"));
    CHECK(axis_label(spec, "h") == "Specific enthalpy h / kJ/kg");
    CHECK(axis_label(spec, "p") == "Pressure p / bar");
    CHECK(label_text(spec, "T", 273.15) == "T=0 deg C");
    CHECK(label_text(spec, "Q", 0.4) == "x=0.4");
    CHECK(label_text(spec, "s", 1500.0) == "s=1.5 kJ/kg/K");
    CHECK_THROWS_AS(compose_json("{not json"), Error);
    CHECK_THROWS_AS(compose_json("{}"), Error);   // valid JSON, no spec
    CHECK_THROWS_AS(compose_json(R"({"spec": {"diagram": "ph"}, "domain": {"ranges_SI": {}},
                                     "cycles": [{"states": {"one": {}}}]})"), Error);   // state number not a number
    CHECK_THROWS_AS(compose(json{{"spec", {{"diagram", "ph"}}}, {"domain", {{"ranges_SI", json::object()}}}}), Error);
}

TEST_CASE("Labels of lines placed by saturation states, as in Python", "[compose]") {
    // The expected texts come from coolplot.compose.label_text for the same record
    json data = load("compose_r290_ph.json").at("input").at("spec");
    data["units"] = "IP";
    for (json& iso : data["isolines"]) {
        std::string key = iso.at("key").get<std::string>();
        if (key == "s") iso["anchor"] = {{"by", "T"}, {"step_SI", 10.0}, {"Q", 0.25}, {"range_SI", nullptr}, {"label", "saturation"}};
        if (key == "rho") iso["anchor"] = {{"by", "p"}, {"step_SI", 1e5}, {"Q", 0.0}, {"range_SI", nullptr}, {"label", "saturation"}};
        if (key == "T") iso["anchor"] = {{"by", "p"}, {"step_SI", 1e5}, {"Q", 1.0}, {"range_SI", nullptr}};   // label: the default
    }
    DiagramSpec spec = DiagramSpec::from_json(data);
    for (const IsolineSet& set : spec.isolines)
        if (set.key == "T") CHECK(set.anchor_label == "value");
    CHECK(label_text(spec, "s", 1000.0, true, 273.15) == "T(x=0.25)=32 deg F");
    CHECK(label_text(spec, "rho", 10.0, true, 2e5) == "p_sat,liq=29.01 psi");
    CHECK(label_text(spec, "T", 300.0, true, 2e5) == "T=80.33 deg F");   // labelled by value, the default
    CHECK(label_text(spec, "s", 1000.0) == "s=0.2388 Btu/lb/R");          // no saturation value given
    data["settings"]["labels"]["show_units"] = false;
    spec = DiagramSpec::from_json(data);
    CHECK(label_text(spec, "s", 1000.0, true, 273.15) == "T(x=0.25)=32");
    CHECK(label_text(spec, "rho", 10.0, true, 2e5) == "p_sat,liq=29.01");
    data["isolines"][0]["anchor"]["label"] = "both";
    CHECK_THROWS_AS(DiagramSpec::from_json(data), Error);
}
