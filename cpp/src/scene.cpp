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
        if (has_direction && (!finite_pair(direction_x, direction_y) || (is_zero(direction_x) && is_zero(direction_y))))
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

// For the redraw decision a NaN (a gap in a line) equals a NaN
bool same_or_both_nan(double a, double b) {
    return (std::isnan(a) && std::isnan(b)) || same_number(a, b);
}

bool same_or_both_nan(const std::vector<double>& a, const std::vector<double>& b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i)
        if (!same_or_both_nan(a[i], b[i])) return false;
    return true;
}

}  // namespace

bool items_equal(const Item& a, const Item& b) {
    if (a.type != b.type || a.id != b.id || a.group != b.group || a.role != b.role || a.has_legend != b.has_legend
        || (a.has_legend && a.legend != b.legend) || a.visible != b.visible || !same_number(a.z_order, b.z_order))
        return false;
    if (a.type == ItemType::Text)
        return same_or_both_nan(a.text_x, b.text_x) && same_or_both_nan(a.text_y, b.text_y) && a.text == b.text
               && a.has_direction == b.has_direction
               && (!a.has_direction || (same_number(a.direction_x, b.direction_x) && same_number(a.direction_y, b.direction_y)))
               && a.text_style == b.text_style && same_number(a.offset_x_pt, b.offset_x_pt) && same_number(a.offset_y_pt, b.offset_y_pt)
               && a.clip == b.clip;
    if (!same_or_both_nan(a.x, b.x) || !same_or_both_nan(a.y, b.y)) return false;
    return a.type == ItemType::Line ? a.line_style == b.line_style : a.marker_style == b.marker_style;
}

Range drawable_limits(Range limits, bool log) {
    double lo = std::min(limits.lo, limits.hi), hi = std::max(limits.lo, limits.hi);
    if (log) {
        if (!(hi > 0.0)) hi = 10.0;
        if (!(lo > 0.0)) lo = hi * 1e-3;
        if (same_number(lo, hi)) {
            lo = lo / 10.0;
            hi = hi * 10.0;
        }
    } else if (same_number(lo, hi)) {
        double pad = std::fabs(lo) * 0.1;
        if (is_zero(pad)) pad = 0.5;
        lo -= pad;
        hi += pad;
    }
    return {lo, hi};
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

const char* const BADGE_CORNERS[4] = {"upper left", "upper right", "lower left", "lower right"};
const double BADGE_LINE_HEIGHT = 1.25;
const double BADGE_BASELINE = 0.95;

double Badge::line_height_pt() const {
    return BADGE_LINE_HEIGHT * text.font.size_pt;
}

std::pair<double, double> Badge::size_pt() const {
    double text_w = 0.0;
    for (const std::string& line : lines) text_w = std::max(text_w, text_width_pt(line, text.font.size_pt));
    double content_h = static_cast<double>(lines.size()) * line_height_pt();
    return {text_w + 2.0 * padding_pt, content_h + 2.0 * padding_pt};
}

void Badge::validate() const {
    if (std::find(std::begin(BADGE_CORNERS), std::end(BADGE_CORNERS), location) == std::end(BADGE_CORNERS))
        throw Error("Badge: location has to be one of upper left, upper right, lower left, lower right, not '" + location + "'.");
    for (double v : {logo_width_pt, frame_width_pt, padding_pt, gap_pt, inset_pt})
        if (!(v >= 0.0 && std::isfinite(v))) throw Error("Badge: sizes have to be finite and >= 0.");
    if (!(background_alpha >= 0.0 && background_alpha <= 1.0)) throw Error("Badge: background_alpha has to be between 0 and 1.");
    text.validate();
}

bool Badge::operator==(const Badge& o) const {
    return location == o.location && same_number(logo_width_pt, o.logo_width_pt) && lines == o.lines && text == o.text
           && background == o.background && same_number(background_alpha, o.background_alpha) && frame_color == o.frame_color
           && same_number(frame_width_pt, o.frame_width_pt) && same_number(padding_pt, o.padding_pt) && same_number(gap_pt, o.gap_pt)
           && same_number(inset_pt, o.inset_pt);
}

json Badge::to_json() const {
    return json{{"location", location},
                {"logo", json::array()},
                {"logo_width_pt", logo_width_pt},
                {"lines", lines},
                {"text", text.to_json()},
                {"background", background.present ? json(background.hex) : json(nullptr)},
                {"background_alpha", background_alpha},
                {"frame_color", frame_color.present ? json(frame_color.hex) : json(nullptr)},
                {"frame_width_pt", frame_width_pt},
                {"padding_pt", padding_pt},
                {"gap_pt", gap_pt},
                {"inset_pt", inset_pt}};
}

Badge Badge::from_json(const json& data) {
    if (!data.value("logo", json::array()).empty())
        throw Error("coolplot-core does not draw a badge logo; the Python writers do.");
    Badge b;
    b.location = data.value("location", "lower right");
    b.logo_width_pt = data.value("logo_width_pt", 72.0);
    // As coolplot.scene.Badge: a line holding line breaks is several drawn lines
    for (const json& entry : data.value("lines", json::array())) {
        std::string line = entry.get<std::string>(), part;
        for (size_t i = 0; i <= line.size(); ++i) {
            if (i == line.size() || line[i] == '\n') {
                if (!part.empty() && part.back() == '\r') part.pop_back();
                b.lines.push_back(part);
                part.clear();
            } else {
                part += line[i];
            }
        }
    }
    if (data.contains("text")) b.text = TextStyle::from_json(data.at("text"));
    if (data.contains("background")) b.background = opaque_color(data.at("background"), "Badge", "background");
    b.background_alpha = data.value("background_alpha", 0.85);
    if (data.contains("frame_color")) b.frame_color = opaque_color(data.at("frame_color"), "Badge", "frame_color");
    b.frame_width_pt = data.value("frame_width_pt", 0.5);
    b.padding_pt = data.value("padding_pt", 4.0);
    b.gap_pt = data.value("gap_pt", 3.0);
    b.inset_pt = data.value("inset_pt", 6.0);
    b.validate();
    return b;
}

void AxesSpec::validate() const {
    if (has_badge) badge.validate();
    if (tick_digits < 1 || tick_digits > 12) throw Error("AxesSpec: tick_digits has to be between 1 and 12.");
    if (has_x_limits && !finite_pair(x_limits.lo, x_limits.hi)) throw Error("AxesSpec: x_limits have to be finite.");
    if (has_y_limits && !finite_pair(y_limits.lo, y_limits.hi)) throw Error("AxesSpec: y_limits have to be finite.");
    style.validate();
}

bool AxesSpec::operator==(const AxesSpec& o) const {
    return x_label == o.x_label && y_label == o.y_label && x_log == o.x_log && y_log == o.y_log && has_x_limits == o.has_x_limits
           && (!has_x_limits || (same_number(x_limits.lo, o.x_limits.lo) && same_number(x_limits.hi, o.x_limits.hi)))
           && has_y_limits == o.has_y_limits
           && (!has_y_limits || (same_number(y_limits.lo, o.y_limits.lo) && same_number(y_limits.hi, o.y_limits.hi))) && title == o.title
           && style == o.style
           && tick_digits == o.tick_digits && has_badge == o.has_badge && (!has_badge || badge == o.badge);
}

json AxesSpec::to_json() const {
    json out{{"x_label", x_label},
                {"y_label", y_label},
                {"x_log", x_log},
                {"y_log", y_log},
                {"x_limits", has_x_limits ? json::array({x_limits.lo, x_limits.hi}) : json(nullptr)},
                {"y_limits", has_y_limits ? json::array({y_limits.lo, y_limits.hi}) : json(nullptr)},
                {"title", title},
                {"style", style.to_json()},
                {"tick_digits", tick_digits}};
    // Only written when there is one, so the record of a chart without badge is the same as before 1.2
    if (has_badge) out["badge"] = badge.to_json();
    return out;
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
    // The composer gives an "auto" legend its corner; a scene made without it gets the upper right one
    if (a.style.legend.location == "auto") a.style.legend.location = "upper right";
    a.tick_digits = data.value("tick_digits", 6);
    if (data.contains("badge") && !data.at("badge").is_null()) {
        a.has_badge = true;
        a.badge = Badge::from_json(data.at("badge"));
    }
    if (data.contains("watermark") && !data.at("watermark").is_null())
        throw Error("coolplot-core does not draw a watermark; the Python writers do.");
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
