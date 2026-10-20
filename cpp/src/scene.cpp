#include "coolplot/scene.h"

#include <algorithm>
#include <cmath>
#include <set>
#include <utility>

namespace coolplot {

namespace {

json number_or_null(double v) {
    return std::isfinite(v) ? json(v) : json(nullptr);
}

json numbers_or_null(const std::vector<double>& values) {
    json out = json::array();
    for (double v : values) out.push_back(number_or_null(v));
    return out;
}

double number_from(const json& v) {
    return v.is_null() ? std::nan("") : v.get<double>();
}

std::vector<double> numbers_from(const json& values) {
    std::vector<double> out;
    for (const json& v : values) out.push_back(number_from(v));
    return out;
}

bool finite_pair(double a, double b) {
    return std::isfinite(a) && std::isfinite(b);
}

}  // namespace

void Item::validate() const {
    if (!(z_order >= 0.0 && std::isfinite(z_order))) throw Error("Item '" + id + "': z_order has to be finite and >= 0.");
    if (type == ItemType::Text) {
        if (!finite_pair(offset_x_pt, offset_y_pt)) throw Error("Text '" + id + "': offset_pt has to be two finite numbers.");
        if (has_direction && (!finite_pair(direction_x, direction_y) || (direction_x == 0.0 && direction_y == 0.0)))
            throw Error("Text '" + id + "': direction has to be two finite numbers, not both zero, or None.");
        text_style.validate();
    } else {
        if (x.size() != y.size()) throw Error("Item '" + id + "': x and y need the same length.");
        if (type == ItemType::Line)
            line_style.validate();
        else
            marker_style.validate();
    }
}

json Item::to_json() const {
    json out = {{"type", type == ItemType::Line ? "line" : type == ItemType::Markers ? "markers" : "text"},
                {"id", id},
                {"group", group},
                {"role", role},
                {"legend", has_legend ? json(legend) : json(nullptr)},
                {"visible", visible},
                {"z_order", z_order}};
    if (type == ItemType::Text) {
        out["style"] = text_style.to_json();
        out["x"] = number_or_null(text_x);
        out["y"] = number_or_null(text_y);
        out["text"] = text;
        out["direction"] = has_direction ? json::array({direction_x, direction_y}) : json(nullptr);
        out["offset_pt"] = json::array({offset_x_pt, offset_y_pt});
        out["clip"] = clip;
    } else {
        out["style"] = type == ItemType::Line ? line_style.to_json() : marker_style.to_json();
        out["x"] = numbers_or_null(x);
        out["y"] = numbers_or_null(y);
    }
    return out;
}

Item Item::from_json(const json& data) {
    Item item;
    std::string type = data.at("type").get<std::string>();
    if (type == "line")
        item.type = ItemType::Line;
    else if (type == "markers")
        item.type = ItemType::Markers;
    else if (type == "text")
        item.type = ItemType::Text;
    else
        throw Error("Unknown item type '" + type + "', expected one of ['line', 'markers', 'text'].");
    item.id = data.at("id").get<std::string>();
    item.group = data.value("group", "");
    item.role = data.value("role", "");
    if (data.contains("legend") && !data.at("legend").is_null()) {
        item.has_legend = true;
        item.legend = data.at("legend").get<std::string>();
    }
    item.visible = data.value("visible", true);
    item.z_order = data.value("z_order", 1.0);
    json style = data.value("style", json::object());
    if (item.type == ItemType::Text) {
        item.text_style = TextStyle::from_json(style);
        item.text_x = number_from(data.at("x"));
        item.text_y = number_from(data.at("y"));
        item.text = data.at("text").get<std::string>();
        if (data.contains("direction") && !data.at("direction").is_null()) {
            item.has_direction = true;
            item.direction_x = data.at("direction").at(0).get<double>();
            item.direction_y = data.at("direction").at(1).get<double>();
        }
        if (data.contains("offset_pt")) {
            item.offset_x_pt = data.at("offset_pt").at(0).get<double>();
            item.offset_y_pt = data.at("offset_pt").at(1).get<double>();
        }
        item.clip = data.value("clip", true);
    } else {
        if (item.type == ItemType::Line)
            item.line_style = LineStyle::from_json(style);
        else
            item.marker_style = MarkerStyle::from_json(style);
        item.x = numbers_from(data.at("x"));
        item.y = numbers_from(data.at("y"));
    }
    item.validate();
    return item;
}

namespace {

bool same_numbers(const std::vector<double>& a, const std::vector<double>& b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i)
        if (!(a[i] == b[i] || (std::isnan(a[i]) && std::isnan(b[i])))) return false;
    return true;
}

bool same_number(double a, double b) {
    return a == b || (std::isnan(a) && std::isnan(b));
}

}  // namespace

bool items_equal(const Item& a, const Item& b) {
    if (a.type != b.type || a.id != b.id || a.group != b.group || a.role != b.role || a.has_legend != b.has_legend
        || (a.has_legend && a.legend != b.legend) || a.visible != b.visible || a.z_order != b.z_order)
        return false;
    if (a.type == ItemType::Text)
        return same_number(a.text_x, b.text_x) && same_number(a.text_y, b.text_y) && a.text == b.text && a.has_direction == b.has_direction
               && (!a.has_direction || (a.direction_x == b.direction_x && a.direction_y == b.direction_y)) && a.text_style == b.text_style
               && a.offset_x_pt == b.offset_x_pt && a.offset_y_pt == b.offset_y_pt && a.clip == b.clip;
    if (!same_numbers(a.x, b.x) || !same_numbers(a.y, b.y)) return false;
    return a.type == ItemType::Line ? a.line_style == b.line_style : a.marker_style == b.marker_style;
}

Range drawable_limits(Range limits, bool log) {
    double lo = std::min(limits.lo, limits.hi), hi = std::max(limits.lo, limits.hi);
    if (log) {
        if (!(hi > 0.0)) hi = 10.0;
        if (!(lo > 0.0)) lo = hi * 1e-3;
        if (lo == hi) {
            lo = lo / 10.0;
            hi = hi * 10.0;
        }
    } else if (lo == hi) {
        double pad = std::fabs(lo) * 0.1;
        if (pad == 0.0) pad = 0.5;
        lo -= pad;
        hi += pad;
    }
    return {lo, hi};
}

void AxesSpec::validate() const {
    if (tick_digits < 1 || tick_digits > 12) throw Error("AxesSpec: tick_digits has to be between 1 and 12.");
    if (has_x_limits && !finite_pair(x_limits.lo, x_limits.hi)) throw Error("AxesSpec: x_limits have to be finite.");
    if (has_y_limits && !finite_pair(y_limits.lo, y_limits.hi)) throw Error("AxesSpec: y_limits have to be finite.");
    style.validate();
}

bool AxesSpec::operator==(const AxesSpec& o) const {
    return x_label == o.x_label && y_label == o.y_label && x_log == o.x_log && y_log == o.y_log && has_x_limits == o.has_x_limits
           && (!has_x_limits || (x_limits.lo == o.x_limits.lo && x_limits.hi == o.x_limits.hi)) && has_y_limits == o.has_y_limits
           && (!has_y_limits || (y_limits.lo == o.y_limits.lo && y_limits.hi == o.y_limits.hi)) && title == o.title && style == o.style
           && tick_digits == o.tick_digits;
}

json AxesSpec::to_json() const {
    return json{{"x_label", x_label},
                {"y_label", y_label},
                {"x_log", x_log},
                {"y_log", y_log},
                {"x_limits", has_x_limits ? json::array({x_limits.lo, x_limits.hi}) : json(nullptr)},
                {"y_limits", has_y_limits ? json::array({y_limits.lo, y_limits.hi}) : json(nullptr)},
                {"title", title},
                {"style", style.to_json()},
                {"tick_digits", tick_digits}};
}

AxesSpec AxesSpec::from_json(const json& data) {
    AxesSpec a;
    a.x_label = data.value("x_label", "");
    a.y_label = data.value("y_label", "");
    a.x_log = data.value("x_log", false);
    a.y_log = data.value("y_log", false);
    for (int axis = 0; axis < 2; ++axis) {
        const char* name = axis == 0 ? "x_limits" : "y_limits";
        if (data.contains(name) && !data.at(name).is_null()) {
            double lo = data.at(name).at(0).get<double>(), hi = data.at(name).at(1).get<double>();
            Range limits = {std::min(lo, hi), std::max(lo, hi)};
            if (axis == 0) {
                a.has_x_limits = true;
                a.x_limits = limits;
            } else {
                a.has_y_limits = true;
                a.y_limits = limits;
            }
        }
    }
    a.title = data.value("title", "");
    if (data.contains("style")) a.style = AxesStyle::from_json(data.at("style"));
    a.tick_digits = data.value("tick_digits", 6);
    a.validate();
    return a;
}

std::vector<size_t> Scene::draw_order() const {
    std::vector<size_t> order(items.size());
    for (size_t i = 0; i < order.size(); ++i) order[i] = i;
    std::stable_sort(order.begin(), order.end(), [this](size_t a, size_t b) { return items[a].z_order < items[b].z_order; });
    return order;
}

std::vector<std::pair<std::string, std::vector<size_t>>> Scene::legend_entries() const {
    std::vector<std::pair<std::string, std::vector<size_t>>> entries;
    for (size_t i = 0; i < items.size(); ++i) {
        const Item& item = items[i];
        if (!item.has_legend || item.legend.empty() || !item.visible) continue;
        bool found = false;
        for (auto& entry : entries)
            if (entry.first == item.legend) {
                entry.second.push_back(i);
                found = true;
                break;
            }
        if (!found) entries.push_back({item.legend, {i}});
    }
    return entries;
}

const Item* Scene::find(const std::string& id) const {
    for (const Item& item : items)
        if (item.id == id) return &item;
    return nullptr;
}

json Scene::to_json(bool in_draw_order) const {
    json list = json::array();
    if (in_draw_order) {
        for (size_t i : draw_order()) list.push_back(items[i].to_json());
    } else {
        for (const Item& item : items) list.push_back(item.to_json());
    }
    return json{{"axes", axes.to_json()}, {"items", list}};
}

Scene Scene::from_json(const json& data) {
    Scene scene;
    if (data.contains("axes")) scene.axes = AxesSpec::from_json(data.at("axes"));
    if (data.contains("items")) {
        std::set<std::string> seen;  // a set, so that a large scene is not searched once per item
        for (const json& item : data.at("items")) {
            Item parsed = Item::from_json(item);
            if (!seen.insert(parsed.id).second) throw Error("Duplicate item id '" + parsed.id + "' in scene.");
            scene.items.push_back(std::move(parsed));
        }
    }
    return scene;
}

}  // namespace coolplot
