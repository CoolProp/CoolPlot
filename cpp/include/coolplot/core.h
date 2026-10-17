// coolplot-core: the presentation side of CoolPlot in C++.
//
// This header holds the plain data the rest of the library is built on,
// ported from coolplot.core: how numbers are written, the quantities a
// chart can show, unit systems, and the diagram types with their families
// of lines. Everything is ASCII, SI on the inside, and free of CoolProp
// and of any plotting library.
#ifndef COOLPLOT_CORE_H
#define COOLPLOT_CORE_H

#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "nlohmann/json.hpp"

namespace coolplot {

using json = nlohmann::json;

/// The error every bad input raises; the Python adapter turns it into ValueError.
class Error : public std::runtime_error
{
   public:
    explicit Error(const std::string& message) : std::runtime_error(message) {}
};

/// A pair of values (low, high), as limits or a range.
struct Range
{
    double lo = 0.0;
    double hi = 0.0;
};

// ---------------------------------------------------------------------------
// Numbers (coolplot.core.numbers)
// ---------------------------------------------------------------------------

/// A number with at most `digits` significant digits, plain ASCII: 25 -> "25",
/// 0.5 -> "0.5", 1e5 -> "100000", 1e6 -> "1e6", 0.00025 -> "2.5e-4". NaN and
/// infinities are written as "nan", "inf" and "-inf".
std::string format_number(double value, int digits = 6);

/// A number as Python's repr writes it: the shortest text that reads back
/// to the same double, e.g. 0.1 -> "0.1", 1e-5 -> "1e-05", 100.0 -> "100.0".
std::string repr_number(double value);

/// Round to 12 significant digits (coolplot.engine.planning.snap).
double snap(double value);

// ---------------------------------------------------------------------------
// Quantities (coolplot.core.quantities)
// ---------------------------------------------------------------------------

struct Quantity
{
    std::string key;     ///< the short name used everywhere, e.g. "p"
    std::string symbol;  ///< symbol in axis labels, plain ASCII
    std::string label;   ///< human readable name
    bool log_scale;      ///< whether an axis showing it defaults to a log scale
};

/// Normalise a quantity name to its key ("P" -> "p", "Hmass" -> "h"); throws Error.
std::string quantity_key(const std::string& name);
const Quantity& get_quantity(const std::string& name);

// ---------------------------------------------------------------------------
// Units (coolplot.core.units)
// ---------------------------------------------------------------------------

/// A linear unit: value_display = value_SI * scale + offset.
struct Unit
{
    std::string label;
    double scale = 1.0;
    double offset = 0.0;
    std::string difference_label;  ///< unit of a difference ("K" for deg C); the label if empty

    double from_SI(double value_SI) const {
        return value_SI * scale + offset;
    }
    double to_SI(double value) const {
        return (value - offset) / scale;
    }
};

/// A named set of units, one per quantity key.
struct UnitSystem
{
    std::string name;
    std::map<std::string, Unit> units;

    const Unit& at(const std::string& key) const;
    /// The record of the contracts: a preset name, or {"name", "units": {key: [label, scale, offset(, difference)]}}.
    json to_json() const;
    static UnitSystem from_json(const json& data);
};

/// A preset by name ("SI", "KSI", "engineering", "IP"; "EUR" as the old name of engineering).
const UnitSystem& get_unit_system(const std::string& name);

// ---------------------------------------------------------------------------
// Diagram types and families (coolplot.core.diagram_type)
// ---------------------------------------------------------------------------

/// How one family of lines (lines of constant `key`) is drawn.
struct Family
{
    std::string key;
    std::string sweep;
    std::vector<std::string> edges;  ///< preferred frame edges for the labels, best first
    int default_num = 15;
    bool has_bounds = false;
    Range bounds;
    bool low_included = true;
    std::vector<double> boundary;  ///< values drawn in the saturation style

    bool has_line(double value_SI) const;
    bool on_boundary() const {
        return !boundary.empty();
    }
    bool is_boundary_value(double value_SI) const;
};

/// The pair of quantities on the axes and the kind of chart ("fluid" or "humid_air").
struct DiagramType
{
    std::string y;
    std::string x;
    std::string kind = "fluid";

    /// From a name like "ph", "Ts", "WT" or "psychrometric".
    static DiagramType parse(const std::string& name);
    std::string name() const {
        return y + x;
    }
    /// Whether both axes may show their quantities in this kind of chart.
    bool valid() const;
    bool x_log() const;
    bool y_log() const;
    /// The families this chart can draw, in their usual order.
    std::vector<Family> families() const;
    /// The family of `iso_key`, or nullptr if the chart does not offer it (static storage).
    const Family* family(const std::string& iso_key) const;
    /// The name of a quantity in this kind of chart ("Dry-bulb temperature" on a psychrometric chart).
    std::string quantity_label(const std::string& key) const;
};

}  // namespace coolplot

#endif
