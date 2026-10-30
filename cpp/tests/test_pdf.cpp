// The PDF writer: fonts, texts, determinism. The thorough check is the
// conformance kit's check_pdf, run from Python on the same output.
#include <catch2/catch_all.hpp>

#include <fstream>

#include "coolplot/pdf.h"
#include "coolplot/truetype.h"

using namespace coolplot;

namespace {

json load(const std::string& name) {
    std::ifstream in(std::string(COOLPLOT_TEST_DATA) + "/" + name);
    REQUIRE(in.good());
    return json::parse(in);
}

size_t count(const std::string& text, const std::string& part) {
    size_t n = 0, at = 0;
    while ((at = text.find(part, at)) != std::string::npos) {
        ++n;
        at += part.size();
    }
    return n;
}

}  // namespace

TEST_CASE("TrueType fonts are found, read and subset", "[pdf]") {
    FontIndex index(FontIndex::default_dirs());
    std::string path = index.find({"DejaVu Sans", "sans-serif"}, false, false);
    if (path.empty()) {
        WARN("No TrueType font on this machine; the PDF tests are skipped");
        return;
    }
    std::ifstream in(path, std::ios::binary);
    std::string data((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    TrueTypeFont font(data);
    CHECK(font.units_per_em() > 0);
    CHECK(font.glyph_of('A') > 0);
    CHECK(font.advance(font.glyph_of('A')) > 0);
    CHECK(font.ascent() > 0);
    CHECK(font.descent() < 0);
    std::string bold = index.find({"DejaVu Sans"}, true, false);
    CHECK(bold != path);
    std::string subset = font.subset({font.glyph_of('A'), font.glyph_of('b')});
    CHECK(TrueTypeFont::is_truetype(subset));
    CHECK(subset.size() < data.size() / 2);
    TrueTypeFont again(subset);
    CHECK(again.num_glyphs() == font.num_glyphs());
    CHECK(again.advance(font.glyph_of('A')) == font.advance(font.glyph_of('A')));
    CHECK(again.glyph_of('A') == font.glyph_of('A'));
    CHECK(index.find({"No Such Font"}, false, false).empty());
}

TEST_CASE("A character map is read only within its declared length", "[pdf]") {
    // A damaged font: every subtable of the cmap table claims a length of 16
    // bytes, so its segments or groups lie outside it. Nothing may be mapped
    // from the bytes that follow (another subtable or another table).
    FontIndex index(FontIndex::default_dirs());
    std::string path = index.find({"DejaVu Sans", "sans-serif"}, false, false);
    if (path.empty()) return;
    std::ifstream in(path, std::ios::binary);
    std::string data((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    auto get = [&](size_t at, int bytes) {
        unsigned long v = 0;
        for (int i = 0; i < bytes; ++i) v = (v << 8) | static_cast<unsigned char>(data[at + i]);
        return v;
    };
    auto put = [&](size_t at, int bytes, unsigned long v) {
        for (int i = bytes - 1; i >= 0; --i, v >>= 8) data[at + i] = static_cast<char>(v & 0xFF);
    };
    size_t cmap = 0;
    for (unsigned long i = 0; i < get(4, 2); ++i)   // the table directory
        if (data.compare(12 + 16 * i, 4, "cmap") == 0) cmap = get(12 + 16 * i + 8, 4);
    REQUIRE(cmap > 0);
    REQUIRE(TrueTypeFont(data).glyph_of('A') > 0);
    for (unsigned long i = 0; i < get(cmap + 2, 2); ++i) {
        size_t sub = cmap + get(cmap + 4 + 8 * i + 4, 4);
        unsigned long format = get(sub, 2);
        if (format == 4) put(sub + 2, 2, 16);          // length is a u16 after the format
        else if (format == 12) put(sub + 4, 4, 16);    // a u32 after format and reserved
    }
    TrueTypeFont damaged(data);
    CHECK(damaged.glyph_of('A') == 0);
}

TEST_CASE("The conformance scene becomes one PDF page with embedded fonts", "[pdf]") {
    FontIndex index(FontIndex::default_dirs());
    if (index.find({"sans-serif"}, false, false).empty()) return;
    Scene scene = Scene::from_json(load("conformance_scene.json"));
    PdfOptions options;
    options.compress = false;
    std::string pdf = scene_to_pdf(scene, options);
    CHECK(pdf.rfind("%PDF-1.4", 0) == 0);
    CHECK(pdf.find("/Type /Page ") != std::string::npos);
    CHECK(count(pdf, "/FontFile2") >= 2);  // sans and serif
    CHECK(count(pdf, "/Subtype /CIDFontType2") >= 2);
    CHECK(pdf.find("/ToUnicode") != std::string::npos);
    CHECK(pdf.find("/Title (Conformance)") != std::string::npos);
    CHECK(pdf.find("/CreationDate") == std::string::npos);
    CHECK(scene_to_pdf(scene, options) == pdf);  // deterministic
    CHECK(pdf_plot_size_pt(scene).first > 0.0);
    options.compress = true;
    std::string packed = scene_to_pdf(scene, options);
    CHECK(packed.rfind("%PDF-1.4", 0) == 0);
    PdfOptions nowhere;
    nowhere.font_dirs = {"/nonexistent"};
    CHECK_THROWS_AS(scene_to_pdf(scene, nowhere), Error);
}

TEST_CASE("The badge is drawn on the PDF page: a translucent box with a frame", "[pdf][badge]") {
    FontIndex index(FontIndex::default_dirs());
    if (index.find({"sans-serif"}, false, false).empty()) return;
    Scene scene = Scene::from_json(load("compose_badge_r290_ph.json").at("scene_order"));
    PdfOptions options;
    options.compress = false;
    std::string pdf = scene_to_pdf(scene, options);
    CHECK(pdf.find("/CA 1 /ca 0.85") != std::string::npos);  // the box fill of the badge
    CHECK(pdf.find(" re B\n") != std::string::npos);         // filled and framed
    scene.axes.has_badge = false;
    CHECK(scene_to_pdf(scene, options).find("/ca 0.85") == std::string::npos);
}
