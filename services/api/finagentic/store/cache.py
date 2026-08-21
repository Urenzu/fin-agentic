"""Where raw EDGAR payloads live between requests.

Three things pushed this out of `EdgarClient`, where it was two near-identical
blocks of `Path.exists()` / `read_text()` / `write_text()`:

*Repeated parsing.* `companyfacts` for a large filer is 3-4MB of JSON. Reading
and parsing it from disk on every ingest costs more than the arithmetic it
feeds. A small in-memory layer in front of the disk removes that entirely for
the companies anyone is actually looking at.

*Deployability.* A directory on local disk does not survive a container
restart, is not shared between instances, and cannot be warmed ahead of demand.
Naming the operations behind a protocol means the disk store can be replaced by
Postgres or object storage without touching a single call site.

*Testability.* Nothing above this file needs a temporary directory any more.

Payloads are stored as text because that is what EDGAR returns and what the
parsers consume; encoding to bytes at this boundary would mean decoding again
immediately on the way back out.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Protocol


class BlobCache(Protocol):
    """A keyed store of raw payloads.

    `get` returning None means "not here", never "empty". EDGAR documents are
    never legitimately empty, so the two do not need telling apart.
    """

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...


class NullCache:
    """Caches nothing. The default, so nothing is written unless asked."""

    def get(self, key: str) -> str | None:
        return None

    def put(self, key: str, value: str) -> None:
        return None


class MemoryCache:
    """A bounded LRU, sized in characters rather than entries.

    Entry counts are the wrong unit here: `company_tickers.json` and a single
    rendered exhibit differ by three orders of magnitude, so a limit of "200
    entries" is either far too much memory or far too little cache depending on
    which arrives first.

    An item larger than the whole budget is not stored -- caching it would
    evict everything else to hold one thing.
    """

    def __init__(self, max_chars: int = 64_000_000) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        self._max_chars = max_chars
        self._entries: OrderedDict[str, str] = OrderedDict()
        self._size = 0
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return self._size

    def get(self, key: str) -> str | None:
        with self._lock:
            value = self._entries.get(key)
            if value is not None:
                self._entries.move_to_end(key)
            return value

    def put(self, key: str, value: str) -> None:
        if len(value) > self._max_chars:
            return
        with self._lock:
            existing = self._entries.pop(key, None)
            if existing is not None:
                self._size -= len(existing)
            self._entries[key] = value
            self._size += len(value)
            while self._size > self._max_chars:
                _, evicted = self._entries.popitem(last=False)
                self._size -= len(evicted)


class DiskCache:
    """Payloads as files in a directory.

    Keys arrive from the fetch layer and are composed from accession numbers and
    filenames, so they are already tame -- but they are still built from data
    EDGAR supplied, and a key containing a separator would write outside the
    directory. Sanitising here means callers do not have to remember to.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._directory / f"{_safe(key)}.cache"

    def get(self, key: str) -> str | None:
        path = self._path(key)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            # A cache is an optimisation. A file that cannot be read is a miss,
            # not an outage.
            return None

    def put(self, key: str, value: str) -> None:
        path = self._path(key)
        # Written beside the target and moved into place, so a process killed
        # mid-write leaves no half-file that would later be served as a
        # complete document.
        temporary = path.with_suffix(".partial")
        try:
            temporary.write_text(value, encoding="utf-8")
            temporary.replace(path)
        except OSError:
            temporary.unlink(missing_ok=True)


class LayeredCache:
    """Reads through the layers in order; writes to all of them.

    In practice this is memory in front of disk. A hit in a later layer is
    promoted into the earlier ones, so the second reader of a company pays the
    disk read but the third does not.
    """

    def __init__(self, *layers: BlobCache) -> None:
        if not layers:
            raise ValueError("a layered cache needs at least one layer")
        self._layers = layers

    def get(self, key: str) -> str | None:
        for index, layer in enumerate(self._layers):
            value = layer.get(key)
            if value is not None:
                for nearer in self._layers[:index]:
                    nearer.put(key, value)
                return value
        return None

    def put(self, key: str, value: str) -> None:
        for layer in self._layers:
            layer.put(key, value)


def _safe(key: str) -> str:
    return "".join(character if character.isalnum() or character in "-_." else "_" for character in key)


def build_cache(directory: Path | None, *, max_memory_chars: int = 64_000_000) -> BlobCache:
    """The cache the application runs with.

    Memory alone when no directory is configured, which is what the tests and
    any read-only deployment want.
    """
    memory = MemoryCache(max_memory_chars)
    if directory is None:
        return memory
    return LayeredCache(memory, DiskCache(directory))


__all__ = [
    "BlobCache",
    "DiskCache",
    "LayeredCache",
    "MemoryCache",
    "NullCache",
    "build_cache",
]
