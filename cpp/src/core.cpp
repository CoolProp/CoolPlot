#include "coolplot/core.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>

namespace coolplot {

// ---------------------------------------------------------------------------
// Numbers
// ---------------------------------------------------------------------------

namespace {

const double SCI_BELOW = 1e-3;
const double SCI_ABOVE = 1e6;

std::string printf_string(const char* format, int precision, double value) {
    char buffer[64];
    std::snprintf(buffer, sizeof(buffer), format, precision, value);
    return buffer;
}

/// Strip trailing zeros after a decimal point, and the point itself.
std::string strip_zeros(std::string text) {
    if (text.find('.') == std::string::npos) return text;
    while (!text.empty() && text.back() == '0') text.pop_back();
    if (!text.empty() && text.back() == '.') text.pop_back();
    return text;
}

}  // namespace

std::string format_number(double value, int digits) {
    if (std::isnan(value)) return "nan";
    if (std::isinf(value)) return value > 0 ? "inf" : "-inf";
    if (value == 0.0) return "0";
    // Round to the significant digits first, as Python's "{:.{digits}g}" does
    double rounded = std::strtod(printf_string("%.*g", digits, value).c_str(), nullptr);
    double magnitude = std::fabs(rounded);
    if (SCI_BELOW <= magnitude && magnitude < SCI_ABOVE) {
        int exponent = static_cast<int>(std::floor(std::log10(magnitude)));
        int decimals = std::max(0, digits - 1 - exponent);
        std::string text = strip_zeros(printf_string("%.*f", decimals, rounded));
        return (text == "-0" || text.empty()) ? "0" : text;
    }
    std::string text = printf_string("%.*e", digits - 1, rounded);
    size_t e = text.find('e');
    std::string mantissa = strip_zeros(text.substr(0, e));
    int exponent = std::atoi(text.c_str() + e + 1);
    return mantissa + "e" + std::to_string(exponent);
}

std::string repr_number(double value) {
    if (std::isnan(value)) return "nan";
    if (std::isinf(value)) return value > 0 ? "inf" : "-inf";
    // The shortest "%.{n}g" that reads back exactly, as Python's repr
    std::string text;
    for (int precision = 1; precision <= 17; ++precision) {
        text = printf_string("%.*g", precision, value);
        if (std::strtod(text.c_str(), nullptr) == value) break;
    }
    // Python writes exponents with at least two digits and keeps ".0" on integers
    size_t e = text.find('e');
    if (e != std::string::npos) {
        std::string mantissa = text.substr(0, e);
        int exponent = std::atoi(text.c_str() + e + 1);
        char buffer[16];
        std::snprintf(buffer, sizeof(buffer), "e%c%02d", exponent < 0 ? '-' : '+', std::abs(exponent));
        // Python switches to exponent form only below 1e-4 or from 1e16; inside
        // that range it writes the decimals out
        if (value != 0.0 && std::fabs(value) >= 1e-4 && std::fabs(value) < 1e16) {
            int decimals = std::max(0, 16 - exponent);
            std::string plain = strip_zeros(printf_string("%.*f", decimals, value));
            if (plain.find('.') == std::string::npos) plain += ".0";
            return plain;
        }
        return mantissa + buffer;
    }
    if (text.find('.') == std::string::npos) text += ".0";
    return text;
}

double snap(double value) {
    return std::strtod(printf_string("%.*g", 12, value).c_str(), nullptr);
}

// ---------------------------------------------------------------------------
// Quantities
// ---------------------------------------------------------------------------

namespace {

const std::vector<Quantity>& quantities() {
    static const std::vector<Quantity> table = {
      {"T", "T", "Temperature", false},
      {"p", "p", "Pressure", true},
      {"h", "h", "Specific enthalpy", false},
      {"s", "s", "Specific entropy", false},
      {"rho", "rho", "Density", true},
      {"u", "u", "Specific internal energy", false},
      {"Q", "x", "Vapour quality", false},
      {"W", "W", "Humidity ratio", false},
      {"RH", "RH", "Relative humidity", false},
      {"Twb", "Twb", "Wet-bulb temperature", false},
      {"Tdp", "Tdp", "Dew-point temperature", false},
      {"v", "v", "Specific volume", false},
    };
    return table;
}

const std::map<std::string, std::string>& aliases() {
    static const std::map<std::string, std::string> table = {
      {"t", "T"},     {"P", "p"},     {"H", "h"},      {"hmass", "h"}, {"S", "s"},     {"smass", "s"},
      {"D", "rho"},   {"d", "rho"},   {"dmass", "rho"}, {"RHO", "rho"}, {"U", "u"},     {"umass", "u"},
      {"q", "Q"},     {"x", "Q"},     {"w", "W"},      {"rh", "RH"},   {"twb", "Twb"}, {"tdp", "Tdp"},
      {"V", "v"},
    };
    return table;
}

std::string lower(std::string text) {
    for (char& c : text) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return text;
}

const Quantity* find_quantity(const std::string& key) {
    for (const Quantity& q : quantities())
        if (q.key == key) return &q;
    return nullptr;
}

}  // namespace

std::string quantity_key(const std::string& name) {
    if (find_quantity(name)) return name;
    auto alias = aliases().find(name);
    if (alias != aliases().end()) return alias->second;
    std::string low = lower(name);
    if (find_quantity(low)) return low;
    alias = aliases().find(low);
    if (alias != aliases().end()) return alias->second;
    throw Error("Unknown quantity '" + name + "'.");
}

const Quantity& get_quantity(const std::string& name) {
    return *find_quantity(quantity_key(name));
}

// ---------------------------------------------------------------------------
// Units
// ---------------------------------------------------------------------------

const Unit& UnitSystem::at(const std::string& key) const {
    auto found = units.find(quantity_key(key));
    if (found == units.end()) throw Error("The unit system '" + name + "' has no unit for '" + key + "'.");
    return found->second;
}

namespace {

Unit unit(const std::string& label, double scale = 1.0, double offset = 0.0, const std::string& difference = "") {
    Unit u;
    u.label = label;
    u.scale = scale;
    u.offset = offset;
    u.difference_label = difference;
    return u;
}

std::map<std::string, Unit> si_units() {
    return {{"T", unit("K")},     {"p", unit("Pa")},    {"h", unit("J/kg")}, {"s", unit("J/kg/K")}, {"rho", unit("kg/m3")}, {"u", unit("J/kg")},
            {"Q", unit("-")},     {"W", unit("kg/kg")}, {"RH", unit("-")},   {"Twb", unit("K")},    {"Tdp", unit("K")},     {"v", unit("m3/kg")}};
}

std::map<std::string, Unit> ksi_units() {
    std::map<std::string, Unit> units = si_units();
    units["p"] = unit("kPa", 1e-3);
    units["h"] = unit("kJ/kg", 1e-3);
    units["s"] = unit("kJ/kg/K", 1e-3);
    units["u"] = unit("kJ/kg", 1e-3);
    return units;
}

std::map<std::string, Unit> engineering_units() {
    std::map<std::string, Unit> units = ksi_units();
    units["T"] = unit("deg C", 1.0, -273.15, "K");
    units["p"] = unit("bar", 1e-5);
    units["W"] = unit("g/kg", 1e3);
    units["RH"] = unit("%", 100.0);
    units["Twb"] = unit("deg C", 1.0, -273.15, "K");
    units["Tdp"] = unit("deg C", 1.0, -273.15, "K");
    return units;
}

std::map<std::string, Unit> ip_units() {
    const double BTU_PER_J = 1.0 / 1055.05585262;
    const double LB_PER_KG = 1.0 / 0.45359237;
    const double FT3_PER_M3 = 1.0 / (0.3048 * 0.3048 * 0.3048);
    return {{"T", unit("deg F", 1.8, -459.67, "R")},
            {"p", unit("psi", 1.0 / 6894.757293168)},
            {"h", unit("Btu/lb", BTU_PER_J / LB_PER_KG)},
            {"s", unit("Btu/lb/R", BTU_PER_J / LB_PER_KG / 1.8)},
            {"rho", unit("lb/ft3", LB_PER_KG / FT3_PER_M3)},
            {"u", unit("Btu/lb", BTU_PER_J / LB_PER_KG)},
            {"Q", unit("-")},
            {"W", unit("gr/lb", 7000.0)},
            {"RH", unit("%", 100.0)},
            {"Twb", unit("deg F", 1.8, -459.67, "R")},
            {"Tdp", unit("deg F", 1.8, -459.67, "R")},
            {"v", unit("ft3/lb", FT3_PER_M3 / LB_PER_KG)}};
}

const std::map<std::string, UnitSystem>& unit_systems() {
    static const std::map<std::string, UnitSystem> table = {
      {"SI", {"SI", si_units()}},
      {"KSI", {"KSI", ksi_units()}},
      {"ENGINEERING", {"engineering", engineering_units()}},
      {"IP", {"IP", ip_units()}},
    };
    return table;
}

std::string upper(std::string text) {
    for (char& c : text) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    return text;
}

}  // namespace

const UnitSystem& get_unit_system(const std::string& name) {
    std::string key = upper(name);
    if (key == "EUR") key = "ENGINEERING";  // the old name
    auto found = unit_systems().find(key);
    if (found == unit_systems().end()) throw Error("Unknown unit system '" + name + "'.");
    return found->second;
}

json UnitSystem::to_json() const {
    auto preset = unit_systems().find(upper(name));
    if (preset != unit_systems().end() && preset->second.units.size() == units.size()) {
        bool same = true;
        for (const auto& kv : units) {
            auto other = preset->second.units.find(kv.first);
            same = same && other != preset->second.units.end() && other->second.label == kv.second.label
                   && other->second.scale == kv.second.scale && other->second.offset == kv.second.offset
                   && other->second.difference_label == kv.second.difference_label;
        }
        if (same) return name;
    }
    json record;
    for (const auto& kv : units) {
        json unit = json::array({kv.second.label, kv.second.scale, kv.second.offset});
        if (!kv.second.difference_label.empty()) unit.push_back(kv.second.difference_label);
        record[kv.first] = unit;
    }
    return json{{"name", name}, {"units", record}};
}

UnitSystem UnitSystem::from_json(const json& data) {
    if (data.is_string()) return get_unit_system(data.get<std::string>());
    UnitSystem out;
    out.name = data.at("name").get<std::string>();
    for (auto it = data.at("units").begin(); it != data.at("units").end(); ++it) {
        const json& u = it.value();
        Unit unit;
        unit.label = u.at(0).get<std::string>();
        if (u.size() > 1) unit.scale = u.at(1).get<double>();
        if (u.size() > 2) unit.offset = u.at(2).get<double>();
        if (u.size() > 3) unit.difference_label = u.at(3).get<std::string>();
        out.units[quantity_key(it.key())] = unit;
    }
    return out;
}

// ---------------------------------------------------------------------------
// Diagram types
// ---------------------------------------------------------------------------

bool Family::has_line(double value_SI) const {
    if (!has_bounds) return true;
    bool above = low_included ? bounds.lo <= value_SI : bounds.lo < value_SI;
    return above && value_SI <= bounds.hi;
}

bool Family::is_boundary_value(double value_SI) const {
    return std::find(boundary.begin(), boundary.end(), value_SI) != boundary.end();
}

namespace {

Family make_family(const std::string& key, const std::string& sweep, std::vector<std::string> edges, int default_num = 15,
                   bool has_bounds = false, Range bounds = {0.0, 1.0}, bool low_included = true, std::vector<double> boundary = {}) {
    Family f;
    f.key = key;
    f.sweep = sweep;
    f.edges = std::move(edges);
    f.default_num = default_num;
    f.has_bounds = has_bounds;
    f.bounds = bounds;
    f.low_included = low_included;
    f.boundary = std::move(boundary);
    return f;
}

const std::map<std::string, std::vector<Family>>& all_families() {
    static const std::map<std::string, std::vector<Family>> table = {
      {"fluid",
       {make_family("T", "p", {"top", "right"}), make_family("p", "T", {"right", "left"}), make_family("h", "p", {"top", "bottom"}),
        make_family("s", "p", {"top", "right"}), make_family("rho", "T", {"right", "top"}), make_family("u", "p", {"top", "bottom"}),
        make_family("Q", "T", {"bottom", "top"}, 11, true, {0.0, 1.0}, true, {0.0, 1.0})}},
      {"humid_air",
       {make_family("RH", "T", {"right", "top"}, 11, true, {0.0, 1.0}, false, {1.0}), make_family("Twb", "T", {"bottom", "left"}, 9),
        make_family("h", "T", {"bottom", "left"}, 13), make_family("v", "T", {"bottom", "right"}, 10)}},
    };
    return table;
}

const std::map<std::string, std::vector<std::string>>& axes_of_kind() {
    static const std::map<std::string, std::vector<std::string>> table = {
      {"fluid", {"T", "p", "h", "s", "rho", "u"}},
      {"humid_air", {"T", "W"}},
    };
    return table;
}

struct NamedType
{
    const char* name;
    const char* y;
    const char* x;
    const char* kind;
};

const std::vector<NamedType>& named_types() {
    static const std::vector<NamedType> table = {
      {"TS", "T", "s", "fluid"},   {"PH", "p", "h", "fluid"},     {"HS", "h", "s", "fluid"},          {"PS", "p", "s", "fluid"},
      {"PD", "p", "rho", "fluid"}, {"PRHO", "p", "rho", "fluid"}, {"TD", "T", "rho", "fluid"},        {"TRHO", "T", "rho", "fluid"},
      {"PT", "p", "T", "fluid"},   {"WT", "W", "T", "humid_air"}, {"PSYCHROMETRIC", "W", "T", "humid_air"},
    };
    return table;
}

}  // namespace

DiagramType DiagramType::parse(const std::string& name) {
    std::string key = upper(name);
    for (const NamedType& t : named_types())
        if (key == t.name) return DiagramType{t.y, t.x, t.kind};
    throw Error("Unknown diagram type '" + name + "'.");
}

bool DiagramType::valid() const {
    auto axes = axes_of_kind().find(kind);
    if (axes == axes_of_kind().end() || x == y) return false;
    const std::vector<std::string>& allowed = axes->second;
    return std::find(allowed.begin(), allowed.end(), x) != allowed.end() && std::find(allowed.begin(), allowed.end(), y) != allowed.end();
}

bool DiagramType::x_log() const {
    return get_quantity(x).log_scale;
}

bool DiagramType::y_log() const {
    return get_quantity(y).log_scale;
}

std::vector<Family> DiagramType::families() const {
    auto found = all_families().find(kind);
    if (found == all_families().end()) throw Error("Unknown chart kind '" + kind + "'.");
    std::vector<Family> out;
    for (const Family& f : found->second)
        if (f.key != x && f.key != y) out.push_back(f);
    return out;
}

const Family* DiagramType::family(const std::string& iso_key) const {
    std::string key = quantity_key(iso_key);
    if (key == x || key == y) return nullptr;
    auto found = all_families().find(kind);
    if (found == all_families().end()) return nullptr;
    for (const Family& f : found->second)
        if (f.key == key) return &f;
    return nullptr;
}

std::string DiagramType::quantity_label(const std::string& key) const {
    std::string k = quantity_key(key);
    if (kind == "humid_air" && k == "T") return "Dry-bulb temperature";
    return get_quantity(k).label;
}

}  // namespace coolplot
