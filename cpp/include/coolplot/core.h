// coolplot-core: the presentation side of CoolPlot in C++.
//
// This header holds the plain data the rest of the library is built on,
// ported from coolplot.core: how numbers are written, the quantities a
// chart can show, unit systems, and the diagram types with their families
// of lines. Everything is ASCII, SI on the inside, and free of CoolProp
// and of any plotting library.
#ifndef COOLPLOT_CORE_H
#define COOLPLOT_CORE_H

#include <cmath>
#include <cstdint>
#include <cstring>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "nlohmann/json.hpp"

namespace coolplot {

using json = nlohmann::json;

// Exact tests on doubles, without comparing two doubles for equality (the
// same helpers as coolplot/core/floats.py). Comparing with == is fragile: two
// ways of computing the same number can differ in the last bit. Where an
// exact answer is meant, these ask a sharper question.

/// Whether v is exactly zero, of either sign: a classification, not a comparison. NaN is not zero.
inline bool is_zero(double v) {
    return std::fpclassify(v) == FP_ZERO;
}

/// The 64 bits of a double, as an integer.
inline std::uint64_t bits_of(double v) {
    static_assert(sizeof(double) == sizeof(std::uint64_t), "a double has 64 bits");
    std::uint64_t bits = 0;
    std::memcpy(&bits, &v, sizeof bits);
    return bits;
}

/// Whether two doubles are the same input, bit for bit (a cache key).
inline bool same_bits(double a, double b) {
    return bits_of(a) == bits_of(b);
}

/// Whether a and b are the very same number: the same bits, or +0.0 and -0.0. For a value set or
/// copied earlier (a setting, a limit, a position), not for two results of a calculation. NaN is no number.
inline bool same_number(double a, double b) {
    if (std::isnan(a) || std::isnan(b)) return false;
    return same_bits(a, b) || (is_zero(a) && is_zero(b));
}

/// same_number element by element.
inline bool same_numbers(const std::vector<double>& a, const std::vector<double>& b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i)
        if (!same_number(a[i], b[i])) return false;
    return true;
}

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

/// printf-style "%.{precision}f", "%.{precision}g" and "%.{precision}e",
/// always with a decimal point: std::to_chars ignores the locale, while
/// printf writes "0,5" in an application that set a German LC_NUMERIC.
std::string fixed_text(double value, int precision);
std::string general_text(double value, int precision);
std::string scientific_text(double value, int precision);
/// A number from text, independent of the locale; throws Error on bad text.
double parse_number(const std::string& text);

/// The number of characters (code points) of UTF-8 text, as Python's len().
size_t text_length(const std::string& utf8);
/// The first `count` characters of UTF-8 text, never cutting a character.
std::string text_prefix(const std::string& utf8, size_t count);
/// Width of one line of UTF-8 text in em of Helvetica, without margin (coolplot.core.textwidth).
double text_width_em(const std::string& utf8);
/// Estimated width of one line of text at `size_pt`, 15 % wider than Helvetica for wider fonts.
double text_width_pt(const std::string& utf8, double size_pt);

// ---------------------------------------------------------------------------
// Quantities (coolplot.core.quantities)
// ---------------------------------------------------------------------------

struct Quantity
{
    std::string key;     ///< the short name used everywhere, e.g. "p"
    std::string symbol;  ///< symbol in axis labels, plain ASCII; charts may write it in Unicode (symbol_text)
    std::string label;   ///< human readable name
    bool log_scale;      ///< whether an axis showing it defaults to a log scale
};

/// Normalise a quantity name to its key ("P" -> "p", "Hmass" -> "h"); throws Error.
std::string quantity_key(const std::string& name);
const Quantity& get_quantity(const std::string& name);

// ---------------------------------------------------------------------------
// Symbols (coolplot.core.symbols)
// ---------------------------------------------------------------------------

/// Throws Error unless `style` is "unicode" or "ascii" (LabelSettings.symbols).
void check_symbol_style(const std::string& style);
/// A quantity symbol as the chart shows it: "rho" in "unicode" style is the Greek letter, in UTF-8.
std::string symbol_text(const std::string& symbol, const std::string& style);
/// A unit label as the chart shows it: "deg C" in "unicode" style is the degree sign and C, in UTF-8.
std::string unit_text(const std::string& label, const std::string& style);

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
    /// The value a label shows: from_SI without the noise of the offset. A line at 0 deg F is
    /// kept as 255.372222222 K (12 significant digits) and comes back as -4e-10; a result that
    /// small next to the two terms it is the difference of is zero (coolplot.core.units.Unit.label_value).
    double label_value(double value_SI) const {
        double term = value_SI * scale;
        double shown = term + offset;
        return std::fabs(shown) <= 1e-9 * std::fmax(std::fabs(term), std::fabs(offset)) ? 0.0 : shown;
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

/// A preset by name ("SI", "KSI", "engineering", "IP"). "EUR", the name of engineering
/// before 0.5, is refused since 1.0; UnitSystem::from_json still reads it in saved records.
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
    /// The symbol of a quantity in this diagram ("x" for the humidity ratio on the Mollier chart).
    std::string symbol(const std::string& key) const;
};

}  // namespace coolplot

#endif
