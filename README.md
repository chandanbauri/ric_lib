# ric_lib

A fast, size-capped in-memory **LRU cache** for Python, written in Rust and
exposed via [PyO3](https://pyo3.rs/).

Values are any JSON-serialisable Python object. The cache enforces a **byte
limit** on the total serialised payload and automatically evicts the
least-recently-used entry when a new insertion would exceed it.

## Installation

```bash
pip install ric_lib
```

## Quick start

```python
import ric_lib

# Create a cache capped at 10 MB
cache = ric_lib.init_cache(10 * 1024 * 1024)

cache.insert("user:42", {"name": "Alice", "score": 99})

value = cache.get("user:42")   # {"name": "Alice", "score": 99}

print(cache.size())            # current bytes used
print(cache.len())             # number of entries
print("user:42" in cache)      # True  (via __contains__)
print(repr(cache))             # Cache(limit=10485760, size=..., entries=1)

cache.remove("user:42")
cache.clear()
```

## API

### `ric_lib.init_cache(limit=None) -> Cache`

Create a new cache.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit`   | `int \| None` | `1_048_576` | Maximum total payload in bytes (1 MB). |

### `Cache`

| Method | Description |
|--------|-------------|
| `insert(key, value)` | Insert or overwrite a key. Evicts LRU entries as needed. Raises `ValueError` if the single value exceeds `limit`. |
| `get(key)` | Return the value and promote the entry to MRU. Raises `KeyError` if missing. |
| `remove(key) -> bool` | Evict a specific key. Returns `True` if it existed. |
| `contains(key) -> bool` | Check existence without updating LRU order. Also `key in cache`. |
| `size() -> int` | Current total byte usage. |
| `len() -> int` | Number of entries. Also `len(cache)`. |
| `is_empty() -> bool` | `True` if no entries. |
| `clear()` | Evict all entries. |
| `limit` | Read-only attribute — the byte cap the cache was created with. |

## How eviction works

Entries are ordered from most-recently-used (MRU) to least-recently-used (LRU)
in a doubly-linked list.  `get` promotes an entry to the MRU position.
`insert` adds to the MRU position.  When the cache is full, the LRU tail is
evicted repeatedly until there is room.

## Building from source

Requires Rust (stable) and [maturin](https://www.maturin.rs/).

```bash
python -m venv .venv && source .venv/bin/activate
pip install maturin
maturin develop
```

## Running tests

```bash
python -m pytest tests/ -v
```

## License

MIT
