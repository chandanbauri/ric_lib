use chrono::Utc;
use pyo3::exceptions::PyKeyError;
use pyo3::prelude::*;
use pyo3::pybacked::PyBackedStr;
use pyo3::types::PyAny;
use std::collections::HashMap;

/// Default capacity (maximum number of items) if the caller does not provide one.
const DEFAULT_CAPACITY: usize = 10_000;

// ---------------------------------------------------------------------------
// Internal doubly-linked list node — not exposed to Python.
// ---------------------------------------------------------------------------

#[pyclass]
struct CacheNode {
    key: PyBackedStr,
    data: Py<PyAny>,
    last_used: i64,
    left: Option<Py<CacheNode>>,
    right: Option<Py<CacheNode>>,
}

// CacheNode must be a #[pyclass] so values can be stored as Py<CacheNode>.
// The empty #[pymethods] block means no methods are callable from Python —
// the type is entirely opaque outside of Rust.
#[pymethods]
impl CacheNode {}

// ---------------------------------------------------------------------------
// Public cache type
// ---------------------------------------------------------------------------

/// An in-memory, item-capped LRU cache backed by a doubly-linked list and a
/// hash map. Stores raw Python objects.
///
/// Parameters
/// ----------
/// capacity : int
///     Maximum number of items the cache may hold. Defaults to 10,000.
#[pyclass(module = "ric_lib")]
pub struct Cache {
    /// Maximum number of items in the cache.
    #[pyo3(get)]
    pub capacity: usize,
    head: Option<Py<CacheNode>>,
    tail: Option<Py<CacheNode>>,
    table: HashMap<PyBackedStr, Option<Py<CacheNode>>>,
}

// ---------------------------------------------------------------------------
// Public Python API
// ---------------------------------------------------------------------------

#[pymethods]
impl Cache {
    #[new]
    #[pyo3(signature = (capacity))]
    fn new(capacity: usize) -> Self {
        Self {
            capacity,
            head: None,
            tail: None,
            table: HashMap::new(),
        }
    }

    /// Insert or overwrite a key.  Evicts the least-recently-used entry when
    /// the cache would exceed its capacity.
    #[pyo3(signature = (key, value))]
    fn insert(
        &mut self,
        py: Python<'_>,
        key: PyBackedStr,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let last_used = Self::now_ms();

        // Evict until we have space for 1 more item.
        // If we are replacing an existing key, the total size doesn't increase,
        // but we handle eviction first if it's a new key.
        let is_new_key = !self.table.contains_key(&key);
        if is_new_key {
            while self.table.len() >= self.capacity {
                self.evict_lru(py);
            }
        }

        let new_node = Py::new(
            py,
            CacheNode {
                key: key.clone_ref(py),
                data: value.clone().unbind(),
                last_used,
                left: None,
                right: None,
            },
        )?;

        // Prepend to head.
        if let Some(ref curr_head) = self.head {
            new_node.borrow_mut(py).right = Some(curr_head.clone_ref(py));
            curr_head.borrow_mut(py).left = Some(new_node.clone_ref(py));
        } else {
            self.tail = Some(new_node.clone_ref(py));
        }
        self.head = Some(new_node.clone_ref(py));

        // Overwrite table entry; remove old node from list if it existed.
        if let Some(Some(old_node)) = self.table.insert(key, Some(new_node.clone_ref(py))) {
            if !old_node.is(&new_node) {
                self.unlink(py, old_node);
            }
        }

        Ok(())
    }

    /// Retrieve the value for `key` and promote it to the most-recently-used
    /// position.
    ///
    /// Raises
    /// ------
    /// KeyError
    ///     If the key is not present in the cache.
    #[pyo3(signature = (key))]
    fn get<'py>(&mut self, py: Python<'py>, key: PyBackedStr) -> PyResult<Py<PyAny>> {
        // Drop the table borrow before calling &mut self methods.
        let (node, node_data) = {
            let entry = self
                .table
                .get(&key)
                .ok_or_else(|| PyKeyError::new_err(format!("Key '{}' not found", key)))?;

            match entry {
                Some(n) => (n.clone_ref(py), n.borrow(py).data.clone_ref(py)),
                None => {
                    return Err(PyKeyError::new_err(format!(
                        "Value associated with key '{}' is corrupted",
                        key
                    )));
                }
            }
        };

        node.borrow_mut(py).last_used = Self::now_ms();
        self.move_to_head(py, node);
        Ok(node_data)
    }

    /// Remove a key from the cache.  Returns ``True`` if the key existed,
    /// ``False`` otherwise.
    #[pyo3(signature = (key))]
    fn remove(&mut self, py: Python<'_>, key: PyBackedStr) -> bool {
        if let Some(Some(node)) = self.table.remove(&key) {
            self.unlink(py, node);
            true
        } else {
            false
        }
    }

    /// Returns ``True`` if the key exists in the cache (without updating LRU order).
    #[pyo3(signature = (key))]
    fn contains(&self, key: PyBackedStr) -> bool {
        self.table.contains_key(&key)
    }

    /// Number of entries currently in the cache.
    #[pyo3(signature = ())]
    fn len(&self) -> usize {
        self.table.len()
    }

    /// ``True`` if the cache holds no entries.
    #[pyo3(signature = ())]
    fn is_empty(&self) -> bool {
        self.table.is_empty()
    }

    /// Evict all entries.
    #[pyo3(signature = ())]
    fn clear(&mut self, py: Python<'_>) {
        while self.head.is_some() {
            self.evict_lru(py);
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "Cache(capacity={}, entries={})",
            self.capacity,
            self.table.len()
        )
    }

    fn __len__(&self) -> usize {
        self.table.len()
    }

    fn __contains__(&self, key: PyBackedStr) -> bool {
        self.contains(key)
    }
}

// ---------------------------------------------------------------------------
// Internal helpers — pure Rust, not callable from Python
// ---------------------------------------------------------------------------

impl Cache {
    fn now_ms() -> i64 {
        Utc::now().timestamp_millis()
    }

    /// Unlink `node` from the doubly-linked list. Does not touch the table.
    /// Severs the node's own pointers to break `Py<T>` cycles.
    fn unlink(&mut self, py: Python<'_>, node: Py<CacheNode>) {
        let left = node.borrow(py).left.as_ref().map(|n| n.clone_ref(py));
        let right = node.borrow(py).right.as_ref().map(|n| n.clone_ref(py));

        match &left {
            Some(l) => l.borrow_mut(py).right = right.as_ref().map(|n| n.clone_ref(py)),
            None => self.head = right.as_ref().map(|n| n.clone_ref(py)),
        }
        match &right {
            Some(r) => r.borrow_mut(py).left = left.as_ref().map(|n| n.clone_ref(py)),
            None => self.tail = left.as_ref().map(|n| n.clone_ref(py)),
        }

        node.borrow_mut(py).left = None;
        node.borrow_mut(py).right = None;
    }

    /// Evict the tail (LRU) node from the list and the table.
    fn evict_lru(&mut self, py: Python<'_>) {
        let tail = match self.tail {
            Some(ref t) => t.clone_ref(py),
            None => return,
        };
        let key = tail.borrow(py).key.clone_ref(py);
        self.table.remove(&key);
        self.unlink(py, tail);
    }

    /// Move `node` to the head (MRU position).  No-op if already the head.
    fn move_to_head(&mut self, py: Python<'_>, node: Py<CacheNode>) {
        if let Some(ref h) = self.head {
            if node.is(h) {
                return;
            }
        }

        let old_left = node.borrow(py).left.as_ref().map(|n| n.clone_ref(py));
        let old_right = node.borrow(py).right.as_ref().map(|n| n.clone_ref(py));

        if let Some(ref l) = old_left {
            l.borrow_mut(py).right = old_right.as_ref().map(|n| n.clone_ref(py));
        }
        if let Some(ref r) = old_right {
            r.borrow_mut(py).left = old_left.as_ref().map(|n| n.clone_ref(py));
        }
        if let Some(ref t) = self.tail {
            if node.is(t) {
                self.tail = old_left.as_ref().map(|n| n.clone_ref(py));
            }
        }

        node.borrow_mut(py).left = None;
        node.borrow_mut(py).right = self.head.as_ref().map(|h| h.clone_ref(py));
        if let Some(ref curr_head) = self.head {
            curr_head.borrow_mut(py).left = Some(node.clone_ref(py));
        }
        self.head = Some(node);
    }
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

/// Instantiate an item-capped LRU cache.
///
/// Parameters
/// ----------
/// capacity : int, optional
///     Maximum number of items. Defaults to 10,000.
#[pyfunction]
#[pyo3(signature = (capacity = None))]
fn init_cache(capacity: Option<usize>) -> Cache {
    Cache::new(capacity.unwrap_or(DEFAULT_CAPACITY))
}

#[pymodule]
fn ric_lib(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(init_cache, m)?)?;
    m.add_class::<Cache>()?;
    Ok(())
}
