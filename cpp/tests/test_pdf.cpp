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
