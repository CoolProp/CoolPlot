// Placing isoline labels where they do not get in the way (coolplot.compose.layout).
//
// Everything is measured in points on the plot area. The module is pure:
// the same inputs always give the same labels. See the Python module's
// docstring for the rules; the names here follow it.
#ifndef COOLPLOT_LAYOUT_H
#define COOLPLOT_LAYOUT_H

#include <limits>
#include <map>
#include <string>
#include <vector>

#include "coolplot/scene.h"

namespace coolplot {

extern const double LABEL_CHAR_WIDTH;   ///< average character width relative to the font size
extern const double LABEL_LINE_HEIGHT;  ///< label box height relative to the font size
extern const double LABEL_PAD_PT;       ///< free space between a label and the frame or a neighbour
extern const double LABEL_MAX_BEND_DEG; ///< labels are not put where the line bends more than this

/// One line that wants a label, in display coordinates. ``value`` is the
/// line's value in display units (NaN where it has none) and ``line_color``
/// the colour of the line; the "rails" mode thins by the one and colours
/// ticks with the other.
struct LabelRequest
{
    std::string id;
    std::string group;
    std::string family;
    std::string text;
    TextStyle style;
    std::vector<double> x;
    std::vector<double> y;
    double value = std::numeric_limits<double>::quiet_NaN();
    Color line_color = Color::none();
};

/// An upright box no label may overlap (the legend, the badge), in points: centre and half sizes.
struct TakenBox
{
    double cx, cy, half_w, half_h;
};

/// The visible plot area and its size, to convert display units to points
/// (lower left corner of the plot area, y up).
struct Frame
{
    Range x_limits;
    Range y_limits;
    bool x_log = false;
    bool y_log = false;
    double width_pt = 0.0;
    double height_pt = 0.0;

    double x_to_pt(double x) const;
    double y_to_pt(double y) const;
    double x_to_data(double px) const;
    double y_to_data(double py) const;
    bool usable() const;
};

/// Estimated (width, height) of a one-line label in points.
std::pair<double, double> text_size_pt(const std::string& text, const TextStyle& style);

/// A visible part of a line in points, with the frame edges it starts and ends on ("" where the line ends inside).
struct Piece
{
    std::vector<double> px;
    std::vector<double> py;
    std::string start_edge;
    std::string end_edge;
    std::vector<double> arc;  ///< cumulative length

    double length() const {
        return arc.empty() ? 0.0 : arc.back();
    }
    std::pair<double, double> at(double s) const;
    /// (arc length, distance) of the point on the piece nearest to (qx, qy).
    std::pair<double, double> project(double qx, double qy) const;
};

/// The parts of a polyline (in points) inside the plot area; NaN splits a line.
std::vector<Piece> visible_pieces(const std::vector<double>& px, const std::vector<double>& py, double width, double height);

/// A line (or unconnected points) that labels keep away from, in display units.
struct KeepOut
{
    std::vector<double> x;
    std::vector<double> y;
    bool joined = true;
};

/// Points every 2 pt along the lines (single points for unjoined markers), in pt (coolplot.compose.layout.keep_out_points).
void keep_out_points_pt(const Frame& frame, const std::vector<KeepOut>& lines, std::vector<double>& xs, std::vector<double>& ys);

/// Edge labels for the requests, most important first (coolplot.compose.layout.place_edge_labels);
/// ``occupied`` are boxes no label may overlap (the legend).
std::vector<Item> place_edge_labels(const std::vector<LabelRequest>& requests, const Frame& frame, const std::vector<KeepOut>& keep_out,
                                    double keep_out_pt, const std::map<std::string, std::vector<std::string>>& preferred_edges,
                                    const std::map<std::string, Item>& previous, bool fallback,
                                    const std::vector<TakenBox>& occupied = std::vector<TakenBox>());

/// The level of each value for thinning: 0 for multiples of ten steps, 1 of five, 2 of two, 3 for the rest
/// (coolplot.compose.rails.value_levels).
std::vector<int> value_levels(const std::vector<double>& values);

/// Ticks and labels on rails along the frame (coolplot.compose.rails.place_rail_labels).
std::vector<Item> place_rail_labels(const std::vector<LabelRequest>& requests, const Frame& frame, const std::vector<KeepOut>& keep_out,
                                    double keep_out_pt, const std::map<std::string, Item>& previous, const std::vector<TakenBox>& occupied,
                                    bool outer_right);

/// Horizontal labels outside the frame where the lines cross it.
std::vector<Item> place_margin_labels(const std::vector<LabelRequest>& requests, const Frame& frame, const std::vector<std::string>& edges,
                                      double gap_pt = 3.0);

/// State numbers moved around their markers so they do not cover each other.
std::vector<Item> place_state_numbers(const std::vector<Item>& numbers, const Frame& frame, const std::vector<double>& marker_x,
                                      const std::vector<double>& marker_y);

}  // namespace coolplot

#endif
