#include "coolplot/style.h"

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace coolplot {

// ---------------------------------------------------------------------------
// Colours
// ---------------------------------------------------------------------------

namespace {

/// The 148 named colours of CSS Color Module Level 4.
const std::map<std::string, std::string>& css_colors() {
    static const std::map<std::string, std::string> table = {
      {"aliceblue", "#f0f8ff"}, {"antiquewhite", "#faebd7"}, {"aqua", "#00ffff"}, {"aquamarine", "#7fffd4"},
      {"azure", "#f0ffff"}, {"beige", "#f5f5dc"}, {"bisque", "#ffe4c4"}, {"black", "#000000"},
      {"blanchedalmond", "#ffebcd"}, {"blue", "#0000ff"}, {"blueviolet", "#8a2be2"}, {"brown", "#a52a2a"},
      {"burlywood", "#deb887"}, {"cadetblue", "#5f9ea0"}, {"chartreuse", "#7fff00"},
      {"chocolate", "#d2691e"}, {"coral", "#ff7f50"}, {"cornflowerblue", "#6495ed"}, {"cornsilk", "#fff8dc"},
      {"crimson", "#dc143c"}, {"cyan", "#00ffff"}, {"darkblue", "#00008b"}, {"darkcyan", "#008b8b"},
      {"darkgoldenrod", "#b8860b"}, {"darkgray", "#a9a9a9"}, {"darkgreen", "#006400"},
      {"darkgrey", "#a9a9a9"}, {"darkkhaki", "#bdb76b"}, {"darkmagenta", "#8b008b"},
      {"darkolivegreen", "#556b2f"}, {"darkorange", "#ff8c00"}, {"darkorchid", "#9932cc"},
      {"darkred", "#8b0000"}, {"darksalmon", "#e9967a"}, {"darkseagreen", "#8fbc8f"},
      {"darkslateblue", "#483d8b"}, {"darkslategray", "#2f4f4f"}, {"darkslategrey", "#2f4f4f"},
      {"darkturquoise", "#00ced1"}, {"darkviolet", "#9400d3"}, {"deeppink", "#ff1493"},
      {"deepskyblue", "#00bfff"}, {"dimgray", "#696969"}, {"dimgrey", "#696969"}, {"dodgerblue", "#1e90ff"},
      {"firebrick", "#b22222"}, {"floralwhite", "#fffaf0"}, {"forestgreen", "#228b22"},
      {"fuchsia", "#ff00ff"}, {"gainsboro", "#dcdcdc"}, {"ghostwhite", "#f8f8ff"}, {"gold", "#ffd700"},
      {"goldenrod", "#daa520"}, {"gray", "#808080"}, {"green", "#008000"}, {"greenyellow", "#adff2f"},
      {"grey", "#808080"}, {"honeydew", "#f0fff0"}, {"hotpink", "#ff69b4"}, {"indianred", "#cd5c5c"},
      {"indigo", "#4b0082"}, {"ivory", "#fffff0"}, {"khaki", "#f0e68c"}, {"lavender", "#e6e6fa"},
      {"lavenderblush", "#fff0f5"}, {"lawngreen", "#7cfc00"}, {"lemonchiffon", "#fffacd"},
      {"lightblue", "#add8e6"}, {"lightcoral", "#f08080"}, {"lightcyan", "#e0ffff"},
      {"lightgoldenrodyellow", "#fafad2"}, {"lightgray", "#d3d3d3"}, {"lightgreen", "#90ee90"},
      {"lightgrey", "#d3d3d3"}, {"lightpink", "#ffb6c1"}, {"lightsalmon", "#ffa07a"},
      {"lightseagreen", "#20b2aa"}, {"lightskyblue", "#87cefa"}, {"lightslategray", "#778899"},
      {"lightslategrey", "#778899"}, {"lightsteelblue", "#b0c4de"}, {"lightyellow", "#ffffe0"},
      {"lime", "#00ff00"}, {"limegreen", "#32cd32"}, {"linen", "#faf0e6"}, {"magenta", "#ff00ff"},
      {"maroon", "#800000"}, {"mediumaquamarine", "#66cdaa"}, {"mediumblue", "#0000cd"},
      {"mediumorchid", "#ba55d3"}, {"mediumpurple", "#9370db"}, {"mediumseagreen", "#3cb371"},
      {"mediumslateblue", "#7b68ee"}, {"mediumspringgreen", "#00fa9a"}, {"mediumturquoise", "#48d1cc"},
      {"mediumvioletred", "#c71585"}, {"midnightblue", "#191970"}, {"mintcream", "#f5fffa"},
      {"mistyrose", "#ffe4e1"}, {"moccasin", "#ffe4b5"}, {"navajowhite", "#ffdead"}, {"navy", "#000080"},
      {"oldlace", "#fdf5e6"}, {"olive", "#808000"}, {"olivedrab", "#6b8e23"}, {"orange", "#ffa500"},
      {"orangered", "#ff4500"}, {"orchid", "#da70d6"}, {"palegoldenrod", "#eee8aa"},
      {"palegreen", "#98fb98"}, {"paleturquoise", "#afeeee"}, {"palevioletred", "#db7093"},
      {"papayawhip", "#ffefd5"}, {"peachpuff", "#ffdab9"}, {"peru", "#cd853f"}, {"pink", "#ffc0cb"},
      {"plum", "#dda0dd"}, {"powderblue", "#b0e0e6"}, {"purple", "#800080"}, {"rebeccapurple", "#663399"},
      {"red", "#ff0000"}, {"rosybrown", "#bc8f8f"}, {"royalblue", "#4169e1"}, {"saddlebrown", "#8b4513"},
      {"salmon", "#fa8072"}, {"sandybrown", "#f4a460"}, {"seagreen", "#2e8b57"}, {"seashell", "#fff5ee"},
      {"sienna", "#a0522d"}, {"silver", "#c0c0c0"}, {"skyblue", "#87ceeb"}, {"slateblue", "#6a5acd"},
      {"slategray", "#708090"}, {"slategrey", "#708090"}, {"snow", "#fffafa"}, {"springgreen", "#00ff7f"},
      {"steelblue", "#4682b4"}, {"tan", "#d2b48c"}, {"teal", "#008080"}, {"thistle", "#d8bfd8"},
      {"tomato", "#ff6347"}, {"turquoise", "#40e0d0"}, {"violet", "#ee82ee"}, {"wheat", "#f5deb3"},
      {"white", "#ffffff"}, {"whitesmoke", "#f5f5f5"}, {"yellow", "#ffff00"}, {"yellowgreen", "#9acd32"},
    };
    return table;
}

std::string trimmed_lower(const std::string& text) {
    size_t a = text.find_first_not_of(" \t\r\n"), b = text.find_last_not_of(" \t\r\n");
    std::string out = a == std::string::npos ? "" : text.substr(a, b - a + 1);
    for (char& c : out) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return out;
}

bool all_hex(const std::string& digits) {
    for (char c : digits)
        if (!std::isxdigit(static_cast<unsigned char>(c))) return false;
    return true;
}

void check_alpha(double alpha, const std::string& owner) {
    if (!(alpha >= 0.0 && alpha <= 1.0)) throw Error(owner + ": alpha has to be between 0 and 1, not " + format_number(alpha) + ".");
}

void check_length(double value, const std::string& owner, const std::string& name) {
    if (!(value >= 0.0 && std::isfinite(value)))
        throw Error(owner + ": " + name + " has to be a finite length >= 0, not " + format_number(value) + ".");
}

}  // namespace

std::pair<Color, double> parse_color(const json& value) {
    if (value.is_null()) return {Color::none(), 0.0};
    if (!value.is_string()) throw Error("A colour has to be a CSS colour name or #rrggbb, not " + value.dump() + ".");
    std::string text = trimmed_lower(value.get<std::string>());
    if (text == "none" || text == "transparent") return {Color::none(), 0.0};
    auto named = css_colors().find(text);
    if (named != css_colors().end()) return {Color::of(named->second), 1.0};
    if (text.size() < 2 || text[0] != '#') throw Error("Unknown colour '" + value.get<std::string>() + "'; use a CSS colour name or #rrggbb.");
    std::string digits = text.substr(1);
    if (!(digits.size() == 3 || digits.size() == 4 || digits.size() == 6 || digits.size() == 8) || !all_hex(digits))
        throw Error("Unknown colour '" + value.get<std::string>() + "'; use a CSS colour name or #rrggbb.");
    if (digits.size() <= 4) {
        std::string doubled;
        for (char c : digits) doubled += std::string(2, c);
        digits = doubled;
    }
    double alpha = 1.0;
    if (digits.size() == 8) {
        alpha = std::stoi(digits.substr(6), nullptr, 16) / 255.0;
        digits = digits.substr(0, 6);
    }
    return {Color::of("#" + digits), alpha};
}

Color opaque_color(const json& value, const std::string& owner, const std::string& field) {
    std::pair<Color, double> parsed = parse_color(value);
    if (!parsed.first.present || parsed.second == 0.0) return Color::none();
    if (parsed.second < 1.0)
        throw Error(owner + ": " + field + " cannot be partly transparent (" + value.dump() + "); this field has no alpha of its own.");
    return parsed.first;
}

// ---------------------------------------------------------------------------
// Dashes
// ---------------------------------------------------------------------------

namespace {

const std::map<std::string, std::vector<double>>& dash_names() {
    static const std::map<std::string, std::vector<double>> table = {
      {"solid", {}},
      {"dashed", {3.7, 1.6}},
      {"dotted", {1.0, 1.65}},
      {"dashdot", {6.4, 1.6, 1.0, 1.6}},
    };
    return table;
}

/// Python's round(value, 6)
double round6(double value) {
    return std::round(value * 1e6) / 1e6;
}

}  // namespace

json Dash::to_json() const {
    if (!name.empty()) return name;
    return json(lengths);
}

Dash Dash::from_json(const json& value) {
    Dash dash;
    if (value.is_string()) {
        dash.name = value.get<std::string>();
        if (dash_names().find(dash.name) == dash_names().end()) throw Error("Unknown dash '" + dash.name + "'.");
        return dash;
    }
    if (!value.is_array()) throw Error("A dash is a name or a list of lengths in points, not " + value.dump() + ".");
    double sum = 0.0;
    for (const json& v : value) {
        if (!v.is_number()) throw Error("A dash tuple needs an even number of finite, non-negative lengths.");
        double length = v.get<double>();
        if (!(length >= 0.0 && std::isfinite(length))) throw Error("A dash tuple needs an even number of finite, non-negative lengths.");
        dash.lengths.push_back(length);
        sum += length;
    }
    if (dash.lengths.size() % 2 != 0 || (!dash.lengths.empty() && sum <= 0.0))
        throw Error("A dash tuple needs an even number of finite, non-negative lengths.");
    return dash;
}

std::vector<double> dash_pattern_pt(const Dash& dash, double width_pt) {
    if (dash.name.empty()) return dash.lengths;
    double scale = std::max(width_pt, 1.0);
    std::vector<double> out;
    for (double v : dash_names().at(dash.name)) out.push_back(round6(v * scale));
    return out;
}

// ---------------------------------------------------------------------------
// JSON helpers: strict reading of fields
// ---------------------------------------------------------------------------

namespace {

void check_keys(const json& data, const std::vector<std::string>& known, const std::string& owner) {
    if (!data.is_object()) throw Error("Expected a dict for " + owner + ", not " + data.dump() + ".");
    for (auto it = data.begin(); it != data.end(); ++it)
        if (std::find(known.begin(), known.end(), it.key()) == known.end()) throw Error(owner + " has no field '" + it.key() + "'.");
}

double number_field(const json& data, const char* name, double fallback) {
    if (!data.contains(name)) return fallback;
    const json& v = data.at(name);
    if (!v.is_number() || v.is_boolean()) throw Error(std::string("Expected a number for ") + name + ", not " + v.dump() + ".");
    return v.get<double>();
}

std::string string_field(const json& data, const char* name, const std::string& fallback) {
    if (!data.contains(name)) return fallback;
    const json& v = data.at(name);
    if (!v.is_string()) throw Error(std::string("Expected a string for ") + name + ", not " + v.dump() + ".");
    return v.get<std::string>();
}

bool bool_field(const json& data, const char* name, bool fallback) {
    if (!data.contains(name)) return fallback;
    const json& v = data.at(name);
    if (!v.is_boolean()) throw Error(std::string("Expected true or false for ") + name + ", not " + v.dump() + ".");
    return v.get<bool>();
}

/// A colour field with its own alpha: an alpha in the colour multiplies into `alpha`.
Color color_with_alpha(const json& data, const char* name, const Color& fallback, double& alpha) {
    if (!data.contains(name)) return fallback;
    std::pair<Color, double> parsed = parse_color(data.at(name));
    if (parsed.first.present && parsed.second < 1.0) alpha *= parsed.second;
    return parsed.first;
}

Color opaque_field(const json& data, const char* name, const Color& fallback, const std::string& owner) {
    if (!data.contains(name)) return fallback;
    return opaque_color(data.at(name), owner, name);
}

json color_json(const Color& c) {
    return c.present ? json(c.hex) : json(nullptr);
}

std::vector<std::string> string_list(const json& value, const char* name) {
    std::vector<std::string> out;
    if (value.is_string()) {
        out.push_back(value.get<std::string>());
        return out;
    }
    if (!value.is_array()) throw Error(std::string("Expected a list for ") + name + ", not " + value.dump() + ".");
    for (const json& v : value) {
        if (!v.is_string()) throw Error(std::string("Expected strings in ") + name + ", not " + v.dump() + ".");
        out.push_back(v.get<std::string>());
    }
    return out;
}

}  // namespace

// ---------------------------------------------------------------------------
// LineStyle
// ---------------------------------------------------------------------------

void LineStyle::validate() const {
    check_length(width_pt, "LineStyle", "width_pt");
    check_length(casing_width_pt, "LineStyle", "casing_width_pt");
    check_alpha(alpha, "LineStyle");
    if (cap != "butt" && cap != "round" && cap != "square") throw Error("Unknown line cap '" + cap + "'.");
    if (join != "miter" && join != "round" && join != "bevel") throw Error("Unknown line join '" + join + "'.");
}

bool LineStyle::operator==(const LineStyle& o) const {
    return color == o.color && width_pt == o.width_pt && dash == o.dash && alpha == o.alpha && cap == o.cap && join == o.join
           && casing_color == o.casing_color && casing_width_pt == o.casing_width_pt;
}

json LineStyle::to_json() const {
    return json{{"color", color_json(color)},     {"width_pt", width_pt},
                {"dash", dash.to_json()},         {"alpha", alpha},
                {"cap", cap},                     {"join", join},
                {"casing_color", color_json(casing_color)}, {"casing_width_pt", casing_width_pt}};
}

LineStyle LineStyle::from_json(const json& data) {
    check_keys(data, {"color", "width_pt", "dash", "alpha", "cap", "join", "casing_color", "casing_width_pt"}, "LineStyle");
    LineStyle s;
    s.alpha = number_field(data, "alpha", 1.0);
    s.color = color_with_alpha(data, "color", s.color, s.alpha);
    s.width_pt = number_field(data, "width_pt", 1.0);
    if (data.contains("dash")) s.dash = Dash::from_json(data.at("dash"));
    s.cap = string_field(data, "cap", "butt");
    s.join = string_field(data, "join", "round");
    s.casing_color = opaque_field(data, "casing_color", Color::none(), "LineStyle");
    s.casing_width_pt = number_field(data, "casing_width_pt", 0.0);
    s.validate();
    return s;
}

LineStyle with_overrides(const LineStyle& style, const json& changes) {
    json record = style.to_json();
    for (auto it = changes.begin(); it != changes.end(); ++it) record[it.key()] = it.value();
    return LineStyle::from_json(record);
}

// ---------------------------------------------------------------------------
// MarkerStyle
// ---------------------------------------------------------------------------

void MarkerStyle::validate() const {
    static const std::vector<std::string> shapes = {"o", "s", "^", "v", "D", "x", "+"};
    if (std::find(shapes.begin(), shapes.end(), shape) == shapes.end()) throw Error("Unknown marker shape '" + shape + "'.");
    check_length(size_pt, "MarkerStyle", "size_pt");
    check_length(edge_width_pt, "MarkerStyle", "edge_width_pt");
    check_alpha(alpha, "MarkerStyle");
}

bool MarkerStyle::operator==(const MarkerStyle& o) const {
    return shape == o.shape && size_pt == o.size_pt && face_color == o.face_color && edge_color == o.edge_color
           && edge_width_pt == o.edge_width_pt && alpha == o.alpha;
}

json MarkerStyle::to_json() const {
    return json{{"shape", shape},
                {"size_pt", size_pt},
                {"face_color", color_json(face_color)},
                {"edge_color", color_json(edge_color)},
                {"edge_width_pt", edge_width_pt},
                {"alpha", alpha}};
}

MarkerStyle MarkerStyle::from_json(const json& data) {
    check_keys(data, {"shape", "size_pt", "face_color", "edge_color", "edge_width_pt", "alpha"}, "MarkerStyle");
    MarkerStyle s;
    s.shape = string_field(data, "shape", "o");
    s.size_pt = number_field(data, "size_pt", 6.0);
    s.face_color = opaque_field(data, "face_color", s.face_color, "MarkerStyle");
    s.edge_color = opaque_field(data, "edge_color", s.edge_color, "MarkerStyle");
    s.edge_width_pt = number_field(data, "edge_width_pt", 1.0);
    s.alpha = number_field(data, "alpha", 1.0);
    s.validate();
    return s;
}

// ---------------------------------------------------------------------------
// Font and TextStyle
// ---------------------------------------------------------------------------

void Font::validate() const {
    if (family.empty()) throw Error("Font: give at least one family.");
    check_length(size_pt, "Font", "size_pt");
    if (weight != "normal" && weight != "bold") throw Error("Font weight has to be 'normal' or 'bold'.");
    if (style != "normal" && style != "italic") throw Error("Font style has to be 'normal' or 'italic'.");
}

bool Font::operator==(const Font& o) const {
    return family == o.family && size_pt == o.size_pt && weight == o.weight && style == o.style && files == o.files;
}

json Font::to_json() const {
    return json{{"family", family}, {"size_pt", size_pt}, {"weight", weight}, {"style", style}, {"files", files}};
}

Font Font::from_json(const json& data) {
    check_keys(data, {"family", "size_pt", "weight", "style", "files"}, "Font");
    Font f;
    if (data.contains("family")) f.family = string_list(data.at("family"), "family");
    f.size_pt = number_field(data, "size_pt", 9.0);
    f.weight = string_field(data, "weight", "normal");
    f.style = string_field(data, "style", "normal");
    if (data.contains("files")) f.files = string_list(data.at("files"), "files");
    f.validate();
    return f;
}

void TextStyle::validate() const {
    font.validate();
    check_alpha(alpha, "TextStyle");
    check_length(halo_width_pt, "TextStyle", "halo_width_pt");
    if (h_align != "left" && h_align != "center" && h_align != "right") throw Error("Unknown horizontal alignment '" + h_align + "'.");
    if (v_align != "bottom" && v_align != "center" && v_align != "top") throw Error("Unknown vertical alignment '" + v_align + "'.");
}

bool TextStyle::operator==(const TextStyle& o) const {
    return font == o.font && color == o.color && alpha == o.alpha && h_align == o.h_align && v_align == o.v_align
           && halo_color == o.halo_color && halo_width_pt == o.halo_width_pt;
}

json TextStyle::to_json() const {
    return json{{"font", font.to_json()}, {"color", color_json(color)},         {"alpha", alpha},
                {"h_align", h_align},     {"v_align", v_align},                 {"halo_color", color_json(halo_color)},
                {"halo_width_pt", halo_width_pt}};
}

TextStyle TextStyle::from_json(const json& data) {
    check_keys(data, {"font", "color", "alpha", "h_align", "v_align", "halo_color", "halo_width_pt"}, "TextStyle");
    TextStyle s;
    if (data.contains("font")) s.font = Font::from_json(data.at("font"));
    s.alpha = number_field(data, "alpha", 1.0);
    s.color = color_with_alpha(data, "color", s.color, s.alpha);
    s.h_align = string_field(data, "h_align", "center");
    s.v_align = string_field(data, "v_align", "center");
    s.halo_color = opaque_field(data, "halo_color", Color::none(), "TextStyle");
    s.halo_width_pt = number_field(data, "halo_width_pt", 0.0);
    s.validate();
    return s;
}

// ---------------------------------------------------------------------------
// LegendStyle and AxesStyle
// ---------------------------------------------------------------------------

void LegendStyle::validate() const {
    static const std::vector<std::string> locations = {"upper left", "upper right", "lower left", "lower right", "outside right"};
    if (std::find(locations.begin(), locations.end(), location) == locations.end())
        throw Error("Unknown legend location '" + location + "'.");
    text.validate();
}

bool LegendStyle::operator==(const LegendStyle& o) const {
    return visible == o.visible && location == o.location && background == o.background && frame_color == o.frame_color && text == o.text;
}

json LegendStyle::to_json() const {
    return json{{"visible", visible},
                {"location", location},
                {"background", color_json(background)},
                {"frame_color", color_json(frame_color)},
                {"text", text.to_json()}};
}

LegendStyle LegendStyle::from_json(const json& data) {
    check_keys(data, {"visible", "location", "background", "frame_color", "text"}, "LegendStyle");
    LegendStyle s;
    s.visible = bool_field(data, "visible", true);
    s.location = string_field(data, "location", "outside right");
    s.background = opaque_field(data, "background", s.background, "LegendStyle");
    s.frame_color = opaque_field(data, "frame_color", Color::none(), "LegendStyle");
    if (data.contains("text")) s.text = TextStyle::from_json(data.at("text"));
    s.validate();
    return s;
}

AxesStyle::AxesStyle() {
    axis_label.font.size_pt = 10.0;
    title.font.size_pt = 11.0;
    title.font.weight = "bold";
    grid_major.color = Color::of("#dddddd");
    grid_major.width_pt = 0.5;
}

void AxesStyle::validate() const {
    check_length(frame_width_pt, "AxesStyle", "frame_width_pt");
    check_length(tick_length_pt, "AxesStyle", "tick_length_pt");
    check_length(tick_width_pt, "AxesStyle", "tick_width_pt");
    if (tick_direction != "out" && tick_direction != "in") throw Error("Tick direction has to be 'out' or 'in'.");
    tick_label.validate();
    axis_label.validate();
    title.validate();
    if (has_grid_major) grid_major.validate();
    if (has_grid_minor) grid_minor.validate();
    legend.validate();
}

bool AxesStyle::operator==(const AxesStyle& o) const {
    return background == o.background && figure_background == o.figure_background && frame_color == o.frame_color
           && frame_width_pt == o.frame_width_pt && tick_color == o.tick_color && tick_length_pt == o.tick_length_pt
           && tick_width_pt == o.tick_width_pt && tick_direction == o.tick_direction && tick_label == o.tick_label
           && axis_label == o.axis_label && title == o.title && has_grid_major == o.has_grid_major
           && (!has_grid_major || grid_major == o.grid_major) && has_grid_minor == o.has_grid_minor
           && (!has_grid_minor || grid_minor == o.grid_minor) && legend == o.legend;
}

json AxesStyle::to_json() const {
    return json{{"background", color_json(background)},
                {"figure_background", color_json(figure_background)},
                {"frame_color", color_json(frame_color)},
                {"frame_width_pt", frame_width_pt},
                {"tick_color", color_json(tick_color)},
                {"tick_length_pt", tick_length_pt},
                {"tick_width_pt", tick_width_pt},
                {"tick_direction", tick_direction},
                {"tick_label", tick_label.to_json()},
                {"axis_label", axis_label.to_json()},
                {"title", title.to_json()},
                {"grid_major", has_grid_major ? grid_major.to_json() : json(nullptr)},
                {"grid_minor", has_grid_minor ? grid_minor.to_json() : json(nullptr)},
                {"legend", legend.to_json()}};
}

AxesStyle AxesStyle::from_json(const json& data) {
    check_keys(data,
               {"background", "figure_background", "frame_color", "frame_width_pt", "tick_color", "tick_length_pt", "tick_width_pt",
                "tick_direction", "tick_label", "axis_label", "title", "grid_major", "grid_minor", "legend"},
               "AxesStyle");
    AxesStyle s;
    s.background = opaque_field(data, "background", s.background, "AxesStyle");
    s.figure_background = opaque_field(data, "figure_background", s.figure_background, "AxesStyle");
    s.frame_color = opaque_field(data, "frame_color", s.frame_color, "AxesStyle");
    s.frame_width_pt = number_field(data, "frame_width_pt", 0.8);
    s.tick_color = opaque_field(data, "tick_color", s.tick_color, "AxesStyle");
    s.tick_length_pt = number_field(data, "tick_length_pt", 3.5);
    s.tick_width_pt = number_field(data, "tick_width_pt", 0.8);
    s.tick_direction = string_field(data, "tick_direction", "out");
    if (data.contains("tick_label")) s.tick_label = TextStyle::from_json(data.at("tick_label"));
    if (data.contains("axis_label")) s.axis_label = TextStyle::from_json(data.at("axis_label"));
    if (data.contains("title")) s.title = TextStyle::from_json(data.at("title"));
    if (data.contains("grid_major")) {
        s.has_grid_major = !data.at("grid_major").is_null();
        if (s.has_grid_major) s.grid_major = LineStyle::from_json(data.at("grid_major"));
    }
    if (data.contains("grid_minor")) {
        s.has_grid_minor = !data.at("grid_minor").is_null();
        if (s.has_grid_minor) s.grid_minor = LineStyle::from_json(data.at("grid_minor"));
    }
    if (data.contains("legend")) s.legend = LegendStyle::from_json(data.at("legend"));
    s.validate();
    return s;
}

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

Theme::Theme() {
    isoline.width_pt = 0.75;
    saturation.width_pt = 1.5;
    quality.width_pt = 0.5;
    isoline_label.font.size_pt = 7.5;
    LineStyle process;
    process.width_pt = 2.0;
    processes = {process};
    state_points = {MarkerStyle()};
    state_number.font.size_pt = 8.0;
    state_number.font.weight = "bold";
}

void Theme::validate() const {
    if (categorical.empty()) throw Error("Theme '" + name + "': categorical needs at least one real colour.");
    if (processes.empty() || state_points.empty()) throw Error("Theme '" + name + "': give at least one process and one marker style.");
    isoline.validate();
    saturation.validate();
    quality.validate();
    isoline_label.validate();
    if (isoline_label_color != "text" && isoline_label_color != "line")
        throw Error("Theme '" + name + "': isoline_label_color is \"text\" or \"line\", not '" + isoline_label_color + "'.");
    for (const LineStyle& p : processes) p.validate();
    for (const MarkerStyle& m : state_points) m.validate();
    state_number.validate();
    axes.validate();
}

LineStyle Theme::isoline_style(const std::string& key, const std::vector<std::string>& families) const {
    std::string k = quantity_key(key);
    std::vector<std::string> keys;
    for (const std::string& f : families)
        if (quantity_key(f) != "Q") keys.push_back(quantity_key(f));
    size_t slot = keys.size();
    for (size_t i = 0; i < keys.size(); ++i)
        if (keys[i] == k) {
            slot = i;
            break;
        }
    LineStyle style = isoline;
    style.dash = slot_dashes[slot % slot_dashes.size()];
    auto pinned = isoline_colors.find(k);
    if (has_isoline_colors && pinned != isoline_colors.end())
        style.color = pinned->second;
    else
        style.color = Color::of(categorical[slot % categorical.size()]);
    return style;
}

namespace {

TextStyle scaled_text(TextStyle style, double factor) {
    style.font.size_pt *= factor;
    return style;
}

}  // namespace

Theme Theme::scaled(double factor) const {
    if (factor == 1.0) return *this;
    Theme t = *this;
    t.isoline_label = scaled_text(isoline_label, factor);
    t.state_number = scaled_text(state_number, factor);
    t.axes.tick_label = scaled_text(axes.tick_label, factor);
    t.axes.axis_label = scaled_text(axes.axis_label, factor);
    t.axes.title = scaled_text(axes.title, factor);
    t.axes.legend.text = scaled_text(axes.legend.text, factor);
    return t;
}

json Theme::to_json() const {
    json dashes = json::array();
    for (const Dash& d : slot_dashes) dashes.push_back(d.to_json());
    json pinned(nullptr);
    if (has_isoline_colors) {
        pinned = json::object();
        for (const auto& kv : isoline_colors) pinned[kv.first] = color_json(kv.second);
    }
    json process_list = json::array(), marker_list = json::array();
    for (const LineStyle& p : processes) process_list.push_back(p.to_json());
    for (const MarkerStyle& m : state_points) marker_list.push_back(m.to_json());
    return json{{"name", name},
                {"categorical", categorical},
                {"slot_dashes", dashes},
                {"isoline_colors", pinned},
                {"isoline", isoline.to_json()},
                {"saturation", saturation.to_json()},
                {"quality", quality.to_json()},
                {"isoline_label", isoline_label.to_json()},
                {"isoline_label_color", isoline_label_color},
                {"processes", process_list},
                {"state_points", marker_list},
                {"state_number", state_number.to_json()},
                {"axes", axes.to_json()}};
}

Theme Theme::from_json(const json& data) {
    check_keys(data,
               {"name", "categorical", "slot_dashes", "isoline_colors", "isoline", "saturation", "quality", "isoline_label",
                "isoline_label_color", "processes", "state_points", "state_number", "axes"},
               "Theme");
    Theme t;
    t.name = string_field(data, "name", "custom");
    std::string owner = "Theme '" + t.name + "'";
    if (data.contains("categorical")) {
        t.categorical.clear();
        for (const json& c : data.at("categorical")) {
            Color color = opaque_color(c, owner, "categorical");
            if (!color.present) throw Error(owner + ": categorical needs at least one real colour.");
            t.categorical.push_back(color.hex);
        }
    }
    if (data.contains("slot_dashes")) {
        t.slot_dashes.clear();
        for (const json& d : data.at("slot_dashes")) t.slot_dashes.push_back(Dash::from_json(d));
        if (t.slot_dashes.empty()) t.slot_dashes.push_back(Dash{"solid", {}});
    }
    if (data.contains("isoline_colors") && !data.at("isoline_colors").is_null()) {
        t.has_isoline_colors = true;
        for (auto it = data.at("isoline_colors").begin(); it != data.at("isoline_colors").end(); ++it)
            t.isoline_colors[quantity_key(it.key())] = opaque_color(it.value(), owner, "isoline_colors");
    }
    if (data.contains("isoline")) t.isoline = LineStyle::from_json(data.at("isoline"));
    if (data.contains("saturation")) t.saturation = LineStyle::from_json(data.at("saturation"));
    if (data.contains("quality")) t.quality = LineStyle::from_json(data.at("quality"));
    if (data.contains("isoline_label")) t.isoline_label = TextStyle::from_json(data.at("isoline_label"));
    t.isoline_label_color = string_field(data, "isoline_label_color", "text");
    if (data.contains("processes")) {
        t.processes.clear();
        for (const json& p : data.at("processes")) t.processes.push_back(LineStyle::from_json(p));
    }
    if (data.contains("state_points")) {
        t.state_points.clear();
        for (const json& m : data.at("state_points")) t.state_points.push_back(MarkerStyle::from_json(m));
    }
    if (data.contains("state_number")) t.state_number = TextStyle::from_json(data.at("state_number"));
    if (data.contains("axes")) t.axes = AxesStyle::from_json(data.at("axes"));
    t.validate();
    // The slot dashes have to be valid dashes for the isoline template
    for (const Dash& d : t.slot_dashes) {
        LineStyle probe = t.isoline;
        probe.dash = d;
        probe.validate();
    }
    return t;
}

// ---------------------------------------------------------------------------
// Presets (coolplot.style.theme)
// ---------------------------------------------------------------------------

namespace {

Font sans(double size_pt, const std::string& weight = "normal") {
    Font f;
    f.family = {"Inter", "Helvetica Neue", "Arial", "DejaVu Sans", "sans-serif"};
    f.size_pt = size_pt;
    f.weight = weight;
    return f;
}

TextStyle text_of(const Font& font, const std::string& color, const std::string& halo = "", double halo_width = 0.0) {
    TextStyle t;
    t.font = font;
    t.color = Color::of(color);
    if (!halo.empty()) {
        t.halo_color = Color::of(halo);
        t.halo_width_pt = halo_width;
    }
    return t;
}

LineStyle line_of(const std::string& color, double width_pt, const std::string& dash = "solid", const std::string& casing = "",
                  double casing_width = 0.0) {
    LineStyle l;
    l.color = Color::of(color);
    l.width_pt = width_pt;
    l.dash = Dash{dash, {}};
    if (!casing.empty()) {
        l.casing_color = Color::of(casing);
        l.casing_width_pt = casing_width;
    }
    return l;
}

MarkerStyle marker_of(const std::string& shape, double size_pt, const std::string& face, const std::string& edge, double edge_width) {
    MarkerStyle m;
    m.shape = shape;
    m.size_pt = size_pt;
    m.face_color = Color::of(face);
    m.edge_color = Color::of(edge);
    m.edge_width_pt = edge_width;
    return m;
}

Theme screen_theme(const std::string& name, const std::string& surface, const std::string& ink, const std::string& ink_secondary,
                   const std::string& ink_muted, const std::string& gridline, const std::string& baseline,
                   const std::vector<std::string>& categorical) {
    Theme t;
    t.name = name;
    t.categorical = categorical;
    t.isoline = line_of("#000000", 0.75);
    t.saturation = line_of(ink, 1.5, "solid", surface, 1.0);
    t.quality = line_of(ink_muted, 0.5);
    t.isoline_label = text_of(sans(7.5), ink_secondary, surface, 2.0);
    t.processes = {line_of(ink, 2.0, "solid", surface, 1.5), line_of(ink, 2.0, "dashed", surface, 1.5),
                   line_of(ink_secondary, 2.0, "dashdot", surface, 1.5)};
    t.state_points = {marker_of("o", 6.0, ink, surface, 1.0), marker_of("s", 6.0, ink, surface, 1.0),
                      marker_of("D", 6.0, ink_secondary, surface, 1.0)};
    t.state_number = text_of(sans(8.0, "bold"), ink, surface, 2.0);
    AxesStyle a;
    a.background = Color::of(surface);
    a.figure_background = Color::of(surface);
    a.frame_color = Color::of(baseline);
    a.frame_width_pt = 0.8;
    a.tick_color = Color::of(baseline);
    a.tick_label = text_of(sans(8.0), ink_secondary);
    a.axis_label = text_of(sans(9.5), ink);
    a.title = text_of(sans(11.0, "bold"), ink);
    a.has_grid_major = true;
    a.grid_major = line_of(gridline, 0.5);
    a.has_grid_minor = false;
    a.legend.location = "outside right";
    a.legend.background = Color::of(surface);
    a.legend.text = text_of(sans(8.0), ink_secondary);
    t.axes = a;
    return t;
}

const std::map<std::string, Theme>& themes() {
    static const std::map<std::string, Theme> table = [] {
        Theme light = screen_theme("default", "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7",
                                   {"#2a78d6", "#eb6834", "#1baf7a", "#eda100"});
        Theme dark = screen_theme("dark", "#1a1a19", "#ffffff", "#c3c2b7", "#898781", "#2c2c2a", "#383835",
                                  {"#3987e5", "#d95926", "#199e70", "#c98500"});
        Theme print = light;
        print.name = "print";
        print.categorical = {"#3a3a3a"};
        print.slot_dashes = {{"solid", {}}, {"dashed", {}}, {"dotted", {}}, {"dashdot", {}}};
        print.isoline = line_of("#000000", 0.6);
        print.quality = line_of("#7a7a7a", 0.4);
        print.axes.background = Color::of("#ffffff");
        print.axes.figure_background = Color::of("#ffffff");
        print.axes.frame_color = Color::of("#000000");
        print.axes.tick_color = Color::of("#000000");
        print.axes.grid_major = line_of("#d0d0d0", 0.4);
        Theme classic;
        classic.name = "classic";
        classic.categorical = {"#000000"};
        classic.has_isoline_colors = true;
        classic.isoline_colors = {{"T", Color::of("#8b0000")}, {"p", Color::of("#008b8b")},   {"h", Color::of("#006400")},
                                  {"rho", Color::of("#00008b")}, {"s", Color::of("#ff8c00")}, {"u", Color::of("#800080")},
                                  {"Twb", Color::of("#8b0000")}, {"v", Color::of("#00008b")}};
        classic.isoline = line_of("#000000", 0.5);
        classic.saturation = line_of("#000000", 1.0);
        classic.quality = line_of("#000000", 0.5);
        Font small;
        small.size_pt = 7.0;
        classic.isoline_label = text_of(small, "#000000", "#ffffff", 1.5);
        classic.processes = {line_of("#ff0000", 1.5)};
        classic.state_points = {marker_of("o", 5.0, "#ff0000", "#ff0000", 1.0)};
        Font eight;
        eight.size_pt = 8.0;
        classic.state_number = text_of(eight, "#ff0000", "#ffffff", 1.5);
        classic.axes = AxesStyle();
        classic.axes.has_grid_major = false;
        classic.axes.legend.visible = false;
        std::map<std::string, Theme> presets;
        for (const Theme& t : {light, dark, print, classic}) presets[t.name] = t;
        return presets;
    }();
    return table;
}

}  // namespace

const Theme& get_theme(const std::string& name) {
    std::string key = trimmed_lower(name);
    auto found = themes().find(key);
    if (found == themes().end()) throw Error("Unknown theme '" + name + "'.");
    return found->second;
}

}  // namespace coolplot
