// TrueType fonts: reading the tables a PDF needs, and a subset with the
// outlines of the used glyphs only.
//
// Only fonts with TrueType outlines (a glyf table) are taken; OpenType
// fonts with CFF outlines are refused, as the PDF check expects TrueType
// in a TrueType slot.
#ifndef COOLPLOT_TRUETYPE_H
#define COOLPLOT_TRUETYPE_H

#include <map>
#include <set>
#include <string>
#include <vector>

#include "coolplot/core.h"

namespace coolplot {

class TrueTypeFont
{
   public:
    /// Parse a font file's bytes; throws Error for anything but a TrueType font.
    explicit TrueTypeFont(const std::string& data);
    /// Whether the bytes are a font with TrueType outlines (no exception).
    static bool is_truetype(const std::string& data);

    const std::string& family() const {
        return family_;
    }
    const std::string& subfamily() const {
        return subfamily_;
    }
    bool bold() const;
    bool italic() const;
    int units_per_em() const {
        return units_per_em_;
    }
    int num_glyphs() const {
        return static_cast<int>(advances_.size());
    }
    /// The glyph of a code point, 0 (notdef) if the font has none.
    int glyph_of(unsigned long code_point) const;
    /// Advance width of a glyph in font units.
    int advance(int glyph) const;
    /// Font metrics in font units.
    int ascent() const {
        return ascent_;
    }
    int descent() const {
        return descent_;
    }
    int cap_height() const {
        return cap_height_;
    }
    double italic_angle() const {
        return italic_angle_;
    }
    int x_min() const {
        return bbox_[0];
    }
    int y_min() const {
        return bbox_[1];
    }
    int x_max() const {
        return bbox_[2];
    }
    int y_max() const {
        return bbox_[3];
    }
    /// A PostScript name for the font: the family and subfamily without spaces.
    std::string postscript_name() const;

    /// The font with the outlines of `glyphs` (and their components) only;
    /// glyph numbers are kept, so the subset is used with an identity map.
    std::string subset(const std::set<int>& glyphs) const;

   private:
    struct Table
    {
        unsigned long offset;
        unsigned long length;
    };
    std::string data_;
    std::map<std::string, Table> tables_;
    std::string family_, subfamily_;
    int units_per_em_ = 1000;
    int ascent_ = 0, descent_ = 0, cap_height_ = 0;
    double italic_angle_ = 0.0;
    int bbox_[4] = {0, 0, 0, 0};
    bool long_loca_ = false;
    std::vector<unsigned long> loca_;
    std::vector<int> advances_;
    std::map<unsigned long, int> cmap_;
    unsigned short weight_class_ = 400;
    unsigned short selection_ = 0;

    const Table& table(const std::string& tag) const;
    void read_names();
    void read_cmap();
    void components_of(int glyph, std::set<int>& out) const;
};

/// A font file found on this machine.
struct FontFace
{
    std::string path;
    std::string family;
    bool bold;
    bool italic;
};

/// Index of the TrueType fonts in `dirs` (recursive) and the given files,
/// built once per process and directory list.
class FontIndex
{
   public:
    explicit FontIndex(const std::vector<std::string>& dirs, const std::vector<std::string>& files = {});
    /// The default directories of this platform.
    static std::vector<std::string> default_dirs();
    const std::vector<FontFace>& faces() const {
        return faces_;
    }
    /// The file for a family list and weight/style, following the fallback
    /// rules of coolplot.style.values.Font; empty if no family can be found.
    std::string find(const std::vector<std::string>& families, bool bold, bool italic, std::string* family_used = nullptr) const;

   private:
    std::vector<FontFace> faces_;
    void add_file(const std::string& path);
    void scan(const std::string& dir, int depth);
};

}  // namespace coolplot

#endif
