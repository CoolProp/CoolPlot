#include "coolplot/core.h"

#include <algorithm>
#include <charconv>
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

std::string chars(double value, std::chars_format format, int precision) {
    char buffer[400];  // the longest fixed text of a double is about 330 characters
    std::to_chars_result result = std::to_chars(buffer, buffer + sizeof(buffer), value, format, precision);
    if (result.ec != std::errc()) throw Error("A number could not be written.");
    return std::string(buffer, result.ptr);
}

std::string printf_string(const char* format, int precision, double value) {
    // format is "%.*f", "%.*g" or "%.*e"; the letter decides
    char kind = format[std::char_traits<char>::length(format) - 1];
    std::chars_format f = kind == 'f' ? std::chars_format::fixed : kind == 'e' ? std::chars_format::scientific : std::chars_format::general;
    return chars(value, f, precision);
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
    if (is_zero(value)) return "0";
    // Round to the significant digits first, as Python's "{:.{digits}g}" does
    double rounded = parse_number(printf_string("%.*g", digits, value));
    if (!std::isfinite(rounded)) rounded = value;  // rounding up the largest numbers overflows
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
    int exponent = static_cast<int>(parse_number(text.substr(e + 1)));
    return mantissa + "e" + std::to_string(exponent);
}

std::string repr_number(double value) {
    if (std::isnan(value)) return "nan";
    if (std::isinf(value)) return value > 0 ? "inf" : "-inf";
    // The shortest "%.{n}g" that reads back exactly, as Python's repr
    std::string text;
    for (int precision = 1; precision <= 17; ++precision) {
        text = printf_string("%.*g", precision, value);
        if (same_number(parse_number(text), value)) break;  // reads back to the same number
    }
    // Python writes exponents with at least two digits and keeps ".0" on integers
    size_t e = text.find('e');
    if (e != std::string::npos) {
        std::string mantissa = text.substr(0, e);
        int exponent = static_cast<int>(parse_number(text.substr(e + 1)));
        char buffer[16];
        std::snprintf(buffer, sizeof(buffer), "e%c%02d", exponent < 0 ? '-' : '+', std::abs(exponent));
        // Python switches to exponent form only below 1e-4 or from 1e16; inside
        // that range it writes the decimals out
        if (!is_zero(value) && std::fabs(value) >= 1e-4 && std::fabs(value) < 1e16) {
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
    return parse_number(printf_string("%.*g", 12, value));
}

std::string fixed_text(double value, int precision) {
    return chars(value, std::chars_format::fixed, precision);
}

std::string general_text(double value, int precision) {
    return chars(value, std::chars_format::general, precision);
}

std::string scientific_text(double value, int precision) {
    return chars(value, std::chars_format::scientific, precision);
}

double parse_number(const std::string& text) {
    const char* first = text.c_str();
    const char* last = first + text.size();
    if (first != last && *first == '+') ++first;  // from_chars takes no leading plus (an exponent "+06")
    double value = 0.0;
    std::from_chars_result result = std::from_chars(first, last, value);
    if (result.ec == std::errc::result_out_of_range && result.ptr == last) {
        // Overflow or underflow: infinity or zero with the sign of the text.
        // Not strtod, which would read the decimal separator of the locale.
        bool negative = *first == '-';
        size_t e = text.find_first_of("eE");
        bool large = e != std::string::npos && e + 1 < text.size() && text[e + 1] != '-';
        return std::copysign(large ? HUGE_VAL : 0.0, negative ? -1.0 : 1.0);
    }
    if (result.ec != std::errc() || result.ptr != last) throw Error("'" + text + "' is not a number.");
    return value;
}

size_t text_length(const std::string& utf8) {
    size_t n = 0;
    for (unsigned char c : utf8)
        if ((c & 0xC0) != 0x80) ++n;  // count every byte that starts a character
    return n;
}

// ---------------------------------------------------------------------------
// Text width (coolplot.core.textwidth)
// ---------------------------------------------------------------------------

namespace {

// Advance widths in 1/1000 em of the characters " " (32) to "~" (126), Helvetica
const int HELVETICA_WIDTHS[] = {
    278, 278, 355, 556, 556, 889, 667, 222, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667,
    611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 278, 278, 278, 469, 556, 222, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500,
    222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
};
const double OTHER_EM = 0.6;   // a character outside printable ASCII
const double WIDE_EM = 1.0;    // a wide character (Chinese, Japanese, Korean, full-width forms)
const double TEXT_MARGIN = 1.15;

// The code points Python's unicodedata.east_asian_width calls "W" or "F",
// as ranges, from the Unicode database 15.1 (Python 3.13). Pythons with an
// older or newer database differ for a few rare characters only.
const std::pair<unsigned long, unsigned long> WIDE_RANGES[] = {
    {0x1100, 0x115F}, {0x231A, 0x231B}, {0x2329, 0x232A}, {0x23E9, 0x23EC}, {0x23F0, 0x23F0}, {0x23F3, 0x23F3},
    {0x25FD, 0x25FE}, {0x2614, 0x2615}, {0x2648, 0x2653}, {0x267F, 0x267F}, {0x2693, 0x2693}, {0x26A1, 0x26A1},
    {0x26AA, 0x26AB}, {0x26BD, 0x26BE}, {0x26C4, 0x26C5}, {0x26CE, 0x26CE}, {0x26D4, 0x26D4}, {0x26EA, 0x26EA},
    {0x26F2, 0x26F3}, {0x26F5, 0x26F5}, {0x26FA, 0x26FA}, {0x26FD, 0x26FD}, {0x2705, 0x2705}, {0x270A, 0x270B},
    {0x2728, 0x2728}, {0x274C, 0x274C}, {0x274E, 0x274E}, {0x2753, 0x2755}, {0x2757, 0x2757}, {0x2795, 0x2797},
    {0x27B0, 0x27B0}, {0x27BF, 0x27BF}, {0x2B1B, 0x2B1C}, {0x2B50, 0x2B50}, {0x2B55, 0x2B55}, {0x2E80, 0x2E99},
    {0x2E9B, 0x2EF3}, {0x2F00, 0x2FD5}, {0x2FF0, 0x303E}, {0x3041, 0x3096}, {0x3099, 0x30FF}, {0x3105, 0x312F},
    {0x3131, 0x318E}, {0x3190, 0x31E3}, {0x31EF, 0x321E}, {0x3220, 0x3247}, {0x3250, 0x4DBF}, {0x4E00, 0xA48C},
    {0xA490, 0xA4C6}, {0xA960, 0xA97C}, {0xAC00, 0xD7A3}, {0xF900, 0xFAFF}, {0xFE10, 0xFE19}, {0xFE30, 0xFE52},
    {0xFE54, 0xFE66}, {0xFE68, 0xFE6B}, {0xFF01, 0xFF60}, {0xFFE0, 0xFFE6}, {0x16FE0, 0x16FE4},
    {0x16FF0, 0x16FF1}, {0x17000, 0x187F7}, {0x18800, 0x18CD5}, {0x18D00, 0x18D08}, {0x1AFF0, 0x1AFF3},
    {0x1AFF5, 0x1AFFB}, {0x1AFFD, 0x1AFFE}, {0x1B000, 0x1B122}, {0x1B132, 0x1B132}, {0x1B150, 0x1B152},
    {0x1B155, 0x1B155}, {0x1B164, 0x1B167}, {0x1B170, 0x1B2FB}, {0x1F004, 0x1F004}, {0x1F0CF, 0x1F0CF},
    {0x1F18E, 0x1F18E}, {0x1F191, 0x1F19A}, {0x1F200, 0x1F202}, {0x1F210, 0x1F23B}, {0x1F240, 0x1F248},
    {0x1F250, 0x1F251}, {0x1F260, 0x1F265}, {0x1F300, 0x1F320}, {0x1F32D, 0x1F335}, {0x1F337, 0x1F37C},
    {0x1F37E, 0x1F393}, {0x1F3A0, 0x1F3CA}, {0x1F3CF, 0x1F3D3}, {0x1F3E0, 0x1F3F0}, {0x1F3F4, 0x1F3F4},
    {0x1F3F8, 0x1F43E}, {0x1F440, 0x1F440}, {0x1F442, 0x1F4FC}, {0x1F4FF, 0x1F53D}, {0x1F54B, 0x1F54E},
    {0x1F550, 0x1F567}, {0x1F57A, 0x1F57A}, {0x1F595, 0x1F596}, {0x1F5A4, 0x1F5A4}, {0x1F5FB, 0x1F64F},
    {0x1F680, 0x1F6C5}, {0x1F6CC, 0x1F6CC}, {0x1F6D0, 0x1F6D2}, {0x1F6D5, 0x1F6D7}, {0x1F6DC, 0x1F6DF},
    {0x1F6EB, 0x1F6EC}, {0x1F6F4, 0x1F6FC}, {0x1F7E0, 0x1F7EB}, {0x1F7F0, 0x1F7F0}, {0x1F90C, 0x1F93A},
    {0x1F93C, 0x1F945}, {0x1F947, 0x1F9FF}, {0x1FA70, 0x1FA7C}, {0x1FA80, 0x1FA88}, {0x1FA90, 0x1FABD},
    {0x1FABF, 0x1FAC5}, {0x1FACE, 0x1FADB}, {0x1FAE0, 0x1FAE8}, {0x1FAF0, 0x1FAF8}, {0x20000, 0x2FFFD},
    {0x30000, 0x3FFFD}
};

bool is_wide(unsigned long code_point) {
    for (const auto& range : WIDE_RANGES) {
        if (code_point < range.first) return false;   // the ranges are sorted
        if (code_point <= range.second) return true;
    }
    return false;
}

}  // namespace

double text_width_em(const std::string& utf8) {
    double total = 0.0;
    size_t i = 0;
    while (i < utf8.size()) {
        unsigned char c = static_cast<unsigned char>(utf8[i]);
        // Decode one UTF-8 character: the lead byte says how many bytes follow
        int extra = c < 0x80 ? 0 : (c >> 5) == 0x6 ? 1 : (c >> 4) == 0xE ? 2 : (c >> 3) == 0x1E ? 3 : 0;
        unsigned long code = extra == 0 ? c : extra == 1 ? (c & 0x1F) : extra == 2 ? (c & 0x0F) : (c & 0x07);
        for (int k = 1; k <= extra && i + k < utf8.size(); ++k) code = (code << 6) | (static_cast<unsigned char>(utf8[i + k]) & 0x3F);
        i += 1 + extra;
        if (code >= 32 && code <= 126)
            total += HELVETICA_WIDTHS[code - 32] / 1000.0;
        else
            total += is_wide(code) ? WIDE_EM : OTHER_EM;
    }
    return total;
}

double text_width_pt(const std::string& utf8, double size_pt) {
    return TEXT_MARGIN * size_pt * text_width_em(utf8);
}

std::string text_prefix(const std::string& utf8, size_t count) {
    size_t n = 0;
    for (size_t i = 0; i < utf8.size(); ++i) {
        if ((static_cast<unsigned char>(utf8[i]) & 0xC0) != 0x80) {
            if (n == count) return utf8.substr(0, i);
            ++n;
        }
    }
    return utf8;
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
      {"Thx", "T", "Temperature", false},  // the temperature scale of the Mollier h,x chart
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
            {"Q", unit("-")},     {"W", unit("kg/kg")}, {"RH", unit("-")},   {"Twb", unit("K")},    {"Tdp", unit("K")},     {"v", unit("m3/kg")},
            {"Thx", unit("K")}};
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
    units["Thx"] = unit("deg C", 1.0, -273.15, "K");
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
            {"v", unit("ft3/lb", FT3_PER_M3 / LB_PER_KG)},
            {"Thx", unit("deg F", 1.8, -459.67, "R")}};
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
    if (key == "EUR")
        throw Error("The unit system '" + name + "' was renamed 'engineering' (deg C, bar, kJ) in CoolPlot 0.5 and the old name removed in 1.0.");
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
                   && same_number(other->second.scale, kv.second.scale) && same_number(other->second.offset, kv.second.offset)
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
    if (data.is_string()) {
        // A record saved by CoolPlot 0.4 names the engineering system "EUR";
        // it still reads (a saved file is data, not a call)
        std::string name = data.get<std::string>();
        return get_unit_system(upper(name) == "EUR" ? "engineering" : name);
    }
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
    // The temperature scale of the Mollier chart is shown like the temperature, unless the record says otherwise
    if (out.units.count("T") && !out.units.count("Thx")) out.units["Thx"] = out.units.at("T");
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
    return std::any_of(boundary.begin(), boundary.end(), [value_SI](double b) { return same_number(b, value_SI); });
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
       {make_family("T", "W", {"right", "left"}, 12),  // isotherms, only where T is no axis (the Mollier chart)
        make_family("RH", "T", {"right", "top"}, 11, true, {0.0, 1.0}, false, {1.0}), make_family("Twb", "T", {"bottom", "left"}, 9),
        make_family("h", "T", {"bottom", "left"}, 13), make_family("v", "T", {"bottom", "right"}, 10)}},
    };
    return table;
}

const std::map<std::string, std::vector<std::string>>& axes_of_kind() {
    static const std::map<std::string, std::vector<std::string>> table = {
      {"fluid", {"T", "p", "h", "s", "rho", "u"}},
      {"humid_air", {"T", "W", "Thx"}},
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
      {"THXW", "Thx", "W", "humid_air"}, {"MOLLIER", "Thx", "W", "humid_air"}, {"HX", "Thx", "W", "humid_air"},
    };
    return table;
}

}  // namespace

DiagramType DiagramType::parse(const std::string& name) {
    std::string key = upper(name);
    for (const NamedType& t : named_types())
        if (key == t.name) return DiagramType{t.y, t.x, t.kind};
    // Any other pair of fluid axis quantities, vertical axis first, as a
    // DiagramType("T", "h") is written by its name "Th"
    for (size_t i = 1; i < name.size(); ++i) {
        try {
            DiagramType candidate{quantity_key(name.substr(0, i)), quantity_key(name.substr(i)), "fluid"};
            if (candidate.valid() && candidate.name() == name) return candidate;
        } catch (const Error&) {
        }
    }
    throw Error("Unknown diagram type '" + name + "'.");
}

bool DiagramType::valid() const {
    auto axes = axes_of_kind().find(kind);
    if (axes == axes_of_kind().end() || x == y) return false;
    const std::vector<std::string>& allowed = axes->second;
    return std::find(allowed.begin(), allowed.end(), x) != allowed.end() && std::find(allowed.begin(), allowed.end(), y) != allowed.end();
}

// ---------------------------------------------------------------------------
// Symbols
// ---------------------------------------------------------------------------

// The characters are written as UTF-8 bytes, so that the source stays ASCII
// and every compiler stores the same bytes. A hex escape takes every hex
// digit that follows, so a letter after one starts a new literal ("\xc2\xb0" "C").

namespace {

const std::map<std::string, std::string>& unicode_symbols() {
    static const std::map<std::string, std::string> table = {
      {"rho", "\xcf\x81"},  // Greek small letter rho, density
      {"phi", "\xcf\x86"},  // Greek small letter phi, relative humidity
      {"RH", "\xcf\x86"},
      {"Twb", "T_wb"},
      {"Tdp", "T_dp"},
    };
    return table;
}

const std::map<std::string, std::string>& unicode_units() {
    static const std::map<std::string, std::string> table = {
      {"deg C", "\xc2\xb0" "C"},  // degree sign
      {"deg F", "\xc2\xb0" "F"},
      {"R", "\xc2\xb0" "R"},
      {"Btu/lb/R", "Btu/lb/\xc2\xb0" "R"},
      {"kg/m3", "kg/m\xc2\xb3"},  // superscript three
      {"m3/kg", "m\xc2\xb3/kg"},
      {"lb/ft3", "lb/ft\xc2\xb3"},
      {"ft3/lb", "ft\xc2\xb3/lb"},
    };
    return table;
}

std::string replaced(const std::map<std::string, std::string>& table, const std::string& text, const std::string& style) {
    if (style != "unicode") return text;
    auto found = table.find(text);
    return found == table.end() ? text : found->second;
}
}

void check_symbol_style(const std::string& style) {
    if (style != "unicode" && style != "ascii") throw Error("Unknown symbol style '" + style + "'.");
}

std::string symbol_text(const std::string& symbol, const std::string& style) {
    return replaced(unicode_symbols(), symbol, style);
}

std::string unit_text(const std::string& label, const std::string& style) {
    return replaced(unicode_units(), label, style);
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

std::string DiagramType::symbol(const std::string& key) const {
    std::string k = quantity_key(key);
    if (kind == "humid_air" && y == "Thx" && x == "W") {  // the Mollier chart writes x and phi
        if (k == "W") return "x";
        if (k == "RH") return "phi";
    }
    return get_quantity(k).symbol;
}

std::string DiagramType::quantity_label(const std::string& key) const {
    std::string k = quantity_key(key);
    if (kind == "humid_air" && k == "T") return "Dry-bulb temperature";
    return get_quantity(k).label;
}

}  // namespace coolplot
