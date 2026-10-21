#include "coolplot/spec.h"

#include <algorithm>

namespace coolplot {

namespace {

const std::vector<std::string> EDGE_NAMES = {"top", "right", "bottom", "left"};

void check_edge(const std::string& edge) {
    if (std::find(EDGE_NAMES.begin(), EDGE_NAMES.end(), edge) == EDGE_NAMES.end()) throw Error("Unknown edge '" + edge + "'.");
}

std::map<std::string, double> state_from(const json& data) {
    std::map<std::string, double> out;
    for (auto it = data.begin(); it != data.end(); ++it) out[quantity_key(it.key())] = it.value().get<double>();
    return out;
}

}  // namespace

std::vector<std::string> LabelSettings::preferred_edges(const std::string& family, const std::vector<std::string>& fallback_edges) const {
    auto found = edges.find(family);
    return found == edges.end() ? fallback_edges : found->second;
}

LabelSettings LabelSettings::from_json(const json& data) {
    LabelSettings s;
    s.mode = data.value("mode", "edge");
    if (s.mode != "edge" && s.mode != "margin" && s.mode != "inline") throw Error("Unknown label mode '" + s.mode + "'.");
    s.keep_out_pt = data.value("keep_out_pt", 12.0);
    if (!(s.keep_out_pt >= 0.0)) throw Error("LabelSettings.keep_out_pt has to be zero or positive.");
    if (data.contains("edges")) {
        const json& edges = data.at("edges");
        if (edges.is_object()) {
            for (auto it = edges.begin(); it != edges.end(); ++it) s.edges[it.key()] = it.value().get<std::vector<std::string>>();
        } else {
            for (const json& pair : edges) s.edges[pair.at(0).get<std::string>()] = pair.at(1).get<std::vector<std::string>>();
        }
        for (const auto& kv : s.edges)
            for (const std::string& e : kv.second) check_edge(e);
    }
    if (data.contains("margin_edges")) s.margin_edges = data.at("margin_edges").get<std::vector<std::string>>();
    for (const std::string& e : s.margin_edges) check_edge(e);
    s.fallback = data.value("fallback", true);
    s.every = data.value("every", 1);
    if (s.every < 1) throw Error("LabelSettings.every has to be at least 1.");
    s.position = data.value("position", 0.5);
    if (!(s.position >= 0.0 && s.position <= 1.0)) throw Error("LabelSettings.position has to be between 0 and 1.");
    s.digits = data.value("digits", 4);
    s.show_units = data.value("show_units", true);
    s.tick_digits = data.value("tick_digits", 6);
    if (s.digits < 1 || s.digits > 12 || s.tick_digits < 1 || s.tick_digits > 12)
        throw Error("LabelSettings.digits and tick_digits have to be between 1 and 12.");
    return s;
}

PageSettings PageSettings::from_json(const json& data) {
    PageSettings p;
    p.width_pt = data.value("width_pt", 576.0);
    p.height_pt = data.value("height_pt", 432.0);
    p.font_scale = data.value("font_scale", 1.0);
    if (!(p.width_pt > 0.0 && p.height_pt > 0.0 && p.font_scale > 0.0)) throw Error("PageSettings values have to be positive.");
    return p;
}

Settings Settings::from_json(const json& data) {
    Settings s;
    const json& look = data.contains("look") ? data.at("look") : json("default");
    s.look = look.is_object() ? Theme::from_json(look) : get_theme(look.is_null() ? "default" : look.get<std::string>());
    if (data.contains("labels")) s.labels = LabelSettings::from_json(data.at("labels"));
    if (data.contains("page")) s.page = PageSettings::from_json(data.at("page"));
    return s;
}

json DiagramSpec::style_override(const std::string& key) const {
    auto found = style_overrides.find(quantity_key(key));
    return found == style_overrides.end() ? json::object() : found->second;
}

DiagramSpec DiagramSpec::from_json(const json& data) {
    DiagramSpec spec;
    spec.diagram = DiagramType::parse(data.value("diagram", "ph"));
    spec.units = UnitSystem::from_json(data.contains("units") ? data.at("units") : json("engineering"));
    spec.settings = Settings::from_json(data.value("settings", json::object()));
    for (const json& iso : data.value("isolines", json::array())) {
        IsolineSet set;
        set.key = quantity_key(iso.at("key").get<std::string>());
        set.labels = iso.value("labels", false);
        if (iso.contains("anchor") && !iso.at("anchor").is_null()) {
            const json& anchor = iso.at("anchor");
            set.has_anchor = true;
            set.anchor_by = quantity_key(anchor.value("by", "T"));
            if (set.anchor_by != "T" && set.anchor_by != "p") throw Error("Lines are placed by saturation 'T' or 'p', not '" + set.anchor_by + "'.");
            set.anchor_Q = anchor.value("Q", 1.0);
            set.anchor_label = anchor.value("label", "value");
            if (set.anchor_label != "saturation" && set.anchor_label != "value")
                throw Error("Unknown label '" + set.anchor_label + "' for lines placed by saturation states.");
        }
        spec.isolines.push_back(set);
    }
    for (const json& p : data.value("processes", json::array())) {
        ProcessSpec process;
        process.name = p.at("name").get<std::string>();
        for (const json& s : p.value("line_states", json::array())) process.line_states.push_back(state_from(s));
        for (const json& s : p.value("marker_states", json::array())) process.marker_states.push_back(state_from(s));
        if (p.contains("line_style") && !p.at("line_style").is_null()) {
            process.has_line_style = true;
            process.line_style = LineStyle::from_json(p.at("line_style"));
        }
        if (p.contains("marker_style") && !p.at("marker_style").is_null()) {
            process.has_marker_style = true;
            process.marker_style = MarkerStyle::from_json(p.at("marker_style"));
        }
        spec.processes.push_back(process);
    }
    for (const json& c : data.value("cycles", json::array())) {
        CycleSpec cycle;
        cycle.name = c.at("name").get<std::string>();
        cycle.numbers = c.value("numbers", true);
        // Python checks the labels; the core still refuses a malformed record instead of guessing
        const json labels = c.contains("labels") && !c.at("labels").is_null() ? c.at("labels") : json::array();
        if (!labels.is_array()) throw Error("cycle '" + cycle.name + "': labels have to be a list of [number, text]");
        for (const json& label : labels) {
            if (!label.is_array() || label.size() != 2 || !label.at(0).is_number_integer() || !label.at(1).is_string())
                throw Error("cycle '" + cycle.name + "': a label has to be [number, text], not " + label.dump());
            int number = label.at(0).get<int>();
            if (cycle.labels.count(number)) throw Error("cycle '" + cycle.name + "': state " + std::to_string(number) + " is labelled twice");
            cycle.labels[number] = label.at(1).get<std::string>();
        }
        if (c.contains("line_style") && !c.at("line_style").is_null()) {
            cycle.has_line_style = true;
            cycle.line_style = LineStyle::from_json(c.at("line_style"));
        }
        if (c.contains("marker_style") && !c.at("marker_style").is_null()) {
            cycle.has_marker_style = true;
            cycle.marker_style = MarkerStyle::from_json(c.at("marker_style"));
        }
        spec.cycles.push_back(cycle);
    }
    json overrides = data.value("style_overrides", json::object());
    for (auto it = overrides.begin(); it != overrides.end(); ++it) spec.style_overrides[quantity_key(it.key())] = it.value();
    if (data.contains("view_SI")) {
        const json& view = data.at("view_SI");
        if (view.size() > 0 && !view.at(0).is_null()) {
            spec.has_x_view = true;
            spec.x_view_SI = {view.at(0).at(0).get<double>(), view.at(0).at(1).get<double>()};
        }
        if (view.size() > 1 && !view.at(1).is_null()) {
            spec.has_y_view = true;
            spec.y_view_SI = {view.at(1).at(0).get<double>(), view.at(1).at(1).get<double>()};
        }
    }
    spec.title = data.value("title", "");
    return spec;
}

}  // namespace coolplot
