# -*- coding: utf-8 -*-
"""Traced lines kept on disk between runs, the way CoolProp keeps its tables.

CoolProp's tabular backends (TTSE, BICUBIC) build their tables once and
keep them in ``~/.CoolProp/Tables``: one folder per fluid and composition,
one compressed file per table, a revision number in every file, and a
rebuild whenever a file is missing, unreadable or of another revision. The
folder has a size limit (``MAXIMUM_TABLE_DIRECTORY_SIZE_IN_GB``).

:class:`CurveStore` does the same for traced lines:

* the folder is ``~/.CoolProp/CoolPlot/Curves`` (next to CoolProp's own
  tables; it follows CoolProp's ``ALTERNATIVE_TABLES_DIRECTORY`` when that
  is set), or the environment variable ``COOLPLOT_CACHE_DIR``, or a folder
  given in the code;
* inside it, one folder per fluid named like CoolProp's, for example
  ``HEOS(R32[0.7]&R125[0.3])``;
* one zlib-compressed JSON file per line, named by a digest of everything
  the line depends on (the engine's cache key, which includes CoolProp's
  version, configuration and reference state);
* each file holds a revision number and the full key: a file of another
  revision, of another key (a digest collision) or one that cannot be read
  is ignored, and the line is traced again and the file replaced;
* writes go to a temporary file that is then renamed, so a second process
  never reads half a file;
* above CoolProp's size limit a warning says so; above 1.5 times the limit
  no more lines are written (CoolProp stops with an error there; a chart
  should not fail because its cache is full).

The store is optional. A script that draws one chart gains nothing from
it; an interactive application, a notebook that restarts, or a batch of
reports for the same fluid draws again without tracing anything.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import tempfile
import threading
import warnings
import zlib
from typing import Any, Hashable, Optional

from ..thermo.fluid import coolprop_home_dir, coolprop_table_limit_GB
from ..thermo.isolines import Curve

#: Bump when the stored record changes; files of another revision are traced again.
REVISION = 1

#: File name ending of a stored line.
SUFFIX = ".json.z"

#: Environment variable that switches the store on for every new cache and names its folder.
ENVIRONMENT_VARIABLE = "COOLPLOT_CACHE_DIR"


def default_directory() -> str:
    """The folder of the store: ``COOLPLOT_CACHE_DIR``, or ~/.CoolProp/CoolPlot/Curves."""
    chosen = os.environ.get(ENVIRONMENT_VARIABLE, "").strip()
    if chosen:
        return os.path.abspath(os.path.expanduser(chosen))
    return os.path.join(coolprop_home_dir(), "CoolPlot", "Curves")


def key_text(key: Hashable) -> str:
    """The cache key as canonical JSON text, the same in every process.

    Numbers are written with ``repr``, so they keep every bit; specs are
    written through their contract records (``to_dict``). Raises TypeError
    for a key part that has no stable text, which keeps that line off disk.
    """
    return json.dumps(_canonical(key), sort_keys=True, separators=(",", ":"))


def _canonical(value: Any):
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return repr(value)   # every bit, and NaN or infinity as text
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if hasattr(value, "to_dict"):
        return {"type": type(value).__name__, "record": _canonical(value.to_dict())}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"type": type(value).__name__,
                "record": {f.name: _canonical(getattr(value, f.name)) for f in dataclasses.fields(value)}}
    if hasattr(value, "item"):   # a numpy number
        return _canonical(value.item())
    raise TypeError("No stable text for a cache key part of type {0}.".format(type(value).__name__))


def fluid_folder(fluid_spec) -> str:
    """The folder name of a fluid, like CoolProp's table folders: "HEOS(R32[0.7]&R125[0.3])"."""
    if getattr(fluid_spec, "kind", "fluid") == "humid_air":
        name = "HumidAir(p={0!r})".format(float(fluid_spec.p_Pa))
    else:
        components = list(getattr(fluid_spec, "components", ()) or ())
        fractions = list(getattr(fluid_spec, "fractions", ()) or ())
        if fractions and len(fractions) == len(components):
            parts = ["{0}[{1:.10f}]".format(c, f) for c, f in zip(components, fractions)]
        else:
            parts = components or [str(fluid_spec)]
        name = "{0}({1})".format(getattr(fluid_spec, "backend", "HEOS"), "&".join(parts))
    # Characters every file system accepts; a long name keeps a digest of the rest
    safe = re.sub(r"[^A-Za-z0-9._()&\[\]=,+-]", "_", name)
    if len(safe) > 100:
        safe = safe[:80] + "~" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    return safe


class CurveStore:
    """Traced lines on disk, one compressed file per line, see the module docstring

    Parameters
    ----------
    directory : str, optional
        The folder of the store; :func:`default_directory` when None.
    """

    def __init__(self, directory: Optional[str] = None):
        self.directory = os.path.abspath(os.path.expanduser(directory)) if directory else default_directory()
        self.limit_GB = coolprop_table_limit_GB()
        self.loaded = 0      # lines read from disk
        self.saved = 0       # lines written
        self.rejected = 0    # files that were there but could not be used
        self._size_bytes = None   # measured on the first write
        self._lock = threading.Lock()
        self._warned = set()
        self._writable = True

    def __repr__(self):
        return "CurveStore({0!r})".format(self.directory)

    # Paths -------------------------------------------------------------------
    def path(self, key: Hashable):
        """(file path, key text) of a line, or (None, None) when the key has no stable text."""
        try:
            text = key_text(key)
        except TypeError:
            return None, None
        fluid = key[0] if isinstance(key, tuple) and key else None
        folder = os.path.join(self.directory, fluid_folder(fluid) if fluid is not None else "_")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
        return os.path.join(folder, digest + SUFFIX), text

    # Reading ------------------------------------------------------------------
    def load(self, key: Hashable) -> Optional[Curve]:
        """The line stored for ``key``, or None (not stored, unreadable, another revision or key)."""
        path, text = self.path(key)
        if path is None or not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as f:
                record = json.loads(zlib.decompress(f.read()).decode("utf-8"))
            if record.get("revision") != REVISION or record.get("key") != text:
                raise ValueError("another revision or key")
            curve = Curve.from_dict(record["curve"])
        except (OSError, zlib.error, ValueError, KeyError, TypeError, AttributeError):
            # Like CoolProp with a table it cannot load: trace again, and the
            # new file replaces this one
            with self._lock:
                self.rejected += 1
            return None
        with self._lock:
            self.loaded += 1
        return curve

    # Writing ------------------------------------------------------------------
    def save(self, key: Hashable, curve: Curve) -> bool:
        """Write a line; returns whether it was written."""
        if not self._writable:
            return False
        path, text = self.path(key)
        if path is None:
            return False
        try:
            data = zlib.compress(json.dumps({"revision": REVISION, "key": text, "curve": curve.to_dict()},
                                            allow_nan=False, separators=(",", ":")).encode("utf-8"), 6)
        except (ValueError, TypeError):
            return False
        if not self._room_for(len(data)):
            return False
        folder = os.path.dirname(path)
        try:
            os.makedirs(folder, exist_ok=True)
            handle, temporary = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=SUFFIX)
            try:
                with os.fdopen(handle, "wb") as f:
                    f.write(data)
                os.replace(temporary, path)   # whole file or nothing, also for a second process
            except BaseException:
                try:
                    os.remove(temporary)
                except OSError:
                    pass
                raise
        except OSError as error:
            # A folder that cannot be written (read-only, full disk): stop trying, say so once
            self._writable = False
            self._warn_once("write", "Traced lines cannot be kept in {0} ({1}); they are traced again next "
                            "time.".format(self.directory, error))
            return False
        with self._lock:
            self.saved += 1
            self._size_bytes += len(data)
        return True

    def size_bytes(self) -> int:
        """Bytes of all stored lines in the folder (measured once, then counted up)."""
        with self._lock:
            if self._size_bytes is None:
                total = 0
                for root, _, files in os.walk(self.directory):
                    for name in files:
                        if name.endswith(SUFFIX):
                            try:
                                total += os.path.getsize(os.path.join(root, name))
                            except OSError:
                                pass
                self._size_bytes = total
            return self._size_bytes

    def _room_for(self, n_bytes: int) -> bool:
        """CoolProp's rule for its table folder: warn above the limit, stop above 1.5 times it."""
        size_GB = (self.size_bytes() + n_bytes) / 1024.0 ** 3
        if size_GB > 1.5 * self.limit_GB:
            self._warn_once("full", "The folder of traced lines {0} holds more than 1.5 times CoolProp's "
                            "MAXIMUM_TABLE_DIRECTORY_SIZE_IN_GB ({1:g} GB); no more lines are kept. Delete "
                            "the folder or raise the limit.".format(self.directory, self.limit_GB))
            return False
        if size_GB > self.limit_GB:
            self._warn_once("limit", "The folder of traced lines {0} holds more than CoolProp's "
                            "MAXIMUM_TABLE_DIRECTORY_SIZE_IN_GB ({1:g} GB).".format(self.directory, self.limit_GB))
        return True

    def _warn_once(self, what: str, message: str):
        if what not in self._warned:
            self._warned.add(what)
            warnings.warn(message, UserWarning, stacklevel=3)
