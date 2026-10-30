// The parts of a chart spec the composer needs (coolplot.spec), read from
// the JSON record of docs/reference/contracts.md, section 1. The fluid and
// the limits are not read: the composer gets the calculation domain and the
// computed curves from the caller.
#ifndef COOLPLOT_SPEC_H
#define COOLPLOT_SPEC_H

#include <map>
#include <string>
#include <vector>

#include "coolplot/core.h"
#include "coolplot/style.h"

namespace coolplot {

struct LabelSettings
{
    std::string mode = "rails";
    double keep_out_pt = 12.0;
    std::map<std::string, std::vector<std::string>> edges;
    std::vector<std::string> margin_edges = {"top"};
    bool fallback = true;
    int every = 1;
    double position = 0.5;
    int digits = 4;
    bool show_units = true;
    int tick_digits = 6;
    /// "unicode" (rho, deg C and m3 with their own characters) or "ascii"; a labels record without it is "ascii"
    std::string symbols = "unicode";

    /// The edges set for a family, or the family's own.
    std::vector<std::string> preferred_edges(const std::string& family, const std::vector<std::string>& fallback_edges) const;
    std::string format_value(double value) const {
        return format_number(value, digits);
    }
    static LabelSettings from_json(const json& data);
};

struct PageSettings
{
    double width_pt = 576.0;
    double height_pt = 432.0;
    double font_scale = 1.0;

    static PageSettings from_json(const json& data);
};

/// The badge part of the branding (coolplot.spec.settings.BrandingSettings).
/// The references and versions lines need CoolProp, so the caller computes
/// them and hands them over as the "sources" of the compose record; the
/// core adds `lines` below them. Logos and watermarks are drawn by Python.
struct BrandingSettings
{
    std::vector<std::string> lines;
    std::string location = "auto";
    double logo_width_pt = 60.0;
    double font_size_pt = 6.0;
    double background_alpha = 0.85;
    bool frame = true;

    static BrandingSettings from_json(const json& data);
};

struct Settings
{
    Theme look;
    LabelSettings labels;
    PageSettings page;
    BrandingSettings branding;

    static Settings from_json(const json& data);
};

struct IsolineSet
{
    std::string key;
    bool labels = false;
    // Placed by saturation states (IsolineSet.anchor in Python): the values
    // come with the curves; the composer needs only what the labels show
    bool has_anchor = false;
    std::string anchor_by;                   ///< "T" or "p"
    double anchor_Q = 1.0;                   ///< vapour quality of the saturation states
    std::string anchor_label = "value";      ///< "value" (the line's own value) or "saturation"
};

/// A legacy process: states along a line and states with markers (SI values by key).
struct ProcessSpec
{
    std::string name;
    std::vector<std::map<std::string, double>> line_states;
    std::vector<std::map<std::string, double>> marker_states;
    bool has_line_style = false;
    LineStyle line_style;
    bool has_marker_style = false;
    MarkerStyle marker_style;
};

struct CycleSpec
{
    std::string name;
    bool numbers = true;
    std::map<int, std::string> labels;  ///< text written next to a state, after its number
    bool has_line_style = false;
    LineStyle line_style;
    bool has_marker_style = false;
    MarkerStyle marker_style;
};

struct DiagramSpec
{
    DiagramType diagram;
    UnitSystem units;
    Settings settings;
    std::vector<IsolineSet> isolines;
    std::vector<ProcessSpec> processes;
    std::vector<CycleSpec> cycles;
    std::map<std::string, json> style_overrides;  ///< LineStyle field changes per family, and for "saturation"
    bool has_x_view = false;
    Range x_view_SI;
    bool has_y_view = false;
    Range y_view_SI;
    std::string title;

    /// LineStyle changes for one family (a quantity key) or the saturation curve ("saturation"),
    /// an empty object if none.
    json style_override(const std::string& key) const;
    static DiagramSpec from_json(const json& data);
};

}  // namespace coolplot

#endif
