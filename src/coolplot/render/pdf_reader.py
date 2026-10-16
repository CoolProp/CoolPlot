# -*- coding: utf-8 -*-
"""Reading a PDF file back, for the conformance kit.

A small reader for the simple PDF files that plotting libraries write
(uncompressed object tables, Flate compressed streams, no encryption). It
finds what a print check cares about:

* the fonts, how each is embedded, and problems: Type 3 fonts, fonts that
  are not embedded, and font programs that do not match their declared
  type (CFF data in a TrueType slot, which viewers report as a damaged
  font);
* the texts, decoded through each font's ToUnicode table;
* the colours used for strokes and fills, and whether CMYK is used;
* the number of pages and the document information (title, author).

It is not a general PDF parser: compressed object streams are refused
with ValueError, so the kit reports them instead of guessing.

:func:`replace_info` writes such a file back with new document
information (and no file identifier), e.g. to give a PDF from another
program the chart title and drop its creation date, so that the same
chart gives the same file.
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

_OBJECT_START = re.compile(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b")
_REF = rb"\s+(\d+)\s+\d+\s+R"


@dataclass
class PdfFont:
    """One font of a PDF file"""
    name: str                   # base font name without the subset tag, e.g. "DejaVuSans"
    subtype: str                # Type0, TrueType, Type1 or Type3
    descendant: Optional[str]   # CIDFontType2 or CIDFontType0 for Type0 fonts
    program: Optional[str]      # FontFile, FontFile2 or FontFile3; None if not embedded
    program_kind: Optional[str]  # "truetype", "cff-opentype", "cff", "type1" or None
    problems: List[str] = field(default_factory=list)


@dataclass
class PdfContent:
    """What :func:`read_pdf` found"""
    pages: int
    info: Dict[str, str]
    fonts: List[PdfFont]
    texts: List[str]
    colors: Set[str]            # "#rrggbb" of every stroke and fill colour
    cmyk: bool                  # True if any CMYK colour operator is used


# ---------------------------------------------------------------------------
# Objects and streams
# ---------------------------------------------------------------------------
def _skip_dictionary(data: bytes, i: int) -> int:
    """Index just after the << >> dictionary starting at data[i], skipping strings inside."""
    depth = 0
    while i < len(data):
        if data.startswith(b"<<", i):
            depth, i = depth + 1, i + 2
        elif data.startswith(b">>", i):
            depth, i = depth - 1, i + 2
            if depth == 0:
                return i
        elif data[i:i + 1] == b"(":
            _, i = _literal(data, i)
        elif data[i:i + 1] == b"<":
            i = data.index(b">", i) + 1   # a hex string
        else:
            i += 1
    raise ValueError("Unterminated dictionary in the PDF file.")


class _Pdf:
    def __init__(self, data: bytes):
        if b"/Encrypt" in data:
            raise ValueError("Encrypted PDF files are not supported.")
        if re.search(rb"/Type\s*/(ObjStm|XRef)\b", data):
            raise ValueError("PDF files with compressed object streams are not supported.")
        self.data = data
        self.objects: Dict[int, bytes] = {}   # object number -> everything between "obj" and "endobj"
        self.first_object = None              # where the first object starts
        i = 0
        while True:
            match = _OBJECT_START.search(data, i)
            if not match:
                break
            if self.first_object is None:
                self.first_object = match.start()
            start = j = match.end()
            while data[j:j + 1].isspace():
                j += 1
            if data.startswith(b"<<", j):
                j = _skip_dictionary(data, j)
                after = re.match(rb"\s*stream\r?\n", data[j:j + 20])
                if after:
                    # Stream data is binary: skip it by its length, never by searching
                    length = self._length(data, data[match.end():j])
                    j += after.end() + length
            end = data.index(b"endobj", j)
            self.objects[int(match.group(1))] = data[start:end]
            i = end + len(b"endobj")

    @staticmethod
    def _length(data: bytes, dictionary: bytes) -> int:
        direct = re.search(rb"/Length\s+(\d+)\b(?!\s+\d+\s+R)", dictionary)   # not "12 0 R"
        if direct:
            return int(direct.group(1))
        ref = re.search(rb"/Length" + _REF, dictionary)
        if ref:
            value = re.search(rb"(?<![0-9])" + ref.group(1) + rb"\s+0\s+obj\s*(\d+)\s*endobj", data)
            if value:
                return int(value.group(1))
        raise ValueError("A stream in the PDF file has no readable /Length.")

    def dictionary(self, number: int) -> bytes:
        """The dictionary part of an object (everything before its stream)."""
        body = self.objects.get(number, b"")
        return body.split(b"stream", 1)[0] if re.search(rb"\bstream\r?\n", body) else body

    def stream(self, number: int) -> bytes:
        """The decoded stream of an object, or b"" if it has none."""
        body = self.objects.get(number, b"")
        match = re.search(rb"\bstream\r?\n", body)
        if not match:
            return b""
        raw = body[match.end():match.end() + self._length(self.data, body[:match.start()])]
        if b"/FlateDecode" in body[:match.start()]:
            return zlib.decompressobj().decompress(raw)
        return raw.rstrip(b"\r\n")

    def ref(self, dictionary: bytes, key: str) -> Optional[int]:
        match = re.search(rb"/" + key.encode() + _REF, dictionary)
        return int(match.group(1)) if match else None

    def sub_dictionary(self, dictionary: bytes, key: str) -> bytes:
        """The value of ``key``: an inline << >> dictionary or a referenced one."""
        number = self.ref(dictionary, key)
        if number is not None:
            return self.dictionary(number)
        start = re.search(rb"/" + key.encode() + rb"\s*<<", dictionary)
        if not start:
            return b""
        depth, i = 1, start.end()
        while i < len(dictionary) and depth:
            if dictionary.startswith(b"<<", i):
                depth, i = depth + 1, i + 2
            elif dictionary.startswith(b">>", i):
                depth, i = depth - 1, i + 2
            else:
                i += 1
        return dictionary[start.end():i - 2]


# ---------------------------------------------------------------------------
# Strings
# ---------------------------------------------------------------------------
def _literal(data: bytes, i: int):
    """A (...) string starting at data[i] == "("; returns (bytes, next index)."""
    out, depth, i = bytearray(), 1, i + 1
    escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while i < len(data):
        c = data[i]
        if c == 0x5C:   # backslash
            i += 1
            c = data[i]
            if c in escapes:
                out.append(escapes[c])
            elif 0x30 <= c <= 0x37:   # up to three octal digits
                digits = re.match(rb"[0-7]{1,3}", data[i:i + 3]).group(0)
                out.append(int(digits, 8) & 0xFF)
                i += len(digits) - 1
            elif c in (0x0A, 0x0D):
                pass   # a line continuation
            else:
                out.append(c)
        elif c == 0x28:
            depth += 1
            out.append(c)
        elif c == 0x29:
            depth -= 1
            if depth == 0:
                return bytes(out), i + 1
            out.append(c)
        else:
            out.append(c)
        i += 1
    return bytes(out), i


def _text_string(raw: bytes) -> str:
    """A string of the document information: UTF-16 with a byte order mark, or PDFDocEncoding."""
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", "replace")
    return raw.decode("latin-1")


def _info(pdf: _Pdf) -> Dict[str, str]:
    trailer = re.findall(rb"trailer\s*<<(.*?)>>", pdf.data, re.S)
    number = pdf.ref(trailer[-1], "Info") if trailer else None
    if number is None:
        return {}
    body = pdf.dictionary(number)
    out = {}
    for match in re.finditer(rb"/(\w+)\s*(\(|<)", body):
        if match.group(2) == b"(":
            raw, _ = _literal(body, match.end() - 1)
        else:
            end = body.index(b">", match.end())
            raw = bytes.fromhex(re.sub(rb"\s", b"", body[match.end():end]).decode())
        out[match.group(1).decode()] = _text_string(raw)
    return out


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
def _program_kind(program: bytes) -> Optional[str]:
    head = program[:4]
    if head in (b"\x00\x01\x00\x00", b"true"):
        return "truetype"
    if head == b"OTTO":
        return "cff-opentype"
    if program[:1] == b"\x01":
        return "cff"
    if program[:2] == b"%!":
        return "type1"
    return None


def _font(pdf: _Pdf, number: int) -> PdfFont:
    body = pdf.dictionary(number)
    subtype = re.search(rb"/Subtype\s*/(\w+)", body)
    subtype = subtype.group(1).decode() if subtype else "?"
    name = re.search(rb"/BaseFont\s*/(?:[A-Z]{6}\+)?([^\s/<>\[\]()]+)", body)
    name = name.group(1).decode() if name else "?"
    descendant = None
    described = body
    if subtype == "Type0":
        array = re.search(rb"/DescendantFonts\s*\[\s*(\d+)\s+\d+\s+R", body)
        if array is None:
            number_ref = pdf.ref(body, "DescendantFonts")
            inner = pdf.dictionary(number_ref) if number_ref is not None else b""
            array = re.search(rb"(\d+)\s+\d+\s+R", inner)
        if array:
            described = pdf.dictionary(int(array.group(1)))
            kind = re.search(rb"/Subtype\s*/(\w+)", described)
            descendant = kind.group(1).decode() if kind else None
    font = PdfFont(name=name, subtype=subtype, descendant=descendant, program=None, program_kind=None)
    if subtype == "Type3":
        font.problems.append("Type 3 font (print checks expect TrueType or Type 1)")
        return font
    descriptor = pdf.ref(described, "FontDescriptor")
    descriptor = pdf.dictionary(descriptor) if descriptor is not None else b""
    for key in ("FontFile2", "FontFile3", "FontFile"):
        program_ref = pdf.ref(descriptor, key)
        if program_ref is not None:
            font.program = key
            font.program_kind = _program_kind(pdf.stream(program_ref))
            break
    if font.program is None:
        font.problems.append("not embedded")
        return font
    # The declared type has to match the embedded program
    truetype_slot = font.program == "FontFile2" or descendant == "CIDFontType2" or subtype == "TrueType"
    if font.program == "FontFile2" and font.program_kind != "truetype":
        font.problems.append("{0} data in a TrueType slot (a damaged font)".format(font.program_kind))
    elif truetype_slot and font.program != "FontFile2":
        font.problems.append("declared TrueType but embedded as {0}".format(font.program))
    elif descendant == "CIDFontType0" and font.program_kind == "truetype":
        font.problems.append("TrueType data in a CFF slot (a damaged font)")
    return font


def _to_unicode(pdf: _Pdf, number: int):
    """(code width in bytes, {code: text}) from a font's ToUnicode CMap.

    Composite (Type0) fonts use two-byte codes, all others one byte;
    the code space range of the CMap is not reliable for that (matplotlib
    declares two bytes for its one-byte Type 3 fonts).
    """
    font = pdf.dictionary(number)
    width = 2 if re.search(rb"/Subtype\s*/Type0", font) else 1
    cmap_ref = pdf.ref(font, "ToUnicode")
    if cmap_ref is None:
        return width, {}
    cmap = pdf.stream(cmap_ref)

    def text(hexdigits: bytes) -> str:
        return bytes.fromhex(hexdigits.decode()).decode("utf-16-be", "replace")

    table = {}
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", cmap, re.S):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block):
            table[int(src, 16)] = text(dst)
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", cmap, re.S):
        for lo, hi, rest in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]*>|\[[^\]]*\])", block):
            lo, hi = int(lo, 16), int(hi, 16)
            if rest.startswith(b"["):
                for k, dst in enumerate(re.findall(rb"<([0-9A-Fa-f]*)>", rest)):
                    table[lo + k] = text(dst)
            else:
                start = bytes.fromhex(rest[1:-1].decode())
                for k in range(hi - lo + 1):
                    code = int.from_bytes(start, "big") + k
                    table[lo + k] = code.to_bytes(len(start), "big").decode("utf-16-be", "replace")
    return width, table


# ---------------------------------------------------------------------------
# Content streams: texts and colours
# ---------------------------------------------------------------------------
_TOKEN = re.compile(rb"\s*(%[^\r\n]*|/[^\s/<>\[\]()%{}]*|<<|>>|<[0-9A-Fa-f\s]*>|\[|\]|\(|[^\s/<>\[\]()%{}]+)")


def _tokens(data: bytes):
    """Tokens of a content stream: ("str", bytes), ("name", ...), ("num", float), ("op", ...), brackets."""
    i = 0
    while i < len(data):
        match = _TOKEN.match(data, i)
        if not match or not match.group(1):
            break
        token = match.group(1)
        i = match.end()
        if token == b"(":
            raw, i = _literal(data, match.start(1))
            yield "str", raw
        elif token.startswith(b"%"):
            continue
        elif token.startswith(b"<") and token != b"<<":
            digits = re.sub(rb"[\s<>]", b"", token).decode()
            yield "str", bytes.fromhex(digits + "0" * (len(digits) % 2))   # an odd last digit means 0
        elif token.startswith(b"/"):
            yield "name", token[1:].decode("latin-1")
        elif token in (b"[", b"]", b"<<", b">>"):
            yield token.decode(), token
        else:
            try:
                yield "num", float(token)
            except ValueError:
                yield "op", token.decode("latin-1")


def _hex_color(values) -> str:
    return "#" + "".join("{0:02x}".format(max(0, min(255, round(v * 255)))) for v in values)


def _read_content(pdf: _Pdf, data: bytes, fonts: Dict[str, tuple], xobjects: Dict[str, int],
                  texts: List[str], colors: Set[str], state=None, depth: int = 0) -> bool:
    """Collect the texts and the painted colours of one content stream.

    Only colours that paint something count: the current stroke and fill
    colours are followed through q/Q (save and restore), and added when a
    path is stroked or filled, text is shown or a form (e.g. a marker
    symbol) is drawn with them. Returns True if CMYK is used.
    """
    state = dict(state or {"stroke": "#000000", "fill": "#000000"})
    saved = []
    stack: list = []
    block: List[str] = []
    in_text = False
    current = (1, {})
    cmyk = False
    array = None
    for kind, value in _tokens(data):
        if kind == "[":
            array = []
            continue
        if kind == "]":
            stack.append(("array", array))
            array = None
            continue
        if array is not None:
            array.append((kind, value))
            continue
        if kind != "op":
            stack.append((kind, value))
            continue
        numbers = [v for k, v in stack if k == "num"]
        if value == "q":
            saved.append(dict(state))
        elif value == "Q" and saved:
            state = saved.pop()
        elif value == "BT":
            in_text, block = True, []
        elif value == "ET":
            if in_text and block:
                texts.append("".join(block))
            in_text = False
        elif value == "Tf":
            names = [v for k, v in stack if k == "name"]
            if names:
                current = fonts.get(names[-1], (1, {}))
        elif value in ("Tj", "'", '"', "TJ"):
            colors.add(state["fill"])
            strings = [v for k, v in stack if k == "str"]
            for k, v in stack:
                if k == "array":
                    strings += [s for kk, s in v if kk == "str"]
            width, table = current
            for raw in strings:
                for j in range(0, len(raw) - width + 1, width):
                    code = int.from_bytes(raw[j:j + width], "big")
                    block.append(table.get(code, chr(code) if width == 1 else ""))
        elif value in ("rg", "sc", "scn") and len(numbers) == 3:
            state["fill"] = _hex_color(numbers)
        elif value in ("RG", "SC", "SCN") and len(numbers) == 3:
            state["stroke"] = _hex_color(numbers)
        elif value in ("g", "sc", "scn") and len(numbers) == 1:
            state["fill"] = _hex_color(numbers * 3)
        elif value in ("G", "SC", "SCN") and len(numbers) == 1:
            state["stroke"] = _hex_color(numbers * 3)
        elif value in ("k", "K"):
            cmyk = True
        elif value in ("S", "s"):
            colors.add(state["stroke"])
        elif value in ("f", "F", "f*"):
            colors.add(state["fill"])
        elif value in ("B", "B*", "b", "b*"):
            colors.update((state["stroke"], state["fill"]))
        elif value == "Do" and depth < 8:
            names = [v for k, v in stack if k == "name"]
            number = xobjects.get(names[-1]) if names else None
            form = pdf.dictionary(number) if number is not None else b""
            if re.search(rb"/Subtype\s*/Form\b", form):
                # A form (a marker symbol, a transparency group) may bring its own fonts and forms
                resources = pdf.sub_dictionary(form, "Resources")
                form_fonts = {n: _to_unicode(pdf, r) for n, r in _names(pdf, pdf.sub_dictionary(resources, "Font")).items()}
                form_xobjects = _names(pdf, pdf.sub_dictionary(resources, "XObject"))
                cmyk |= _read_content(pdf, pdf.stream(number), form_fonts or fonts, form_xobjects or xobjects,
                                      texts, colors, state, depth + 1)
        stack = []
    return cmyk


def _names(pdf: _Pdf, table: bytes) -> Dict[str, int]:
    """Resource names and the objects they refer to, e.g. {"F1": 12}."""
    return {name.decode(): int(ref) for name, ref in re.findall(rb"/([^\s/<>\[\]()]+)" + _REF, table)}


def read_pdf(path) -> PdfContent:
    """Read the fonts, texts, colours and document information of a PDF file."""
    with open(path, "rb") as f:
        pdf = _Pdf(f.read())
    fonts: Dict[int, PdfFont] = {}
    for number, body in pdf.objects.items():
        if re.search(rb"/Type\s*/Font\b", pdf.dictionary(number)) and not re.search(
                rb"/Subtype\s*/CIDFontType", pdf.dictionary(number)):
            fonts[number] = _font(pdf, number)
    texts: List[str] = []
    colors: Set[str] = set()
    cmyk = False
    pages = [n for n in pdf.objects if re.search(rb"/Type\s*/Page\b(?!s)", pdf.dictionary(n))]
    for page in pages:
        page_dict = pdf.dictionary(page)
        resources = pdf.sub_dictionary(page_dict, "Resources")
        by_name = {name: _to_unicode(pdf, ref) for name, ref in _names(pdf, pdf.sub_dictionary(resources, "Font")).items()}
        xobjects = _names(pdf, pdf.sub_dictionary(resources, "XObject"))
        contents = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+\d+\s+R)", page_dict)
        refs = [int(n) for n in re.findall(rb"(\d+)\s+\d+\s+R", contents.group(1))] if contents else []
        if len(refs) == 1 and pdf.stream(refs[0]) == b"" and b"[" in pdf.dictionary(refs[0]):
            refs = [int(n) for n in re.findall(rb"(\d+)\s+\d+\s+R", pdf.dictionary(refs[0]))]
        for ref in refs:
            cmyk |= _read_content(pdf, pdf.stream(ref), by_name, xobjects, texts, colors)
    return PdfContent(pages=len(pages), info=_info(pdf), fonts=list(fonts.values()), texts=texts,
                      colors=colors, cmyk=cmyk)


# ---------------------------------------------------------------------------
# Writing the document information
# ---------------------------------------------------------------------------
def _pdf_string(text: str) -> bytes:
    """A PDF text string: plain ASCII in parentheses, anything else as UTF-16 hex."""
    try:
        raw = text.encode("ascii")
    except UnicodeEncodeError:
        return b"<FEFF" + text.encode("utf-16-be").hex().upper().encode() + b">"
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def replace_info(path, info: Dict[str, str]):
    """Write a PDF file again with ``info`` as its document information.

    ``info`` replaces all old entries (creation dates, producer strings);
    the file identifier is dropped too, so the same content gives the same
    file. Objects keep their numbers and content; a new cross-reference
    table is written.
    """
    with open(path, "rb") as f:
        data = f.read()
    pdf = _Pdf(data)
    trailer = re.findall(rb"trailer\s*<<(.*?)>>\s*startxref", data, re.S)
    root = pdf.ref(trailer[-1], "Root") if trailer else None
    if root is None or pdf.first_object is None:
        raise ValueError("The PDF file has no readable trailer.")
    info_number = pdf.ref(trailer[-1], "Info") or max(pdf.objects) + 1
    entries = b"".join(b"/" + key.encode("ascii") + b" " + _pdf_string(value) + b"\n"
                       for key, value in sorted(info.items()) if value is not None)
    objects = dict(pdf.objects)
    objects[info_number] = b"\n<<" + entries + b">>\n"
    out = bytearray(data[:pdf.first_object])
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj" % number + objects[number] + b"endobj\n"
    size = max(objects) + 1
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for number in range(1, size):
        out += (b"%010d 00000 n \n" % offsets[number]) if number in offsets else b"0000000000 00000 f \n"
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        size, root, info_number, xref)
    with open(path, "wb") as f:
        f.write(bytes(out))
