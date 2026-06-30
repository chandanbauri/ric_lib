"""Type stubs for ric_lib — a size-capped LRU cache written in Rust."""

from typing import Any, Optional

def init_cache(limit: Optional[int] = None) -> Cache:
    """Create a new size-capped LRU cache.

    Parameters
    ----------
    limit:
        Maximum total serialised payload in bytes.
        Defaults to 1 048 576 (1 MB).
    """
    ...

class Cache:
    """In-memory, size-capped LRU cache.

    Values must be JSON-serialisable Python objects (dicts, lists, str, int,
    float, bool, None).  The cache serialises values to JSON bytes internally
    and evicts the least-recently-used entry whenever a new insertion would
    exceed the byte limit.
    """

    limit: int
    """Maximum total payload size in bytes (read-only)."""

    def insert(self, key: str, value: Any) -> None:
        """Insert or overwrite *key* with *value*.

        Evicts LRU entries until there is enough room.

        Raises
        ------
        ValueError
            If the serialised *value* alone exceeds ``self.limit``.
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

    def size(self) -> int:
        """Current total payload size in bytes."""
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
