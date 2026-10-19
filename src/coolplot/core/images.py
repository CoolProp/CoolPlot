# -*- coding: utf-8 -*-
"""Pictures a chart can carry: a logo and a watermark.

A :class:`Picture` is the bytes of one PNG or SVG file plus its size in
pixels, read once when the chart settings name it. The size is all the
layout needs (the aspect ratio); the backends decode the bytes themselves,
matplotlib through its own image reader, the SVG writer by embedding them.

Only PNG and SVG are accepted. Both are read without any third party
library: PNG from its header, SVG from the ``viewBox`` (or ``width`` and
``height``) of its root element.

This module is plain Python; no CoolProp, no plotting library.
"""
from __future__ import annotations

import base64
import os
import re
import struct
from dataclasses import dataclass
from functools import lru_cache
from typing import Tuple, Union

PNG = "image/png"
SVG = "image/svg+xml"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"


@dataclass(frozen=True)
class Picture:
    """The bytes of one PNG or SVG image and its size in pixels

    Attributes
    ----------
    data : bytes
        The file content.
    mime : str
        "image/png" or "image/svg+xml".
    width_px, height_px : float
        The size the image declares: the pixel size of a PNG, the
        ``viewBox`` (or ``width`` and ``height``) of an SVG.
    """
    data: bytes
    mime: str
    width_px: float
    height_px: float

    def __post_init__(self):
        if self.mime not in (PNG, SVG):
            raise ValueError("Picture: only PNG and SVG are supported, not {0!r}.".format(self.mime))
        if not (self.width_px > 0.0 and self.height_px > 0.0):
            raise ValueError("Picture: the size has to be positive, not {0} x {1}.".format(
                self.width_px, self.height_px))

    @property
    def aspect(self) -> float:
        """Height divided by width."""
        return self.height_px / self.width_px

    def data_uri(self) -> str:
        """The image as a ``data:`` URI, for embedding in SVG or HTML."""
        return "data:{0};base64,{1}".format(self.mime, base64.b64encode(self.data).decode("ascii"))

    def __repr__(self):
        return "Picture({0}, {1:g} x {2:g}, {3} bytes)".format(
            self.mime, self.width_px, self.height_px, len(self.data))


def picture_from_bytes(data: bytes) -> Picture:
    """A :class:`Picture` from the content of a PNG or SVG file."""
    data = bytes(data)
    if data.startswith(_PNG_SIGNATURE):
        # The IHDR chunk comes first: length, b"IHDR", then width and height
        if len(data) < 24 or data[12:16] != b"IHDR":
            raise ValueError("Picture: a PNG without its IHDR header.")
        width, height = struct.unpack(">II", data[16:24])
        return Picture(data, PNG, float(width), float(height))
    width, height = _svg_size(data)
    return Picture(data, SVG, width, height)


def load_picture(source: Union[str, os.PathLike, bytes, Picture]) -> Picture:
    """A :class:`Picture` from a file name, a ``data:`` URI, file bytes or a Picture.

    Files are read once per name and modification time, so a chart that
    is updated often does not read its logo again on every update.
    """
    if isinstance(source, Picture):
        return source
    if isinstance(source, (bytes, bytearray)):
        return picture_from_bytes(bytes(source))
    text = os.fspath(source)
    if text.startswith("data:"):
        return picture_from_bytes(_decode_data_uri(text))
    try:
        stat = os.stat(text)
    except OSError as e:
        raise ValueError("Picture: cannot read {0!r}: {1}.".format(text, e.strerror)) from None
    return _load_file(text, stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=32)
def _load_file(path: str, mtime_ns: int, size: int) -> Picture:
    # mtime and size are part of the cache key only: a changed file is read again
    with open(path, "rb") as f:
        return picture_from_bytes(f.read())


def _decode_data_uri(uri: str) -> bytes:
    header, _, payload = uri.partition(",")
    if not header.endswith(";base64"):
        raise ValueError("Picture: only base64 data URIs are supported.")
    return base64.b64decode(payload)


def _svg_size(data: bytes) -> Tuple[float, float]:
    """(width, height) of an SVG document from its root element."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Picture: neither a PNG nor an SVG file (SVG has to be UTF-8).") from None
    match = re.search(r"<svg\b([^>]*)>", text)
    if match is None:
        raise ValueError("Picture: neither a PNG nor an SVG file.")
    attrs = match.group(1)
    view_box = re.search(r'viewBox\s*=\s*["\']([^"\']*)["\']', attrs)
    if view_box is not None:
        values = [float(v) for v in re.findall(_NUMBER, view_box.group(1))]
        if len(values) == 4 and values[2] > 0.0 and values[3] > 0.0:
            return values[2], values[3]
    sizes = []
    for name in ("width", "height"):
        found = re.search(r'\b{0}\s*=\s*["\']\s*({1})\s*(px)?\s*["\']'.format(name, _NUMBER), attrs)
        if found is None:
            raise ValueError("Picture: an SVG needs a viewBox, or a width and height in pixels.")
        sizes.append(float(found.group(1)))
    return sizes[0], sizes[1]
