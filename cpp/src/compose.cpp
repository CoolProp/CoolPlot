#include "coolplot/compose.h"

#include <algorithm>
#include <cmath>
#include <set>

#include "coolplot/layout.h"

namespace coolplot {

const double Z_ISOLINE = 1.0, Z_SATURATION = 2.0, Z_LABEL = 4.0, Z_PROCESS = 5.0, Z_STATES = 6.0;

namespace {

const double NaN = std::nan("");

struct CurveRequest
{
    std::string item_id;
    std::string key;
    double value_SI;
    int points;
    bool labels;
    bool has_anchor = false;  ///< the line passes through a saturation state of its family's anchor
    double anchor_SI = 0.0;   ///< that saturation temperature or pressure
};

struct CurveInput
{
    CurveRequest request;
    std::vector<double> x;
    std::vector<double> y;
};

struct CycleInput
{
    std::map<int, std::map<std::string, double>> states;
    std::vector<std::vector<std::map<std::string, double>>> chains;
};

struct Domain
{
    std::map<std::string, Range> ranges_SI;

    Range range_SI(const std::string& key) const {
        auto found = ranges_SI.find(key);
        if (found == ranges_SI.end())
            throw Error("The range of '" + key + "' could not be determined for this fluid; give the isoline values or a range explicitly.");
        return found->second;
    }
};

std::vector<double> numbers_from(const json& values) {
    std::vector<double> out;
    for (const json& v : values) out.push_back(v.is_null() ? NaN : v.get<double>());
    return out;
}

std::map<std::string, double> state_from(const json& data) {
    std::map<std::string, double> out;
    for (auto it = data.begin(); it != data.end(); ++it) out[quantity_key(it.key())] = it.value().get<double>();
    return out;
}

std::vector<double> converted(const Unit& unit, const std::vector<double>& values_SI) {
    std::vector<double> out;
    for (double v : values_SI) out.push_back(unit.from_SI(v));
    return out;
}

/// (x_log, y_log): a quantity shown in a unit with an offset gets a linear axis.
std::pair<bool, bool> axis_scales(const DiagramSpec& spec) {
    return {spec.diagram.x_log() && is_zero(spec.units.at(spec.diagram.x).offset),
            spec.diagram.y_log() && is_zero(spec.units.at(spec.diagram.y).offset)};
}

/// Widen (lo, hi) so that all finite values lie inside, with a margin of pad times the span.
Range include(Range limits, const std::vector<double>& values, bool log, double pad = 0.04) {
    std::vector<double> kept;
    for (double v : values)
        if (std::isfinite(v) && (v > 0.0 || !log)) kept.push_back(v);
    if (kept.empty()) return limits;
    double lo = limits.lo, hi = limits.hi;
    double smallest = *std::min_element(kept.begin(), kept.end()), largest = *std::max_element(kept.begin(), kept.end());
    if (log) {
        double span = std::log10(hi) - std::log10(lo);
        lo = std::min(lo, smallest / std::pow(10.0, pad * span));
        hi = std::max(hi, largest * std::pow(10.0, pad * span));
    } else {
        double span = hi - lo;
        lo = std::min(lo, smallest - pad * span);
        hi = std::max(hi, largest + pad * span);
    }
    return {lo, hi};
}

/// (style, role, legend text, z order) of one isoline, from the theme and overrides.
struct Look
{
    LineStyle style;
    std::string role;
    std::string legend;
    double z_order;
};

Look isoline_look(const DiagramSpec& spec, const Theme& theme, const std::string& key, double value_SI) {
    const Family* family = spec.diagram.family(key);
    if (!family) throw Error("Lines of constant '" + key + "' cannot be drawn in a " + spec.diagram.name() + " diagram.");
    if (family->on_boundary()) {
        if (family->is_boundary_value(value_SI)) return {theme.saturation, "saturation", "Saturation", Z_SATURATION};
        return {theme.quality, "quality", spec.diagram.quantity_label(key), Z_ISOLINE};
    }
    std::vector<std::string> families;
    for (const Family& f : spec.diagram.families())
        if (!f.on_boundary()) families.push_back(f.key);
    LineStyle style = theme.isoline_style(key, families);
    json overrides = spec.style_override(key);
    if (!overrides.empty()) style = with_overrides(style, overrides);
    return {style, "isoline", spec.diagram.quantity_label(key), Z_ISOLINE};
}

Item line_item(const std::string& id, const std::string& group, const std::string& role, bool has_legend, const std::string& legend,
               const std::vector<double>& x, const std::vector<double>& y, const LineStyle& style, double z_order) {
    Item item;
    item.type = ItemType::Line;
    item.id = id;
    item.group = group;
    item.role = role;
    item.has_legend = has_legend;
    item.legend = legend;
    item.x = x;
    item.y = y;
    item.line_style = style;
    item.z_order = z_order;
    return item;
}

Item markers_item(const std::string& id, const std::string& group, const std::string& role, bool has_legend, const std::string& legend,
                  const std::vector<double>& x, const std::vector<double>& y, const MarkerStyle& style, double z_order) {
    Item item;
    item.type = ItemType::Markers;
    item.id = id;
    item.group = group;
    item.role = role;
    item.has_legend = has_legend;
    item.legend = legend;
    item.x = x;
    item.y = y;
    item.marker_style = style;
    item.z_order = z_order;
    return item;
}

}  // namespace

std::string axis_label(const DiagramSpec& spec, const std::string& key) {
    return spec.diagram.quantity_label(key) + " " + get_quantity(key).symbol + " / " + spec.units.at(key).label;
}

std::string label_text(const DiagramSpec& spec, const std::string& key, double value_SI, bool has_anchor, double anchor_SI) {
    const LabelSettings& labels = spec.settings.labels;
    // A line placed by saturation states shows its own value, unless its
    // family asks for the saturation state ("T_sat=0 deg C")
    const IsolineSet* anchored = nullptr;
    if (has_anchor)
        for (const IsolineSet& s : spec.isolines)
            if (s.key == key && s.has_anchor) anchored = &s;
    std::string shown_key = key, symbol = get_quantity(key).symbol;
    double shown = value_SI;
    if (anchored && anchored->anchor_label == "saturation") {
        shown_key = anchored->anchor_by;
        shown = anchor_SI;
        symbol = get_quantity(shown_key).symbol;
        if (anchored->anchor_Q == 1.0)
            symbol += "_sat";
        else if (anchored->anchor_Q == 0.0)
            symbol += "_sat,liq";
        else
            symbol += "(" + get_quantity("Q").symbol + "=" + labels.format_value(anchored->anchor_Q) + ")";
    }
    const Unit& unit = spec.units.at(shown_key);
    std::string text = symbol + "=" + labels.format_value(unit.from_SI(shown));
    if (labels.show_units && unit.label != "-" && !unit.label.empty()) text += " " + unit.label;
    return text;
}

std::pair<double, double> default_plot_size_pt(const DiagramSpec& spec) {
    return {0.72 * spec.settings.page.width_pt, 0.82 * spec.settings.page.height_pt};
}

namespace {

AxesSpec axes_spec(const DiagramSpec& spec, const Domain& domain, const Theme& theme, const std::vector<Item>& shown) {
    const DiagramType& diagram = spec.diagram;
    std::pair<bool, bool> logs = axis_scales(spec);
    AxesSpec axes;
    for (int axis = 0; axis < 2; ++axis) {
        const std::string& key = axis == 0 ? diagram.x : diagram.y;
        bool has_view = axis == 0 ? spec.has_x_view : spec.has_y_view;
        Range view = axis == 0 ? spec.x_view_SI : spec.y_view_SI;
        bool log = axis == 0 ? logs.first : logs.second;
        Range lo_hi = has_view ? view : domain.range_SI(key);
        const Unit& unit = spec.units.at(key);
        double a = unit.from_SI(lo_hi.lo), b = unit.from_SI(lo_hi.hi);
        lo_hi = {std::min(a, b), std::max(a, b)};
        if (!has_view) {
            std::vector<double> values;
            for (const Item& item : shown) {
                const std::vector<double>& v = axis == 0 ? item.x : item.y;
                values.insert(values.end(), v.begin(), v.end());
            }
            lo_hi = include(lo_hi, values, log);
        }
        // What the backends will draw, so that labels are laid out in that frame
        Range drawn = drawable_limits(lo_hi, log);
        if (axis == 0) {
            axes.has_x_limits = true;
            axes.x_limits = drawn;
        } else {
            axes.has_y_limits = true;
            axes.y_limits = drawn;
        }
    }
    axes.x_label = axis_label(spec, diagram.x);
    axes.y_label = axis_label(spec, diagram.y);
    axes.x_log = logs.first;
    axes.y_log = logs.second;
    axes.title = spec.title;
    axes.style = theme.axes;
    axes.tick_digits = spec.settings.labels.tick_digits;
    return axes;
}

std::vector<Item> isoline_items(const DiagramSpec& spec, const Theme& theme, const std::vector<CurveInput>& curves) {
    const Unit& ux = spec.units.at(spec.diagram.x);
    const Unit& uy = spec.units.at(spec.diagram.y);
    std::vector<Item> items;
    std::set<std::string> legends_given;
    for (const CurveInput& c : curves) {
        Look look = isoline_look(spec, theme, c.request.key, c.request.value_SI);
        std::string legend_key = (look.role == "saturation" || look.role == "quality") ? look.role : c.request.key;
        bool has_legend = !legends_given.count(legend_key);
        legends_given.insert(legend_key);
        items.push_back(line_item(c.request.item_id, "iso/" + c.request.key, look.role, has_legend, look.legend, converted(ux, c.x),
                                  converted(uy, c.y), look.style, look.z_order));
    }
    return items;
}

/// The lines that get a label, most important first.
std::vector<LabelRequest> label_requests(const DiagramSpec& spec, const Theme& theme, const std::vector<CurveInput>& curves,
                                         const std::vector<Item>& lines) {
    int every = spec.settings.labels.every;
    std::map<std::string, std::vector<std::pair<const CurveInput*, const Item*>>> by_family;
    std::vector<std::string> family_order;
    for (size_t i = 0; i < curves.size(); ++i) {
        const CurveRequest& request = curves[i].request;
        const Family* family = spec.diagram.family(request.key);
        if (!request.labels || (family && family->is_boundary_value(request.value_SI))) continue;
        if (!by_family.count(request.key)) family_order.push_back(request.key);
        by_family[request.key].push_back({&curves[i], &lines[i]});
    }
    // Quality lines first (they sit in the dome), then the families in the order of the spec
    auto spec_index = [&](const std::string& key) {
        for (size_t i = 0; i < spec.isolines.size(); ++i)
            if (spec.isolines[i].key == key) return static_cast<int>(i);
        return static_cast<int>(spec.isolines.size());
    };
    std::stable_sort(family_order.begin(), family_order.end(), [&](const std::string& a, const std::string& b) {
        bool a_inner = !spec.diagram.family(a)->on_boundary(), b_inner = !spec.diagram.family(b)->on_boundary();
        if (a_inner != b_inner) return !a_inner;
        return spec_index(a) < spec_index(b);
    });
    std::vector<LabelRequest> requests;
    for (const std::string& key : family_order) {
        const auto& members = by_family[key];
        for (size_t i = 0; i < members.size(); i += every) {
            const CurveInput* c = members[i].first;
            const Item* line = members[i].second;
            LabelRequest r;
            r.id = line->id + "/label";
            r.group = line->group + "/label";
            r.family = key;
            r.text = label_text(spec, key, c->request.value_SI, c->request.has_anchor, c->request.anchor_SI);
            r.style = theme.isoline_label;
            if (theme.isoline_label_color == "line" && line->line_style.color.present)
                r.style.color = line->line_style.color;   // the label in its line's colour
            r.x = line->x;
            r.y = line->y;
            requests.push_back(r);
        }
    }
    return requests;
}

/// Labels at Settings.labels.position along the visible part of each line.
std::vector<Item> inline_labels(const DiagramSpec& spec, const std::vector<LabelRequest>& requests, const AxesSpec& axes) {
    double x_lo = axes.x_limits.lo, x_hi = axes.x_limits.hi, y_lo = axes.y_limits.lo, y_hi = axes.y_limits.hi;
    double position = spec.settings.labels.position;
    std::vector<Item> labels;
    for (const LabelRequest& r : requests) {
        std::vector<size_t> inside;
        for (size_t i = 0; i < r.x.size(); ++i)
            if (std::isfinite(r.x[i]) && std::isfinite(r.y[i]) && r.x[i] >= x_lo && r.x[i] <= x_hi && r.y[i] >= y_lo && r.y[i] <= y_hi)
                inside.push_back(i);
        if (inside.size() < 3) continue;
        size_t pick = static_cast<size_t>(position * inside.size());
        size_t i = inside[std::min(pick, inside.size() - 1)];
        size_t i0 = i > 0 ? i - 1 : 0, i1 = std::min(i + 1, r.x.size() - 1);
        double dx = r.x[i1] - r.x[i0], dy = r.y[i1] - r.y[i0];
        Item t;
        t.type = ItemType::Text;
        t.id = r.id;
        t.group = r.group;
        t.role = "isoline_label";
        t.text_x = r.x[i];
        t.text_y = r.y[i];
        t.text = r.text;
        t.has_direction = std::isfinite(dx) && std::isfinite(dy);
        t.direction_x = dx;
        t.direction_y = dy;
        t.text_style = r.style;
        t.z_order = Z_LABEL;
        labels.push_back(t);
    }
    return labels;
}

std::vector<Item> labels_for(const DiagramSpec& spec, const std::vector<LabelRequest>& requests, const AxesSpec& axes,
                             const std::vector<KeepOut>& keep_out, std::pair<double, double> plot_size_pt,
                             const std::map<std::string, Item>& previous) {
    const LabelSettings& settings = spec.settings.labels;
    if (settings.mode == "inline") return inline_labels(spec, requests, axes);
    Frame frame{axes.x_limits, axes.y_limits, axes.x_log, axes.y_log, plot_size_pt.first, plot_size_pt.second};
    if (settings.mode == "margin") return place_margin_labels(requests, frame, settings.margin_edges);
    std::map<std::string, std::vector<std::string>> edges;
    for (const LabelRequest& r : requests)
        if (!edges.count(r.family)) edges[r.family] = settings.preferred_edges(r.family, spec.diagram.family(r.family)->edges);
    return place_edge_labels(requests, frame, keep_out, settings.keep_out_pt, edges, previous, settings.fallback);
}

std::vector<double> column(const std::vector<std::map<std::string, double>>& states, const std::string& key, const Unit& unit) {
    std::vector<double> out;
    for (const auto& s : states) {
        auto found = s.find(key);
        out.push_back(found == s.end() ? NaN : unit.from_SI(found->second));
    }
    return out;
}

std::vector<Item> process_items(const DiagramSpec& spec, const Theme& theme, const ProcessSpec& process, size_t index) {
    const Unit& ux = spec.units.at(spec.diagram.x);
    const Unit& uy = spec.units.at(spec.diagram.y);
    std::string group = "process/" + process.name;
    std::vector<Item> items;
    if (!process.line_states.empty())
        items.push_back(line_item(group + "/line", group, "process", true, process.name, column(process.line_states, spec.diagram.x, ux),
                                  column(process.line_states, spec.diagram.y, uy),
                                  process.has_line_style ? process.line_style : theme.process_style(index), Z_PROCESS));
    if (!process.marker_states.empty())
        items.push_back(markers_item(group + "/points", group, "state_points", true, process.name,
                                     column(process.marker_states, spec.diagram.x, ux), column(process.marker_states, spec.diagram.y, uy),
                                     process.has_marker_style ? process.marker_style : theme.state_point_style(index), Z_STATES));
    return items;
}

std::vector<Item> state_numbers(const std::string& group, const Theme& theme, const MarkerStyle& marker_style, const std::vector<int>& numbers,
                                const std::vector<double>& x, const std::vector<double>& y) {
    double offset = 0.5 * marker_style.size_pt + 1.5;
    TextStyle number_style = theme.state_number;
    number_style.h_align = "left";
    number_style.v_align = "bottom";
    std::vector<Item> out;
    for (size_t i = 0; i < numbers.size(); ++i) {
        Item t;
        t.type = ItemType::Text;
        t.id = group + "/number/" + std::to_string(numbers[i]);
        t.group = group + "/numbers";
        t.role = "state_number";
        t.text_x = x[i];
        t.text_y = y[i];
        t.text = std::to_string(numbers[i]);
        t.offset_x_pt = offset;
        t.offset_y_pt = offset;
        t.text_style = number_style;
        t.z_order = Z_STATES + 1.0;
        out.push_back(t);
    }
    return out;
}

std::vector<Item> cycle_items(const DiagramSpec& spec, const Theme& theme, const CycleSpec& cycle, const CycleInput& computed, size_t index) {
    const Unit& ux = spec.units.at(spec.diagram.x);
    const Unit& uy = spec.units.at(spec.diagram.y);
    std::string group = "cycle/" + cycle.name;
    LineStyle line_style = cycle.has_line_style ? cycle.line_style : theme.process_style(index);
    MarkerStyle marker_style = cycle.has_marker_style ? cycle.marker_style : theme.state_point_style(index);
    std::vector<Item> items;
    for (size_t i = 0; i < computed.chains.size(); ++i)
        items.push_back(line_item(group + "/loop/" + std::to_string(i), group, "cycle", i == 0, cycle.name,
                                  column(computed.chains[i], spec.diagram.x, ux), column(computed.chains[i], spec.diagram.y, uy), line_style,
                                  Z_PROCESS));
    std::vector<int> numbers;
    std::vector<std::map<std::string, double>> states;
    for (const auto& kv : computed.states) {  // std::map keeps them in ascending state number
        numbers.push_back(kv.first);
        states.push_back(kv.second);
    }
    std::vector<double> x = column(states, spec.diagram.x, ux), y = column(states, spec.diagram.y, uy);
    items.push_back(markers_item(group + "/states", group, "state_points", true, cycle.name, x, y, marker_style, Z_STATES));
    if (cycle.numbers) {
        std::vector<Item> texts = state_numbers(group, theme, marker_style, numbers, x, y);
        items.insert(items.end(), texts.begin(), texts.end());
    }
    return items;
}

std::vector<Item> overlay_items(const DiagramSpec& spec, const Theme& theme, const std::vector<CycleInput>& cycles) {
    std::vector<Item> parts;
    for (size_t i = 0; i < spec.processes.size(); ++i) {
        std::vector<Item> items = process_items(spec, theme, spec.processes[i], i);
        parts.insert(parts.end(), items.begin(), items.end());
    }
    for (size_t i = 0; i < spec.cycles.size() && i < cycles.size(); ++i) {
        std::vector<Item> items = cycle_items(spec, theme, spec.cycles[i], cycles[i], spec.processes.size() + i);
        parts.insert(parts.end(), items.begin(), items.end());
    }
    return parts;
}

std::vector<Item> placed_state_numbers(const std::vector<Item>& parts, const Frame& frame) {
    std::vector<Item> numbers;
    std::vector<double> mx, my;
    for (const Item& p : parts) {
        if (p.type == ItemType::Text) numbers.push_back(p);
        if (p.type == ItemType::Markers) {
            mx.insert(mx.end(), p.x.begin(), p.x.end());
            my.insert(my.end(), p.y.begin(), p.y.end());
        }
    }
    if (numbers.empty()) return parts;
    std::map<std::string, Item> moved;
    for (const Item& t : place_state_numbers(numbers, frame, mx, my)) moved[t.id] = t;
    std::vector<Item> out;
    for (const Item& p : parts) {
        auto found = moved.find(p.id);
        out.push_back(found != moved.end() && p.type == ItemType::Text ? found->second : p);
    }
    return out;
}

}  // namespace

Scene compose(const json& input) {
    DiagramSpec spec = DiagramSpec::from_json(input.at("spec"));
    Domain domain;
    const json& ranges = input.at("domain").at("ranges_SI");
    for (auto it = ranges.begin(); it != ranges.end(); ++it)
        domain.ranges_SI[quantity_key(it.key())] = {it.value().at(0).get<double>(), it.value().at(1).get<double>()};
    std::vector<CurveInput> curves;
    for (const json& entry : input.value("curves", json::array())) {
        const json& r = entry.at("request");
        CurveInput c;
        c.request = {r.at("item_id").get<std::string>(), quantity_key(r.at("key").get<std::string>()), r.at("value_SI").get<double>(),
                     r.value("points", 250), r.value("labels", false)};
        if (r.contains("anchor_SI") && !r.at("anchor_SI").is_null()) {
            c.request.has_anchor = true;
            c.request.anchor_SI = r.at("anchor_SI").get<double>();
        }
        c.x = numbers_from(entry.at("curve").at("x"));
        c.y = numbers_from(entry.at("curve").at("y"));
        if (c.x.size() != c.y.size()) throw Error("Curve '" + c.request.item_id + "': x and y need the same length.");
        curves.push_back(c);
    }
    std::vector<CycleInput> cycles;
    for (const json& entry : input.value("cycles", json::array())) {
        CycleInput c;
        const json& states = entry.at("states");
        for (auto it = states.begin(); it != states.end(); ++it) c.states[std::stoi(it.key())] = state_from(it.value());
        for (const json& chain : entry.value("chains", json::array())) {
            std::vector<std::map<std::string, double>> parsed;
            for (const json& s : chain) parsed.push_back(state_from(s));
            c.chains.push_back(parsed);
        }
        cycles.push_back(c);
    }
    std::map<std::string, Item> previous;
    if (input.contains("previous_labels") && !input.at("previous_labels").is_null())
        for (const json& t : input.at("previous_labels")) {
            Item item = Item::from_json(t);
            if (item.role == "isoline_label") previous[item.id] = item;
        }

    Theme theme = spec.settings.look.scaled(spec.settings.page.font_scale);
    std::vector<Item> process_parts = overlay_items(spec, theme, cycles);
    std::vector<Item> drawn;
    std::vector<KeepOut> keep_out;
    for (const Item& p : process_parts)
        if (p.type != ItemType::Text) {
            drawn.push_back(p);
            keep_out.push_back({p.x, p.y, p.type == ItemType::Line});
        }
    AxesSpec axes = axes_spec(spec, domain, theme, drawn);
    std::pair<double, double> size = default_plot_size_pt(spec);
    if (input.contains("plot_size_pt") && !input.at("plot_size_pt").is_null())
        size = {input.at("plot_size_pt").at(0).get<double>(), input.at("plot_size_pt").at(1).get<double>()};
    Frame frame{axes.x_limits, axes.y_limits, axes.x_log, axes.y_log, size.first, size.second};
    process_parts = placed_state_numbers(process_parts, frame);
    std::vector<Item> lines = isoline_items(spec, theme, curves);
    Scene scene;
    scene.axes = axes;
    scene.items = lines;
    std::vector<LabelRequest> requests = label_requests(spec, theme, curves, lines);
    if (!requests.empty()) {
        std::vector<Item> labels = labels_for(spec, requests, axes, keep_out, size, previous);
        scene.items.insert(scene.items.end(), labels.begin(), labels.end());
    }
    scene.items.insert(scene.items.end(), process_parts.begin(), process_parts.end());
    return scene;
}

std::string compose_json(const std::string& input_text) {
    json input;
    try {
        input = json::parse(input_text);
    } catch (const std::exception& e) {
        throw Error(std::string("The compose record is not valid JSON: ") + e.what());
    }
    // In scene order, not drawing order: the order the composer made the
    // items in carries more (the legend follows it), and sorting by z order
    // gives the drawing order back. A field that is missing or has the wrong
    // type throws a json::exception, a state number that is not a number an
    // exception of std::stoi; all of them leave here as Error, as documented.
    try {
        return compose(input).to_json(false).dump();
    } catch (const Error&) {
        throw;
    } catch (const json::exception& e) {
        throw Error(std::string("The compose record is not valid: ") + e.what());
    } catch (const std::invalid_argument& e) {
        throw Error(std::string("The compose record is not valid: ") + e.what());
    } catch (const std::out_of_range& e) {
        throw Error(std::string("The compose record is not valid: ") + e.what());
    }
}

}  // namespace coolplot
