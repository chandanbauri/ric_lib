"""Test suite for ric_lib — size-capped LRU cache."""

import json
import unittest

import ric_lib


def make_cache(limit: int):
    return ric_lib.init_cache(limit)


def _byte_size(val: dict) -> int:
    """JSON-serialised byte length, mirroring the Rust encode step."""
    return len(json.dumps(val, separators=(",", ":")).encode())


# ---------------------------------------------------------------------------
# Basic insert / get
# ---------------------------------------------------------------------------

class TestBasicInsertAndGet(unittest.TestCase):

    def test_insert_and_retrieve(self):
        cache = make_cache(1000)
        cache.insert("k1", {"a": 1})
        self.assertEqual(cache.get("k1"), {"a": 1})

    def test_missing_key_raises_key_error(self):
        cache = make_cache(1000)
        with self.assertRaises(KeyError):
            cache.get("missing")

    def test_size_reflects_payload_bytes(self):
        cache = make_cache(1000)
        val = {"hello": "world"}
        cache.insert("k1", val)
        self.assertEqual(cache.size(), _byte_size(val))

    def test_multiple_inserts_accumulate_size(self):
        cache = make_cache(1000)
        v1, v2 = {"x": "1"}, {"y": "2"}
        cache.insert("k1", v1)
        cache.insert("k2", v2)
        self.assertEqual(cache.size(), _byte_size(v1) + _byte_size(v2))

    def test_empty_cache_size_is_zero(self):
        cache = make_cache(1000)
        self.assertEqual(cache.size(), 0)

    def test_len_and_is_empty(self):
        cache = make_cache(1000)
        self.assertTrue(cache.is_empty())
        self.assertEqual(len(cache), 0)
        cache.insert("k1", {"a": 1})
        self.assertFalse(cache.is_empty())
        self.assertEqual(len(cache), 1)

    def test_contains_and_dunder_contains(self):
        cache = make_cache(1000)
        cache.insert("k1", {"a": 1})
        self.assertTrue(cache.contains("k1"))
        self.assertIn("k1", cache)
        self.assertNotIn("k2", cache)

    def test_repr(self):
        cache = make_cache(500)
        self.assertIn("Cache(limit=500", repr(cache))

    def test_various_value_types(self):
        cache = make_cache(1000)
        cache.insert("str", "hello")
        cache.insert("int", 42)
        cache.insert("list", [1, 2, 3])
        cache.insert("nested", {"a": {"b": [1, 2]}})
        self.assertEqual(cache.get("str"), "hello")
        self.assertEqual(cache.get("int"), 42)
        self.assertEqual(cache.get("list"), [1, 2, 3])
        self.assertEqual(cache.get("nested"), {"a": {"b": [1, 2]}})


# ---------------------------------------------------------------------------
# Remove / clear
# ---------------------------------------------------------------------------

class TestRemoveAndClear(unittest.TestCase):

    def test_remove_existing_key(self):
        cache = make_cache(1000)
        v = {"x": 1}
        cache.insert("k1", v)
        self.assertTrue(cache.remove("k1"))
        with self.assertRaises(KeyError):
            cache.get("k1")

    def test_remove_nonexistent_key_returns_false(self):
        cache = make_cache(1000)
        self.assertFalse(cache.remove("ghost"))

    def test_remove_reclaims_size(self):
        cache = make_cache(1000)
        v = {"x": "y"}
        cache.insert("k1", v)
        cache.remove("k1")
        self.assertEqual(cache.size(), 0)

    def test_clear_empties_cache(self):
        cache = make_cache(1000)
        cache.insert("k1", {"a": 1})
        cache.insert("k2", {"b": 2})
        cache.clear()
        self.assertTrue(cache.is_empty())
        self.assertEqual(cache.size(), 0)
        self.assertEqual(len(cache), 0)


# ---------------------------------------------------------------------------
# Duplicate key overwrite
# ---------------------------------------------------------------------------

class TestDuplicateKeyOverwrite(unittest.TestCase):

    def test_overwrite_returns_new_value(self):
        cache = make_cache(1000)
        cache.insert("k1", {"v": 1})
        cache.insert("k1", {"v": 2})
        self.assertEqual(cache.get("k1"), {"v": 2})

    def test_overwrite_does_not_double_count_size(self):
        cache = make_cache(1000)
        cache.insert("k1", {"v": 1})
        cache.insert("k1", {"value": 9999})
        self.assertEqual(cache.size(), _byte_size({"value": 9999}))

    def test_overwrite_len_stays_one(self):
        cache = make_cache(1000)
        cache.insert("k1", {"v": 1})
        cache.insert("k1", {"v": 2})
        self.assertEqual(len(cache), 1)


# ---------------------------------------------------------------------------
# LRU eviction ordering
# ---------------------------------------------------------------------------

class TestLRUEviction(unittest.TestCase):

    def test_lru_node_evicted_when_limit_exceeded(self):
        v1, v2, v3 = {"a": "1"}, {"b": "2"}, {"c": "3"}
        limit = _byte_size(v1) + _byte_size(v2)
        cache = make_cache(limit)
        cache.insert("k1", v1)   # LRU
        cache.insert("k2", v2)
        cache.insert("k3", v3)   # should evict k1
        with self.assertRaises(KeyError):
            cache.get("k1")
        self.assertEqual(cache.get("k2"), v2)
        self.assertEqual(cache.get("k3"), v3)

    def test_get_promotes_entry_protecting_it_from_eviction(self):
        v1, v2, v3 = {"a": "1"}, {"b": "2"}, {"c": "3"}
        limit = _byte_size(v1) + _byte_size(v2)
        cache = make_cache(limit)
        cache.insert("k1", v1)
        cache.insert("k2", v2)
        cache.get("k1")           # promote k1 → k2 becomes LRU
        cache.insert("k3", v3)   # should evict k2
        self.assertEqual(cache.get("k1"), v1)
        with self.assertRaises(KeyError):
            cache.get("k2")
        self.assertEqual(cache.get("k3"), v3)

    def test_size_never_exceeds_limit(self):
        v = {"key": "val"}
        limit = _byte_size(v) * 3
        cache = make_cache(limit)
        for i in range(10):
            cache.insert(f"k{i}", v)
            self.assertLessEqual(cache.size(), limit)

    def test_multiple_evictions_until_room(self):
        v = {"x": "y"}
        sz = _byte_size(v)
        cache = make_cache(sz * 2)
        cache.insert("k1", v)
        cache.insert("k2", v)
        cache.insert("k3", v)    # evicts k1
        with self.assertRaises(KeyError):
            cache.get("k1")
        self.assertLessEqual(cache.size(), sz * 2)


# ---------------------------------------------------------------------------
# Size limit enforcement
# ---------------------------------------------------------------------------

class TestSizeLimitEnforcement(unittest.TestCase):

    def test_item_larger_than_limit_raises_value_error(self):
        cache = make_cache(5)
        with self.assertRaises(ValueError):
            cache.insert("big", {"this": "will never fit"})

    def test_item_exactly_at_limit_is_accepted(self):
        v = {"a": "b"}
        limit = _byte_size(v)
        cache = make_cache(limit)
        cache.insert("k1", v)
        self.assertEqual(cache.get("k1"), v)

    def test_size_stays_zero_after_rejected_insert(self):
        cache = make_cache(3)
        try:
            cache.insert("k1", {"too": "large"})
        except ValueError:
            pass
        self.assertEqual(cache.size(), 0)

    def test_limit_attribute_is_readable(self):
        cache = make_cache(12345)
        self.assertEqual(cache.limit, 12345)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):

    def test_single_insert_then_evict_empties_cache(self):
        v1 = {"a": "1"}
        v2 = {"b": "2"}
        cache = make_cache(_byte_size(v1))
        cache.insert("k1", v1)
        cache.insert("k2", v2)    # evicts k1
        self.assertEqual(cache.size(), _byte_size(v2))
        with self.assertRaises(KeyError):
            cache.get("k1")

    def test_reinsert_after_eviction(self):
        v = {"x": "y"}
        sz = _byte_size(v)
        cache = make_cache(sz)
        cache.insert("k1", v)
        cache.insert("k2", v)    # evicts k1
        cache.insert("k1", v)    # re-insert should succeed
        self.assertEqual(cache.get("k1"), v)

    def test_insert_after_clear(self):
        cache = make_cache(1000)
        cache.insert("k1", {"a": 1})
        cache.clear()
        cache.insert("k1", {"b": 2})
        self.assertEqual(cache.get("k1"), {"b": 2})

    def test_get_on_empty_cache_raises_key_error(self):
        cache = make_cache(1000)
        with self.assertRaises(KeyError):
            cache.get("anything")

    def test_default_limit_is_one_megabyte(self):
        cache = ric_lib.init_cache()
        self.assertEqual(cache.limit, 1_000_000)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
