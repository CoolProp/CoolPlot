// Backend-neutral style values and themes (coolplot.style).
//
// Colours are "#rrggbb" with a separate alpha, lengths are typographic
// points, dash patterns resolve to explicit on/off lengths. A theme maps
// every kind of element of a chart to a style. Every value reads from and
// writes to the JSON records of docs/reference/contracts.md.
#ifndef COOLPLOT_STYLE_H
#define COOLPLOT_STYLE_H

#include <map>
#include <string>
#include <vector>

#include "coolplot/core.h"

namespace coolplot {

/// A colour as the styles hold it: "#rrggbb", or absent ("none").
struct Color
{
    bool present = false;
    std::string hex;  ///< "#rrggbb" when present

    static Color none() {
        return Color{};
    }
    static Color of(const std::string& hex) {
        return Color{true, hex};
    }
    bool operator==(const Color& other) const {
        return present == other.present && (!present || hex == other.hex);
    }
    bool operator!=(const Color& other) const {
        return !(*this == other);
    }
    /// The colour for an attribute: its hex, or "none".
    std::string text() const {
        return present ? hex : "none";
    }
};

/// Normalise a CSS colour name or hex code to (colour, alpha); "none" gives (absent, 0).
std::pair<Color, double> parse_color(const json& value);
/// A colour for a field without an alpha of its own: opaque or absent; partly transparent is refused.
Color opaque_color(const json& value, const std::string& owner, const std::string& field);

/// A dash: a name ("solid", "dashed", "dotted", "dashdot") or explicit lengths in points.
struct Dash
{
    std::string name;            ///< empty when explicit lengths are given
    std::vector<double> lengths;

    bool operator==(const Dash& other) const {
        return name == other.name && lengths == other.lengths;
    }
    json to_json() const;
    static Dash from_json(const json& value);
};

/// Explicit on/off lengths in points for a dash and a line width; empty means solid.
std::vector<double> dash_pattern_pt(const Dash& dash, double width_pt);

struct LineStyle
{
    Color color = Color::of("#000000");
    double width_pt = 1.0;
    Dash dash{"solid", {}};
    double alpha = 1.0;
    std::string cap = "butt";
    std::string join = "round";
    Color casing_color = Color::none();
    double casing_width_pt = 0.0;

    void validate() const;
    bool operator==(const LineStyle& o) const;
    bool operator!=(const LineStyle& o) const {
        return !(*this == o);
    }
    json to_json() const;
    static LineStyle from_json(const json& data);
};

struct MarkerStyle
{
    std::string shape = "o";
    double size_pt = 6.0;
    Color face_color = Color::of("#000000");
    Color edge_color = Color::of("#000000");
    double edge_width_pt = 1.0;
    double alpha = 1.0;

    void validate() const;
    bool operator==(const MarkerStyle& o) const;
    bool operator!=(const MarkerStyle& o) const {
        return !(*this == o);
    }
    json to_json() const;
    static MarkerStyle from_json(const json& data);
};

struct Font
{
    std::vector<std::string> family = {"DejaVu Sans", "Helvetica", "Arial", "sans-serif"};
    double size_pt = 9.0;
    std::string weight = "normal";
    std::string style = "normal";
    std::vector<std::string> files;

    void validate() const;
    bool operator==(const Font& o) const;
    json to_json() const;
    static Font from_json(const json& data);
};

struct TextStyle
{
    Font font;
    Color color = Color::of("#000000");
    double alpha = 1.0;
    std::string h_align = "center";
    std::string v_align = "center";
    Color halo_color = Color::none();
    double halo_width_pt = 0.0;

    void validate() const;
    bool operator==(const TextStyle& o) const;
    bool operator!=(const TextStyle& o) const {
        return !(*this == o);
    }
    json to_json() const;
    static TextStyle from_json(const json& data);
};

struct LegendStyle
{
    bool visible = true;
    std::string location = "outside right";
    Color background = Color::of("#ffffff");
    Color frame_color = Color::none();
    TextStyle text;

    void validate() const;
    bool operator==(const LegendStyle& o) const;
    json to_json() const;
    static LegendStyle from_json(const json& data);
};

struct AxesStyle
{
    Color background = Color::of("#ffffff");
    Color figure_background = Color::of("#ffffff");
    Color frame_color = Color::of("#000000");
    double frame_width_pt = 0.8;
    Color tick_color = Color::of("#000000");
    double tick_length_pt = 3.5;
    double tick_width_pt = 0.8;
    std::string tick_direction = "out";
    TextStyle tick_label;
    TextStyle axis_label;
    TextStyle title;
    bool has_grid_major = true;
    LineStyle grid_major;
    bool has_grid_minor = false;
    LineStyle grid_minor;
    LegendStyle legend;

    AxesStyle();
    void validate() const;
    bool operator==(const AxesStyle& o) const;
    bool operator!=(const AxesStyle& o) const {
        return !(*this == o);
    }
    json to_json() const;
    static AxesStyle from_json(const json& data);
};

/// All styles of a chart (coolplot.style.theme.Theme).
struct Theme
{
    std::string name = "custom";
    std::vector<std::string> categorical = {"#2a78d6", "#eb6834", "#1baf7a", "#eda100"};
    std::vector<Dash> slot_dashes = {{"solid", {}}, {"solid", {}}, {"solid", {}}, {"solid", {}}};
    bool has_isoline_colors = false;
    std::map<std::string, Color> isoline_colors;
    LineStyle isoline;
    LineStyle saturation;
    LineStyle quality;
    TextStyle isoline_label;
    std::string isoline_label_color = "text"; ///< "text" (isoline_label's colour) or "line" (each label in its line's colour)
    std::vector<LineStyle> processes;
    std::vector<MarkerStyle> state_points;
    TextStyle state_number;
    AxesStyle axes;

    Theme();
    void validate() const;
    /// Style of the isolines of `key` in a chart offering `families` (keys without "Q").
    LineStyle isoline_style(const std::string& key, const std::vector<std::string>& families) const;
    const LineStyle& process_style(size_t index) const {
        return processes[index % processes.size()];
    }
    const MarkerStyle& state_point_style(size_t index) const {
        return state_points[index % state_points.size()];
    }
    /// The theme with every font size multiplied by `factor` (Settings.page.font_scale).
    Theme scaled(double factor) const;
    json to_json() const;
    static Theme from_json(const json& data);
};

/// A preset by name: "default", "dark", "print", "classic".
const Theme& get_theme(const std::string& name);

/// Apply LineStyle field changes from a JSON record (a style override of a spec).
LineStyle with_overrides(const LineStyle& style, const json& changes);

}  // namespace coolplot

#endif
