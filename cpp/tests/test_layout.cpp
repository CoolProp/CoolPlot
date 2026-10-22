// Mirrors tests/test_layout.py.
#include <catch2/catch_all.hpp>

#include <cmath>
#include <set>

#include "coolplot/layout.h"

using namespace coolplot;
using Catch::Matchers::WithinULP;

namespace {

Frame frame(double w = 400.0, double h = 300.0) {
    return Frame{{0.0, 10.0}, {0.0, 10.0}, false, false, w, h};
}

LabelRequest request(const std::string& id, const std::string& family, std::vector<double> x, std::vector<double> y,
                     const std::string& text = "T=25 deg C") {
    LabelRequest r;
    r.id = id;
    r.group = family + "/label";
    r.family = family;
    r.text = text;
    r.style.font.size_pt = 8.0;
    r.x = x;
    r.y = y;
    return r;
}

bool overlap(const Item& a, const Item& b, const Frame& f) {
    double ax = f.x_to_pt(a.text_x), ay = f.y_to_pt(a.text_y), bx = f.x_to_pt(b.text_x), by = f.y_to_pt(b.text_y);
    return std::hypot(ax - bx, ay - by) < 10.0;
}

}  // namespace

TEST_CASE("Visible pieces know their edges", "[layout]") {
    // A line entering from the left, leaving through the top; a NaN gap; a part fully inside
    std::vector<double> px = {-10.0, 50.0, 150.0, std::nan(""), 200.0, 250.0};
    std::vector<double> py = {50.0, 100.0, 350.0, std::nan(""), 100.0, 120.0};
    std::vector<Piece> pieces = visible_pieces(px, py, 400.0, 300.0);
    REQUIRE(pieces.size() == 2);
    CHECK(pieces[0].start_edge == "left");
    CHECK(pieces[0].end_edge == "top");
    CHECK(pieces[0].px.front() == Catch::Approx(0.0));
    CHECK(pieces[0].py.back() == Catch::Approx(300.0));
    CHECK(pieces[1].start_edge.empty());
    CHECK(pieces[1].end_edge.empty());
    CHECK(pieces[1].length() == Catch::Approx(std::hypot(50.0, 20.0)));
    // A point exactly on the frame counts as crossing it
    std::vector<Piece> on_edge = visible_pieces({0.0, 100.0}, {100.0, 100.0}, 400.0, 300.0);
    REQUIRE(on_edge.size() == 1);
    CHECK(on_edge[0].start_edge == "left");
    CHECK(visible_pieces({500.0, 600.0}, {10.0, 10.0}, 400.0, 300.0).empty());
    CHECK(visible_pieces({1.0}, {1.0}, 400.0, 300.0).empty());
}

TEST_CASE("Edge labels do not overlap and stay in the frame", "[layout]") {
    std::vector<LabelRequest> requests;
    for (int i = 0; i < 8; ++i) {
        double y = 1.0 + i * 0.6;  // lines close together, all leaving through the right edge
        requests.push_back(request("iso/T/" + std::to_string(i) + "/label", "T", {0.0, 5.0, 10.0}, {y, y + 0.5, y + 1.0}));
    }
    Frame f = frame();
    std::map<std::string, std::vector<std::string>> edges = {{"T", {"right", "top"}}};
    std::vector<Item> labels = place_edge_labels(requests, f, {}, 12.0, edges, {}, true);
    CHECK(labels.size() >= 4);
    for (size_t i = 0; i < labels.size(); ++i) {
        CHECK(labels[i].role == "isoline_label");
        CHECK(labels[i].text_x >= 0.0);
        CHECK(labels[i].text_x <= 10.0);
        CHECK(labels[i].has_direction);
        for (size_t j = 0; j < i; ++j) CHECK_FALSE(overlap(labels[i], labels[j], f));
    }
    // Deterministic and stable: the same inputs give the same labels, and
    // labels placed before keep their items while their spot stays free
    std::vector<Item> again = place_edge_labels(requests, f, {}, 12.0, edges, {}, true);
    REQUIRE(again.size() == labels.size());
    for (size_t i = 0; i < labels.size(); ++i) CHECK(items_equal(again[i], labels[i]));
    std::map<std::string, Item> previous;
    for (const Item& t : labels) previous[t.id] = t;
    std::vector<Item> kept = place_edge_labels(requests, f, {}, 12.0, edges, previous, true);
    REQUIRE(kept.size() == labels.size());
    for (size_t i = 0; i < labels.size(); ++i) CHECK(items_equal(kept[i], labels[i]));
}

TEST_CASE("The keep-out zone around a process and unconnected markers", "[layout]") {
    std::vector<LabelRequest> requests = {request("a", "T", {0.0, 10.0}, {5.0, 5.0})};
    Frame f = frame();
    std::map<std::string, std::vector<std::string>> edges = {{"T", {"left", "right"}}};
    std::vector<Item> free_labels = place_edge_labels(requests, f, {}, 12.0, edges, {}, true);
    REQUIRE(free_labels.size() == 1);
    CHECK(free_labels[0].text_x < 2.0);  // near the preferred left edge
    // A process along the whole line leaves no free spot
    KeepOut process{{0.0, 10.0}, {5.0, 5.0}, true};
    CHECK(place_edge_labels(requests, f, {process}, 12.0, edges, {}, true).empty());
    // Two markers at the ends are points, not a line: the label slides inward
    // past the marker's keep-out zone and the middle stays free
    KeepOut markers{{0.0, 10.0}, {5.0, 5.0}, false};
    std::vector<Item> with_markers = place_edge_labels(requests, f, {markers}, 12.0, edges, {}, true);
    REQUIRE(with_markers.size() == 1);
    CHECK(with_markers[0].text_x > free_labels[0].text_x);
    CHECK(with_markers[0].text_x < 3.0);
    // Without fallbacks the slid-in spot next to the edge is still allowed
    std::vector<Item> strict = place_edge_labels(requests, f, {markers}, 12.0, edges, {}, false);
    REQUIRE(strict.size() == 1);
    CHECK_THAT(strict[0].text_x, WithinULP(with_markers[0].text_x, 0));
}

TEST_CASE("Margin labels sit outside and do not collide", "[layout]") {
    std::vector<LabelRequest> requests;
    for (int i = 0; i < 6; ++i) {
        double x = 2.0 + i * 0.3;  // leaving through the top, close together
        requests.push_back(request("m" + std::to_string(i), "T", {x, x + 0.1}, {0.0, 10.0}, "T=" + std::to_string(i)));
    }
    Frame f = frame();
    std::vector<Item> labels = place_margin_labels(requests, f, {"top"});
    CHECK(labels.size() >= 2);
    CHECK(labels.size() < 6);
    for (const Item& t : labels) {
        CHECK_FALSE(t.clip);
        CHECK(t.text_y == Catch::Approx(10.0));
        CHECK_THAT(t.offset_y_pt, WithinULP(3.0, 0));
        CHECK(t.text_style.h_align == "left");
        CHECK(t.has_direction);
        CHECK_THAT(t.direction_y, WithinULP(1.0, 0));
    }
    CHECK(place_margin_labels(requests, f, {"left"}).empty());
}

TEST_CASE("An unusable frame gives no labels", "[layout]") {
    std::vector<LabelRequest> requests = {request("a", "T", {0.0, 10.0}, {5.0, 5.0})};
    Frame flat{{0.0, 10.0}, {0.0, 10.0}, false, false, 0.0, 300.0};
    CHECK(place_edge_labels(requests, flat, {}, 12.0, {}, {}, true).empty());
    CHECK(place_margin_labels(requests, flat, {"top"}).empty());
    Frame log_from_zero{{0.0, 10.0}, {0.0, 10.0}, true, false, 400.0, 300.0};
    CHECK_FALSE(log_from_zero.usable());
}

TEST_CASE("State numbers move clear of each other and of other markers", "[layout]") {
    Frame f = frame();
    std::vector<Item> numbers;
    for (int n = 1; n <= 3; ++n) {
        Item t;
        t.type = ItemType::Text;
        t.id = "n" + std::to_string(n);
        t.text = std::to_string(n);
        t.text_x = 5.0;
        t.text_y = 5.0 + 0.05 * n;  // almost on top of each other
        t.offset_x_pt = t.offset_y_pt = 4.5;
        t.text_style.font.size_pt = 8.0;
        numbers.push_back(t);
    }
    std::vector<Item> placed = place_state_numbers(numbers, f, {5.0, 5.05, 5.1}, {5.0, 5.05, 5.1});
    REQUIRE(placed.size() == 3);
    std::set<std::pair<double, double>> corners;
    for (const Item& t : placed) corners.insert({t.offset_x_pt, t.offset_y_pt});
    CHECK(corners.size() == 3);
    CHECK_THAT(placed[0].offset_x_pt, WithinULP(4.5, 0));
    CHECK(placed[0].text_style.h_align == "left");
}

TEST_CASE("A long state label turns to the side where it stays inside the frame", "[layout]") {
    Frame f = frame();  // 400 x 300 pt for 0..10 on both axes
    Item t;
    t.type = ItemType::Text;
    t.id = "n1";
    t.text = "1: a label far too long to fit to the right of its state";
    t.text_x = 9.5;  // 20 pt from the right edge
    t.text_y = 5.0;
    t.offset_x_pt = t.offset_y_pt = 4.5;
    t.text_style.font.size_pt = 8.0;
    std::vector<Item> placed = place_state_numbers({t}, f, {9.5}, {5.0});
    REQUIRE(placed.size() == 1);
    CHECK(placed[0].text_style.h_align == "right");
    CHECK_THAT(placed[0].offset_x_pt, WithinULP(-4.5, 0));
}
