"""Test suite for ric_lib — item-capped LRU cache."""

import unittest
import ric_lib


def make_cache(capacity: int):
    return ric_lib.init_cache(capacity)


# ---------------------------------------------------------------------------
# Basic insert / get
# ---------------------------------------------------------------------------

class TestBasicInsertAndGet(unittest.TestCase):

    def test_insert_and_retrieve(self):
        cache = make_cache(10)
        cache.insert("k1", {"a": 1})
        self.assertEqual(cache.get("k1"), {"a": 1})

    def test_missing_key_raises_key_error(self):
        cache = make_cache(10)
        with self.assertRaises(KeyError):
            cache.get("missing")

    def test_len_and_is_empty(self):
        cache = make_cache(10)
        self.assertTrue(cache.is_empty())
        self.assertEqual(len(cache), 0)
        cache.insert("k1", {"a": 1})
        self.assertFalse(cache.is_empty())
        self.assertEqual(len(cache), 1)

    def test_contains_and_dunder_contains(self):
        cache = make_cache(10)
        cache.insert("k1", {"a": 1})
        self.assertTrue(cache.contains("k1"))
        self.assertIn("k1", cache)
        self.assertNotIn("k2", cache)

    def test_repr(self):
        cache = make_cache(5)
        self.assertIn("Cache(capacity=5", repr(cache))

    def test_various_value_types(self):
        cache = make_cache(10)
        
        class CustomObj:
            def __init__(self, val):
                self.val = val
                
        obj = CustomObj(42)
        
        cache.insert("str", "hello")
        cache.insert("int", 42)
        cache.insert("list", [1, 2, 3])
        cache.insert("nested", {"a": {"b": [1, 2]}})
        cache.insert("custom", obj)
        
        self.assertEqual(cache.get("str"), "hello")
        self.assertEqual(cache.get("int"), 42)
        self.assertEqual(cache.get("list"), [1, 2, 3])
        self.assertEqual(cache.get("nested"), {"a": {"b": [1, 2]}})
        self.assertEqual(cache.get("custom").val, 42)


# ---------------------------------------------------------------------------
# Remove / clear
# ---------------------------------------------------------------------------

class TestRemoveAndClear(unittest.TestCase):

    def test_remove_existing_key(self):
        cache = make_cache(10)
        v = {"x": 1}
        cache.insert("k1", v)
        self.assertTrue(cache.remove("k1"))
        with self.assertRaises(KeyError):
            cache.get("k1")

    def test_remove_nonexistent_key_returns_false(self):
        cache = make_cache(10)
        self.assertFalse(cache.remove("ghost"))

    def test_clear_empties_cache(self):
        cache = make_cache(10)
        cache.insert("k1", {"a": 1})
        cache.insert("k2", {"b": 2})
        cache.clear()
        self.assertTrue(cache.is_empty())
        self.assertEqual(len(cache), 0)


# ---------------------------------------------------------------------------
# Duplicate key overwrite
# ---------------------------------------------------------------------------

class TestDuplicateKeyOverwrite(unittest.TestCase):

    def test_overwrite_returns_new_value(self):
        cache = make_cache(10)
        cache.insert("k1", {"v": 1})
        cache.insert("k1", {"v": 2})
        self.assertEqual(cache.get("k1"), {"v": 2})

    def test_overwrite_len_stays_one(self):
        cache = make_cache(10)
        cache.insert("k1", {"v": 1})
        cache.insert("k1", {"v": 2})
        self.assertEqual(len(cache), 1)


# ---------------------------------------------------------------------------
# LRU eviction ordering
# ---------------------------------------------------------------------------

class TestLRUEviction(unittest.TestCase):

    def test_lru_node_evicted_when_capacity_exceeded(self):
        cache = make_cache(2)
        cache.insert("k1", "v1")   # LRU
        cache.insert("k2", "v2")
        cache.insert("k3", "v3")   # should evict k1
        
        with self.assertRaises(KeyError):
            cache.get("k1")
            
        self.assertEqual(cache.get("k2"), "v2")
        self.assertEqual(cache.get("k3"), "v3")
        self.assertEqual(len(cache), 2)

    def test_get_promotes_entry_protecting_it_from_eviction(self):
        cache = make_cache(2)
        cache.insert("k1", "v1")
        cache.insert("k2", "v2")
        cache.get("k1")           # promote k1 → k2 becomes LRU
        cache.insert("k3", "v3")   # should evict k2
        
        self.assertEqual(cache.get("k1"), "v1")
        with self.assertRaises(KeyError):
            cache.get("k2")
        self.assertEqual(cache.get("k3"), "v3")

    def test_multiple_evictions(self):
        cache = make_cache(3)
        cache.insert("k1", 1)
        cache.insert("k2", 2)
        cache.insert("k3", 3)
        cache.insert("k4", 4)
        cache.insert("k5", 5)
        
        with self.assertRaises(KeyError):
            cache.get("k1")
        with self.assertRaises(KeyError):
            cache.get("k2")
            
        self.assertEqual(len(cache), 3)


# ---------------------------------------------------------------------------
# Capacity enforcement
# ---------------------------------------------------------------------------

class TestCapacityEnforcement(unittest.TestCase):

    def test_capacity_attribute_is_readable(self):
        cache = make_cache(12345)
        self.assertEqual(cache.capacity, 12345)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):

    def test_single_insert_then_evict_empties_cache(self):
        cache = make_cache(1)
        cache.insert("k1", 1)
        cache.insert("k2", 2)    # evicts k1
        with self.assertRaises(KeyError):
            cache.get("k1")
        self.assertEqual(cache.get("k2"), 2)

    def test_reinsert_after_eviction(self):
        cache = make_cache(1)
        cache.insert("k1", 1)
        cache.insert("k2", 2)    # evicts k1
        cache.insert("k1", 1)    # re-insert should succeed (evicts k2)
        self.assertEqual(cache.get("k1"), 1)

    def test_insert_after_clear(self):
        cache = make_cache(10)
        cache.insert("k1", {"a": 1})
        cache.clear()
        cache.insert("k1", {"b": 2})
        self.assertEqual(cache.get("k1"), {"b": 2})

    def test_get_on_empty_cache_raises_key_error(self):
        cache = make_cache(10)
        with self.assertRaises(KeyError):
            cache.get("anything")

    def test_default_capacity(self):
        cache = ric_lib.init_cache()
        self.assertEqual(cache.capacity, 10_000)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
