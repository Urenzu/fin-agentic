"""The blob cache holding raw EDGAR payloads."""

from __future__ import annotations

import pytest

from finagentic.store.cache import (
    DiskCache,
    LayeredCache,
    MemoryCache,
    NullCache,
    build_cache,
)


class CountingCache:
    """Records what was asked of it, so promotion can be observed."""

    def __init__(self, **initial: str) -> None:
        self.entries = dict(initial)
        self.gets: list[str] = []
        self.puts: list[str] = []

    def get(self, key: str) -> str | None:
        self.gets.append(key)
        return self.entries.get(key)

    def put(self, key: str, value: str) -> None:
        self.puts.append(key)
        self.entries[key] = value


# ---------------------------------------------------------------------------
# memory
# ---------------------------------------------------------------------------


def test_a_stored_payload_comes_back():
    cache = MemoryCache()
    cache.put("facts", "{}")
    assert cache.get("facts") == "{}"


def test_a_key_never_stored_is_a_miss_rather_than_an_error():
    assert MemoryCache().get("absent") is None


def test_the_budget_is_characters_not_entries():
    """A ticker map and a rendered exhibit differ by orders of magnitude, so
    counting entries would size the cache by whichever arrived first."""
    cache = MemoryCache(max_chars=100)
    cache.put("small", "x" * 10)
    cache.put("large", "y" * 80)
    assert cache.size == 90
    assert cache.get("small") is not None
    assert cache.get("large") is not None


def test_the_least_recently_used_entry_is_evicted_first():
    cache = MemoryCache(max_chars=100)
    cache.put("a", "x" * 50)
    cache.put("b", "y" * 50)
    cache.get("a")  # "b" is now the stale one
    cache.put("c", "z" * 50)

    assert cache.get("a") is not None
    assert cache.get("b") is None
    assert cache.get("c") is not None


def test_replacing_a_key_does_not_double_count_its_size():
    cache = MemoryCache(max_chars=100)
    cache.put("a", "x" * 40)
    cache.put("a", "y" * 40)
    assert cache.size == 40


def test_something_larger_than_the_whole_budget_is_not_stored():
    # Holding it would mean evicting everything else for one item.
    cache = MemoryCache(max_chars=100)
    cache.put("keep", "x" * 50)
    cache.put("huge", "y" * 500)

    assert cache.get("huge") is None
    assert cache.get("keep") is not None


def test_eviction_keeps_the_recorded_size_honest():
    cache = MemoryCache(max_chars=100)
    for index in range(20):
        cache.put(f"k{index}", "x" * 30)
    assert cache.size <= 100
    assert cache.size >= 0


def test_a_cache_that_could_hold_nothing_is_rejected():
    with pytest.raises(ValueError):
        MemoryCache(max_chars=0)


# ---------------------------------------------------------------------------
# disk
# ---------------------------------------------------------------------------


def test_disk_survives_a_new_instance_over_the_same_directory(tmp_path):
    """The whole point of the disk layer: outliving the process."""
    DiskCache(tmp_path).put("facts", "payload")
    assert DiskCache(tmp_path).get("facts") == "payload"


def test_a_key_carrying_a_separator_cannot_write_outside_the_directory(tmp_path):
    root = tmp_path / "cache"
    cache = DiskCache(root)
    cache.put("../../escape", "payload")

    assert cache.get("../../escape") == "payload"
    assert not (tmp_path.parent / "escape.cache").exists()
    assert list(root.iterdir())


def test_keys_that_differ_only_by_punctuation_do_not_collide(tmp_path):
    cache = DiskCache(tmp_path)
    cache.put("report_0001_R2.htm", "two")
    cache.put("report_0001_R3.htm", "three")
    assert cache.get("report_0001_R2.htm") == "two"
    assert cache.get("report_0001_R3.htm") == "three"


def test_a_half_written_file_is_never_served(tmp_path):
    """Payloads are written beside the target and moved into place, so a
    process killed mid-write leaves no truncated document to be read back."""
    cache = DiskCache(tmp_path)
    cache.put("facts", "complete")
    assert not list(tmp_path.glob("*.partial"))
    assert cache.get("facts") == "complete"


def test_unicode_survives_the_round_trip(tmp_path):
    # Filer labels carry a curly apostrophe and a non-breaking space. Built
    # from codepoints so the exact characters under test are unambiguous.
    label = "SHAREHOLDERS" + chr(0x2019) + " EQUITY" + chr(0xA0)
    cache = DiskCache(tmp_path)
    cache.put("k", label)
    assert cache.get("k") == label


# ---------------------------------------------------------------------------
# layering
# ---------------------------------------------------------------------------


def test_a_hit_in_a_later_layer_is_promoted_into_the_earlier_ones():
    near = CountingCache()
    far = CountingCache(facts="payload")
    layered = LayeredCache(near, far)

    assert layered.get("facts") == "payload"
    assert near.puts == ["facts"]

    far.gets.clear()
    assert layered.get("facts") == "payload"
    assert far.gets == []


def test_a_write_reaches_every_layer():
    near, far = CountingCache(), CountingCache()
    LayeredCache(near, far).put("facts", "payload")
    assert near.puts == ["facts"] and far.puts == ["facts"]


def test_a_miss_everywhere_is_a_miss():
    layered = LayeredCache(CountingCache(), CountingCache())
    assert layered.get("absent") is None


def test_the_nearest_layer_short_circuits_the_rest():
    near = CountingCache(facts="near")
    far = CountingCache(facts="far")
    layered = LayeredCache(near, far)

    assert layered.get("facts") == "near"
    assert far.gets == []


def test_a_layered_cache_needs_at_least_one_layer():
    with pytest.raises(ValueError):
        LayeredCache()


# ---------------------------------------------------------------------------
# construction
# ---------------------------------------------------------------------------


def test_without_a_directory_the_cache_is_memory_only():
    cache = build_cache(None)
    cache.put("k", "v")
    assert cache.get("k") == "v"
    assert isinstance(cache, MemoryCache)


def test_with_a_directory_payloads_reach_the_disk(tmp_path):
    build_cache(tmp_path).put("k", "v")
    assert DiskCache(tmp_path).get("k") == "v"


def test_the_null_cache_forgets_everything():
    cache = NullCache()
    cache.put("k", "v")
    assert cache.get("k") is None
