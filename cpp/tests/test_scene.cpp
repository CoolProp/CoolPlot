// Mirrors tests/test_scene_render.py and tests/test_contracts.py for the scene.
#include <catch2/catch_all.hpp>

#include <cmath>
#include <fstream>
#include <limits>

#include "coolplot/scene.h"

using namespace coolplot;

namespace {

json load(const std::string& name) {
    std::ifstream in(std::string(COOLPLOT_TEST_DATA) + "/" + name);
    REQUIRE(in.good());
    return json::parse(in);
}

}  // namespace

TEST_CASE("The limits a backend draws", "[scene]") {
    CHECK(drawable_limits({0.0, 100.0}, true).lo == Catch::Approx(0.1));
    CHECK(drawable_limits({-5.0, 0.0}, true).hi == 10.0);
    CHECK(drawable_limits({5.0, 5.0}, true).lo == 0.5);
    CHECK(drawable_limits({5.0, 5.0}, false).lo == Catch::Approx(4.5));
    CHECK(drawable_limits({0.0, 0.0}, false).hi == 0.5);
    CHECK(drawable_limits({3.0, 1.0}, false).lo == 1.0);
}

TEST_CASE("Scene validation", "[scene]") {
    Item line;
    line.id = "a";
    line.x = {1.0, 2.0};
    line.y = {1.0};
    CHECK_THROWS_AS(line.validate(), Error);
    line.y = {1.0, 2.0};
    line.z_order = -1.0;
    CHECK_THROWS_AS(line.validate(), Error);
    Item text;
    text.type = ItemType::Text;
    text.id = "t";
    text.has_direction = true;
    CHECK_THROWS_AS(text.validate(), Error);
    text.direction_x = std::nan("");
    CHECK_THROWS_AS(text.validate(), Error);
    text.direction_x = 1.0;
    CHECK_NOTHROW(text.validate());
    CHECK_THROWS_AS(Scene::from_json({{"items", {{{"type", "circle"}, {"id", "c"}}}}}), Error);
    json twice = {{"items", {{{"type", "line"}, {"id", "a"}, {"x", {1.0}}, {"y", {1.0}}}, {{"type", "line"}, {"id", "a"}, {"x", {1.0}}, {"y", {1.0}}}}}};
    CHECK_THROWS_AS(Scene::from_json(twice), Error);
}

TEST_CASE("NaN becomes null and back, items compare by value", "[scene]") {
    Item line;
    line.id = "a";
    line.x = {0.0, std::nan(""), 2.0};
    line.y = {1.0, std::numeric_limits<double>::infinity(), 3.0};
    json record = line.to_json();
    CHECK(record.at("x").at(1).is_null());
    CHECK(record.at("y").at(1).is_null());
    Item again = Item::from_json(record);
    CHECK(std::isnan(again.x[1]));
    CHECK(std::isnan(again.y[1]));
    Item other = again;
    CHECK(items_equal(again, other));
    other.y[2] = 4.0;
    CHECK_FALSE(items_equal(again, other));
    Item text = Item::from_json({{"type", "text"}, {"id", "t"}, {"x", nullptr}, {"y", 1.0}, {"text", "nowhere"}});
    CHECK(std::isnan(text.text_x));
    CHECK(items_equal(text, Item::from_json(text.to_json())));
}

TEST_CASE("The conformance scene round-trips through JSON unchanged", "[scene]") {
    json data = load("conformance_scene.json");
    Scene scene = Scene::from_json(data);
    CHECK(scene.items.size() == data.at("items").size());
    json again = scene.to_json(false);  // the file holds the items in scene order
    CHECK(again == data);
    // The drawing order follows z order, then the scene order
    std::vector<size_t> order = scene.draw_order();
    for (size_t i = 1; i < order.size(); ++i) CHECK(scene.items[order[i - 1]].z_order <= scene.items[order[i]].z_order);
    CHECK(scene.items[order.back()].id == "line/on-top");
    // Legend entries collect the items that share a text, visible ones only
    auto entries = scene.legend_entries();
    REQUIRE(entries.size() == 2);
    CHECK(entries[0].first == "Solid <$1>");
    CHECK(entries[1].first == "Dashed");
    CHECK(entries[1].second.size() == 2);
}
