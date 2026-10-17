#include "coolplot/truetype.h"

#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <sstream>

#include <dirent.h>
#include <sys/stat.h>

namespace coolplot {

namespace {

unsigned long u8(const std::string& d, size_t at) {
    if (at >= d.size()) throw Error("The font file is truncated.");
    return static_cast<unsigned char>(d[at]);
}
unsigned long u16(const std::string& d, size_t at) {
    return (u8(d, at) << 8) | u8(d, at + 1);
}
long s16(const std::string& d, size_t at) {
    long v = static_cast<long>(u16(d, at));
    return v >= 0x8000 ? v - 0x10000 : v;
}
unsigned long u32(const std::string& d, size_t at) {
    return (u16(d, at) << 16) | u16(d, at + 2);
}

void put16(std::string& out, unsigned long v) {
    out += static_cast<char>((v >> 8) & 0xFF);
    out += static_cast<char>(v & 0xFF);
}
void put32(std::string& out, unsigned long v) {
    put16(out, (v >> 16) & 0xFFFF);
    put16(out, v & 0xFFFF);
}

unsigned long checksum(const std::string& d, size_t at, size_t length) {
    unsigned long sum = 0;
    for (size_t i = 0; i < length; i += 4) {
        unsigned long word = 0;
        for (int k = 0; k < 4; ++k) word = (word << 8) | (i + k < length ? static_cast<unsigned char>(d[at + i + k]) : 0);
        sum = (sum + word) & 0xFFFFFFFFUL;
    }
    return sum;
}

std::string lower(std::string text) {
    for (char& c : text) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return text;
}

bool contains(const std::string& text, const std::string& part) {
    return lower(text).find(lower(part)) != std::string::npos;
}

}  // namespace

// ---------------------------------------------------------------------------
// Reading
// ---------------------------------------------------------------------------

bool TrueTypeFont::is_truetype(const std::string& data) {
    if (data.size() < 12) return false;
    unsigned long version = u32(data, 0);
    if (version != 0x00010000UL && data.substr(0, 4) != "true") return false;
    unsigned long n = u16(data, 4);
    for (unsigned long i = 0; i < n; ++i) {
        size_t at = 12 + 16 * i;
        if (at + 16 > data.size()) return false;
        if (data.substr(at, 4) == "glyf") return true;
    }
    return false;
}

TrueTypeFont::TrueTypeFont(const std::string& data) : data_(data) {
    if (!is_truetype(data)) throw Error("Not a font with TrueType outlines.");
    unsigned long n = u16(data_, 4);
    for (unsigned long i = 0; i < n; ++i) {
        size_t at = 12 + 16 * i;
        Table t = {u32(data_, at + 8), u32(data_, at + 12)};
        if (t.offset + t.length > data_.size()) throw Error("The font file is truncated.");
        tables_[data_.substr(at, 4)] = t;
    }
    const Table& head = table("head");
    units_per_em_ = static_cast<int>(u16(data_, head.offset + 18));
    for (int k = 0; k < 4; ++k) bbox_[k] = static_cast<int>(s16(data_, head.offset + 36 + 2 * k));
    long_loca_ = s16(data_, head.offset + 50) != 0;
    const Table& hhea = table("hhea");
    ascent_ = static_cast<int>(s16(data_, hhea.offset + 4));
    descent_ = static_cast<int>(s16(data_, hhea.offset + 6));
    unsigned long metrics = u16(data_, hhea.offset + 34);
    unsigned long glyphs = u16(data_, table("maxp").offset + 4);
    const Table& hmtx = table("hmtx");
    int last = 0;
    for (unsigned long g = 0; g < glyphs; ++g) {
        if (g < metrics) last = static_cast<int>(u16(data_, hmtx.offset + 4 * g));
        advances_.push_back(last);
    }
    const Table& loca = table("loca");
    for (unsigned long g = 0; g <= glyphs; ++g)
        loca_.push_back(long_loca_ ? u32(data_, loca.offset + 4 * g) : 2 * u16(data_, loca.offset + 2 * g));
    cap_height_ = static_cast<int>(0.7 * ascent_);
    auto os2 = tables_.find("OS/2");
    if (os2 != tables_.end()) {
        size_t at = os2->second.offset;
        unsigned long version = u16(data_, at);
        weight_class_ = static_cast<unsigned short>(u16(data_, at + 4));
        selection_ = static_cast<unsigned short>(u16(data_, at + 62));
        if (version >= 2 && os2->second.length >= 90) {
            int cap = static_cast<int>(s16(data_, at + 88));
            if (cap > 0) cap_height_ = cap;
        }
    }
    auto post = tables_.find("post");
    if (post != tables_.end()) italic_angle_ = static_cast<long>(static_cast<int32_t>(u32(data_, post->second.offset + 4))) / 65536.0;
    read_names();
    read_cmap();
}

const TrueTypeFont::Table& TrueTypeFont::table(const std::string& tag) const {
    auto found = tables_.find(tag);
    if (found == tables_.end()) throw Error("The font has no " + tag + " table.");
    return found->second;
}

void TrueTypeFont::read_names() {
    auto found = tables_.find("name");
    if (found == tables_.end()) return;
    size_t at = found->second.offset;
    unsigned long count = u16(data_, at + 2), strings = at + u16(data_, at + 4);
    std::map<int, std::string> best;  // name id -> text, Windows Unicode names preferred
    std::map<int, int> rank;
    for (unsigned long i = 0; i < count; ++i) {
        size_t rec = at + 6 + 12 * i;
        unsigned long platform = u16(data_, rec), encoding = u16(data_, rec + 2), language = u16(data_, rec + 4);
        int name_id = static_cast<int>(u16(data_, rec + 6));
        unsigned long length = u16(data_, rec + 8), offset = u16(data_, rec + 10);
        if (name_id != 1 && name_id != 2 && name_id != 16 && name_id != 17) continue;
        if (strings + offset + length > data_.size()) continue;
        std::string text;
        int score;
        if (platform == 3 && (encoding == 1 || encoding == 0)) {
            for (unsigned long k = 0; k + 1 < length; k += 2) {
                unsigned long cp = u16(data_, strings + offset + k);
                text += cp < 128 ? static_cast<char>(cp) : '?';
            }
            score = language == 0x0409 ? 3 : 2;
        } else if (platform == 1 || platform == 0) {
            if (platform == 0) {
                for (unsigned long k = 0; k + 1 < length; k += 2) {
                    unsigned long cp = u16(data_, strings + offset + k);
                    text += cp < 128 ? static_cast<char>(cp) : '?';
                }
            } else {
                text = data_.substr(strings + offset, length);
            }
            score = 1;
        } else {
            continue;
        }
        if (score > rank[name_id]) {
            rank[name_id] = score;
            best[name_id] = text;
        }
    }
    family_ = best.count(16) ? best[16] : best[1];
    subfamily_ = best.count(17) ? best[17] : best[2];
}

void TrueTypeFont::read_cmap() {
    auto found = tables_.find("cmap");
    if (found == tables_.end()) return;
    size_t at = found->second.offset;
    unsigned long count = u16(data_, at + 2);
    size_t chosen = 0;
    int chosen_rank = 0;
    for (unsigned long i = 0; i < count; ++i) {
        size_t rec = at + 4 + 8 * i;
        unsigned long platform = u16(data_, rec), encoding = u16(data_, rec + 2);
        size_t sub = at + u32(data_, rec + 4);
        if (sub + 4 > data_.size()) continue;
        unsigned long format = u16(data_, sub);
        int rank = 0;
        if (platform == 3 && encoding == 10 && format == 12) rank = 4;
        else if (platform == 3 && encoding == 1 && format == 4) rank = 3;
        else if (platform == 0 && format == 12) rank = 2;
        else if (platform == 0 && format == 4) rank = 1;
        if (rank > chosen_rank) {
            chosen_rank = rank;
            chosen = sub;
        }
    }
    if (!chosen_rank) return;
    unsigned long format = u16(data_, chosen);
    if (format == 4) {
        unsigned long seg_count = u16(data_, chosen + 6) / 2;
        size_t ends = chosen + 14, starts = ends + 2 * seg_count + 2, deltas = starts + 2 * seg_count, ranges = deltas + 2 * seg_count;
        for (unsigned long s = 0; s < seg_count; ++s) {
            unsigned long end = u16(data_, ends + 2 * s), start = u16(data_, starts + 2 * s);
            unsigned long delta = u16(data_, deltas + 2 * s), range_offset = u16(data_, ranges + 2 * s);
            if (start > end || start == 0xFFFF) continue;
            for (unsigned long c = start; c <= end; ++c) {
                unsigned long glyph;
                if (range_offset == 0) {
                    glyph = (c + delta) & 0xFFFF;
                } else {
                    size_t address = ranges + 2 * s + range_offset + 2 * (c - start);
                    if (address + 2 > data_.size()) continue;
                    glyph = u16(data_, address);
                    if (glyph) glyph = (glyph + delta) & 0xFFFF;
                }
                if (glyph) cmap_[c] = static_cast<int>(glyph);
            }
        }
    } else if (format == 12) {
        unsigned long groups = u32(data_, chosen + 12);
        for (unsigned long g = 0; g < groups; ++g) {
            size_t rec = chosen + 16 + 12 * g;
            unsigned long start = u32(data_, rec), end = u32(data_, rec + 4), glyph = u32(data_, rec + 8);
            if (end - start > 0x10000) continue;
            for (unsigned long c = start; c <= end; ++c) cmap_[c] = static_cast<int>(glyph + (c - start));
        }
    }
}

bool TrueTypeFont::bold() const {
    return (selection_ & 0x20) != 0 || weight_class_ >= 600 || contains(subfamily_, "bold");
}

bool TrueTypeFont::italic() const {
    return (selection_ & 0x01) != 0 || contains(subfamily_, "italic") || contains(subfamily_, "oblique");
}

int TrueTypeFont::glyph_of(unsigned long code_point) const {
    auto found = cmap_.find(code_point);
    return found == cmap_.end() ? 0 : found->second;
}

int TrueTypeFont::advance(int glyph) const {
    if (glyph < 0 || glyph >= num_glyphs()) return 0;
    return advances_[glyph];
}

std::string TrueTypeFont::postscript_name() const {
    std::string name;
    for (char c : family_ + (subfamily_ == "Regular" || subfamily_ == "Book" || subfamily_.empty() ? "" : "-" + subfamily_))
        if (c != ' ') name += c;
    return name.empty() ? "Font" : name;
}

// ---------------------------------------------------------------------------
// Subsetting
// ---------------------------------------------------------------------------

void TrueTypeFont::components_of(int glyph, std::set<int>& out) const {
    if (glyph < 0 || glyph >= num_glyphs() || out.count(glyph)) return;
    out.insert(glyph);
    unsigned long start = loca_[glyph], end = loca_[glyph + 1];
    if (end <= start + 10) return;
    size_t at = table("glyf").offset + start;
    if (s16(data_, at) >= 0) return;  // a simple glyph
    at += 10;
    while (true) {
        unsigned long flags = u16(data_, at);
        int component = static_cast<int>(u16(data_, at + 2));
        components_of(component, out);
        at += 4 + ((flags & 0x0001) ? 4 : 2);
        if (flags & 0x0008)
            at += 2;
        else if (flags & 0x0040)
            at += 4;
        else if (flags & 0x0080)
            at += 8;
        if (!(flags & 0x0020)) break;
    }
}

std::string TrueTypeFont::subset(const std::set<int>& glyphs) const {
    std::set<int> keep;
    keep.insert(0);
    for (int g : glyphs) components_of(g, keep);
    // New glyf and loca: the kept glyphs as they are, the others empty
    std::string glyf, loca;
    const Table& old_glyf = table("glyf");
    std::vector<unsigned long> offsets;
    for (int g = 0; g < num_glyphs(); ++g) {
        offsets.push_back(glyf.size());
        if (keep.count(g)) {
            glyf += data_.substr(old_glyf.offset + loca_[g], loca_[g + 1] - loca_[g]);
            while (glyf.size() % 4) glyf += '\0';
        }
    }
    offsets.push_back(glyf.size());
    for (unsigned long o : offsets) put32(loca, o);
    // The tables a PDF viewer needs are copied (metrics, hinting, names);
    // layout tables (GPOS, GSUB, kern, ...) are left out. head gets the long loca format
    static const std::set<std::string> kept_tables = {"head", "hhea", "maxp", "hmtx", "cmap", "OS/2", "post", "name", "cvt ", "fpgm", "prep", "gasp"};
    std::map<std::string, std::string> out_tables;
    for (const auto& kv : tables_)
        if (kept_tables.count(kv.first)) out_tables[kv.first] = data_.substr(kv.second.offset, kv.second.length);
    out_tables["glyf"] = glyf;
    out_tables["loca"] = loca;
    std::string& head = out_tables["head"];
    head[50] = 0;
    head[51] = 1;
    head[8] = head[9] = head[10] = head[11] = 0;  // checkSumAdjustment, computed below
    // The font file: directory, then the tables, 4-byte aligned
    std::string out;
    put32(out, 0x00010000UL);
    unsigned long count = out_tables.size();
    unsigned long search = 1, entry_selector = 0;
    while (search * 2 <= count) {
        search *= 2;
        ++entry_selector;
    }
    put16(out, count);
    put16(out, search * 16);
    put16(out, entry_selector);
    put16(out, count * 16 - search * 16);
    size_t directory = out.size();
    out.resize(directory + 16 * count, '\0');
    size_t head_at = 0;
    size_t i = 0;
    for (const auto& kv : out_tables) {
        while (out.size() % 4) out += '\0';
        size_t at = out.size();
        if (kv.first == "head") head_at = at;
        out += kv.second;
        size_t rec = directory + 16 * i++;
        for (int k = 0; k < 4; ++k) out[rec + k] = kv.first[k];
        std::string word;
        put32(word, checksum(out, at, kv.second.size()));
        put32(word, static_cast<unsigned long>(at));
        put32(word, static_cast<unsigned long>(kv.second.size()));
        out.replace(rec + 4, 12, word);
    }
    while (out.size() % 4) out += '\0';
    unsigned long adjustment = (0xB1B0AFBAUL - checksum(out, 0, out.size())) & 0xFFFFFFFFUL;
    std::string word;
    put32(word, adjustment);
    out.replace(head_at + 8, 4, word);
    return out;
}

// ---------------------------------------------------------------------------
// Finding fonts
// ---------------------------------------------------------------------------

std::vector<std::string> FontIndex::default_dirs() {
    std::vector<std::string> dirs = {"/usr/share/fonts", "/usr/local/share/fonts", "/Library/Fonts", "/System/Library/Fonts",
                                     "C:/Windows/Fonts"};
    const char* home = std::getenv("HOME");
    if (home) {
        dirs.push_back(std::string(home) + "/.fonts");
        dirs.push_back(std::string(home) + "/.local/share/fonts");
        dirs.push_back(std::string(home) + "/Library/Fonts");
    }
    return dirs;
}

FontIndex::FontIndex(const std::vector<std::string>& dirs, const std::vector<std::string>& files) {
    for (const std::string& file : files) add_file(file);
    for (const std::string& dir : dirs) scan(dir, 0);
}

void FontIndex::add_file(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in.good()) return;
    std::stringstream buffer;
    buffer << in.rdbuf();
    std::string data = buffer.str();
    if (!TrueTypeFont::is_truetype(data)) return;
    try {
        TrueTypeFont font(data);
        faces_.push_back({path, font.family(), font.bold(), font.italic()});
    } catch (const std::exception&) {
    }
}

void FontIndex::scan(const std::string& dir, int depth) {
    if (depth > 4) return;
    DIR* handle = opendir(dir.c_str());
    if (!handle) return;
    std::vector<std::string> names;
    while (dirent* entry = readdir(handle)) {
        std::string name = entry->d_name;
        if (name != "." && name != "..") names.push_back(name);
    }
    closedir(handle);
    std::sort(names.begin(), names.end());  // a fixed order, so the same font wins every time
    for (const std::string& name : names) {
        std::string path = dir + "/" + name;
        struct stat info;
        if (stat(path.c_str(), &info) != 0) continue;
        if (S_ISDIR(info.st_mode)) {
            scan(path, depth + 1);
        } else {
            std::string ext = lower(name.size() > 4 ? name.substr(name.size() - 4) : "");
            if (ext == ".ttf") add_file(path);
        }
    }
}

std::string FontIndex::find(const std::vector<std::string>& families, bool bold, bool italic, std::string* family_used) const {
    static const std::map<std::string, std::vector<std::string>> generic = {
      {"sans-serif", {"DejaVu Sans", "Liberation Sans", "Arial", "Helvetica", "Helvetica Neue"}},
      {"serif", {"DejaVu Serif", "Liberation Serif", "Times New Roman", "Times"}},
      {"monospace", {"DejaVu Sans Mono", "Liberation Mono", "Courier New", "Courier"}},
    };
    std::vector<std::string> wanted;
    for (const std::string& family : families) {
        auto g = generic.find(lower(family));
        if (g != generic.end())
            wanted.insert(wanted.end(), g->second.begin(), g->second.end());
        else
            wanted.push_back(family);
    }
    for (const std::string& family : wanted) {
        const FontFace* best = nullptr;
        int best_score = -1;
        for (const FontFace& face : faces_) {
            if (lower(face.family) != lower(family)) continue;
            int score = (face.bold == bold ? 2 : 0) + (face.italic == italic ? 1 : 0);
            if (score > best_score) {
                best_score = score;
                best = &face;
            }
        }
        if (best) {
            if (family_used) *family_used = best->family;
            return best->path;
        }
    }
    return "";
}

}  // namespace coolplot
