"""Type stubs for ric_lib — an item-capped LRU cache written in Rust."""

from typing import Any, Optional

def init_cache(capacity: Optional[int] = None) -> Cache:
    """Create a new item-capped LRU cache.

    Parameters
    ----------
    capacity:
        Maximum number of items the cache can hold.
        Defaults to 10,000.
    """
    ...

class Cache:
    """In-memory, item-capped LRU cache.

    Values can be any Python object. The cache stores raw Python references
    internally and evicts the least-recently-used entry whenever a new
    insertion would exceed the item capacity.
    """

    capacity: int
    """Maximum number of items the cache can hold (read-only)."""

    def insert(self, key: str, value: Any) -> None:
        """Insert or overwrite *key* with *value*.

        Evicts LRU entries if the capacity is exceeded.
        """
        ...

    def get(self, key: str) -> Any:
        """Return the value for *key* and promote it to most-recently-used.

        Raises
        ------
        KeyError
            If *key* is not present in the cache.
        """
        ...

    def remove(self, key: str) -> bool:
        """Remove *key* from the cache.

        Returns
        -------
        bool
            ``True`` if the key existed and was removed, ``False`` otherwise.
        """
        ...

    def contains(self, key: str) -> bool:
        """Return ``True`` if *key* is in the cache (does not update LRU order)."""
        ...

    def len(self) -> int:
        """Number of entries currently stored."""
        ...

    def is_empty(self) -> bool:
        """``True`` if the cache holds no entries."""
        ...

    def clear(self) -> None:
        """Evict all entries."""
        ...

    def __len__(self) -> int: ...
    def __contains__(self, key: str) -> bool: ...
    def __repr__(self) -> str: ...
