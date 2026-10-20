// The scene: what a renderer draws (coolplot.scene).
//
// One set of axes and a flat list of items (lines, markers, texts) in
// drawing order, with coordinates in display units. The JSON form is the
// contract of docs/reference/contracts.md, section 3.
#ifndef COOLPLOT_SCENE_H
#define COOLPLOT_SCENE_H

#include <string>
#include <vector>

#include "coolplot/style.h"

namespace coolplot {

enum class ItemType { Line, Markers, Text };

/// A drawable item. One struct for the three kinds, with `type` saying
/// which fields apply: x/y arrays for lines and markers, the text fields
/// for a label.
struct Item
{
    ItemType type = ItemType::Line;
    std::string id;
    std::string group;
    std::string role;
    bool has_legend = false;
    std::string legend;
    bool visible = true;
    double z_order = 1.0;
    // lines and markers
    std::vector<double> x;
    std::vector<double> y;
    LineStyle line_style;
    MarkerStyle marker_style;
    // text
    double text_x = 0.0;
    double text_y = 0.0;
    std::string text;
    bool has_direction = false;
    double direction_x = 0.0;
    double direction_y = 0.0;
    TextStyle text_style;
    double offset_x_pt = 0.0;
    double offset_y_pt = 0.0;
    bool clip = true;

    void validate() const;
    json to_json() const;
    static Item from_json(const json& data);
};

/// Field by field equality, arrays by value with NaN equal to NaN (coolplot.scene.items_equal).
bool items_equal(const Item& a, const Item& b);

/// The axis limits a backend draws for the requested ones (coolplot.scene.drawable_limits).
Range drawable_limits(Range limits, bool log);

struct AxesSpec
{
    std::string x_label;
    std::string y_label;
    bool x_log = false;
    bool y_log = false;
    bool has_x_limits = false;
    Range x_limits;
    bool has_y_limits = false;
    Range y_limits;
    std::string title;
    AxesStyle style;
    int tick_digits = 6;

    void validate() const;
    bool operator==(const AxesSpec& o) const;
    bool operator!=(const AxesSpec& o) const {
        return !(*this == o);
    }
    json to_json() const;
    static AxesSpec from_json(const json& data);
};

/// An ordered collection of items plus one AxesSpec.
struct Scene
{
    AxesSpec axes;
    std::vector<Item> items;  ///< in scene order (insertion order)

    /// Item ids in drawing order: by z order, then by position in the scene.
    std::vector<size_t> draw_order() const;
    /// (text, item indices) pairs for the legend, in scene order.
    std::vector<std::pair<std::string, std::vector<size_t>>> legend_entries() const;
    const Item* find(const std::string& id) const;
    /// The scene record: items in drawing order (the contract), or in scene order when asked.
    json to_json(bool in_draw_order = true) const;
    static Scene from_json(const json& data);
};

}  // namespace coolplot

#endif
