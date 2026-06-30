use chrono::Utc;
use pyo3::exceptions::{PyKeyError, PySystemError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyAny;
use pythonize::{depythonize, pythonize};
use std::collections::HashMap;

/// Default size cap in bytes if the caller does not provide one.
const DEFAULT_MAX_MEMORY_LIMIT: u64 = 1_000_000; // 1 MB

// ---------------------------------------------------------------------------
// Internal doubly-linked list node — not exposed to Python.
// ---------------------------------------------------------------------------

#[pyclass]
struct CacheNode {
    key: String,
    data: Vec<u8>,
    last_used: i64,
    left: Option<Py<CacheNode>>,
    right: Option<Py<CacheNode>>,
    size: u64,
}

// CacheNode must be a #[pyclass] so values can be stored as Py<CacheNode>.
// The empty #[pymethods] block means no methods are callable from Python —
// the type is entirely opaque outside of Rust.
#[pymethods]
impl CacheNode {}


// ---------------------------------------------------------------------------
// Public cache type
// ---------------------------------------------------------------------------

/// An in-memory, size-capped LRU cache backed by a doubly-linked list and a
/// hash map.  Serialises Python objects to JSON bytes internally.
///
/// Parameters
/// ----------
/// limit : int
///     Maximum number of bytes the cache may hold (measured as the length of
///     the JSON-serialised value).  Defaults to 1 MB.
#[pyclass(module = "ric_lib")]
pub struct Cache {
    /// Maximum total payload size in bytes.
    #[pyo3(get)]
    pub limit: u64,
    size: u64,
    head: Option<Py<CacheNode>>,
    tail: Option<Py<CacheNode>>,
    table: HashMap<String, Option<Py<CacheNode>>>,
}

// ---------------------------------------------------------------------------
// Public Python API
// ---------------------------------------------------------------------------

#[pymethods]
impl Cache {
    #[new]
    #[pyo3(signature = (limit))]
    fn new(limit: u64) -> Self {
        Self {
            limit,
            size: 0,
            head: None,
            tail: None,
            table: HashMap::new(),
        }
    }

    /// Insert or overwrite a key.  Evicts the least-recently-used entry when
    /// the cache would exceed its limit.
    ///
    /// Raises
    /// ------
    /// ValueError
    ///     If the serialised value is larger than the cache limit itself.
    #[pyo3(signature = (key, value))]
    fn insert(&mut self, py: Python<'_>, key: String, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let data = self.encode(value)?;
        let last_used = Self::now_ms();
        let curr_data_size = data.len() as u64;

        if curr_data_size > self.limit {
            return Err(PyValueError::new_err(format!(
                "Value for key '{}' ({} bytes) exceeds the cache limit ({} bytes)",
                key, curr_data_size, self.limit
            )));
        }

        while self.size + curr_data_size > self.limit {
            self.evict_lru(py);
        }

        let new_node = Py::new(py, CacheNode {
            key: key.clone(),
            data,
            last_used,
            left: None,
            right: None,
            size: curr_data_size,
        })?;

        // Prepend to head.
        if let Some(ref curr_head) = self.head {
            new_node.borrow_mut(py).right = Some(curr_head.clone_ref(py));
            curr_head.borrow_mut(py).left = Some(new_node.clone_ref(py));
        } else {
            self.tail = Some(new_node.clone_ref(py));
        }
        self.head = Some(new_node.clone_ref(py));
        self.size += curr_data_size;

        // Overwrite table entry; remove old node from list if it existed.
        if let Some(Some(old_node)) = self.table.insert(key, Some(new_node.clone_ref(py))) {
            if !old_node.is(&new_node) {
                let old_size = old_node.borrow(py).size;
                self.size = self.size.saturating_sub(old_size);
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
    fn get<'py>(&mut self, py: Python<'py>, key: String) -> PyResult<Bound<'py, PyAny>> {
        // Drop the table borrow before calling &mut self methods.
        let (node, node_data) = {
            let entry = self
                .table
                .get(&key)
                .ok_or_else(|| PyKeyError::new_err(format!("Key '{}' not found", key)))?;

            match entry {
                Some(n) => (n.clone_ref(py), n.borrow(py).data.clone()),
                None => {
                    return Err(PyValueError::new_err(format!(
                        "Value associated with key '{}' is corrupted",
                        key
                    )));
                }
            }
        };

        node.borrow_mut(py).last_used = Self::now_ms();
        self.move_to_head(py, node);
        self.decode(py, node_data)
    }

    /// Remove a key from the cache.  Returns ``True`` if the key existed,
    /// ``False`` otherwise.
    #[pyo3(signature = (key))]
    fn remove(&mut self, py: Python<'_>, key: String) -> bool {
        if let Some(Some(node)) = self.table.remove(&key) {
            let node_size = node.borrow(py).size;
            self.size = self.size.saturating_sub(node_size);
            self.unlink(py, node);
            true
        } else {
            false
        }
    }

    /// Returns ``True`` if the key exists in the cache (without updating LRU order).
    #[pyo3(signature = (key))]
    fn contains(&self, key: String) -> bool {
        self.table.contains_key(&key)
    }

    /// Current total byte usage.
    #[pyo3(signature = ())]
    fn size(&self) -> u64 {
        self.size
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
            "Cache(limit={}, size={}, entries={})",
            self.limit,
            self.size,
            self.table.len()
        )
    }

    fn __len__(&self) -> usize {
        self.table.len()
    }

    fn __contains__(&self, key: String) -> bool {
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

    fn encode(&self, val: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
        let json_val: serde_json::Value = depythonize(val).map_err(|e| {
            PySystemError::new_err(format!("failed to serialise Python object: {e}"))
        })?;
        serde_json::to_vec(&json_val)
            .map_err(|e| PySystemError::new_err(format!("JSON serialisation failed: {e}")))
    }

    fn decode<'py>(&self, py: Python<'py>, val: Vec<u8>) -> PyResult<Bound<'py, PyAny>> {
        let json_val: serde_json::Value = serde_json::from_slice(&val)
            .map_err(|e| PySystemError::new_err(format!("JSON deserialisation failed: {e}")))?;
        pythonize(py, &json_val).map_err(|e| {
            PySystemError::new_err(format!("failed to convert value to Python object: {e}"))
        })
    }

    /// Unlink `node` from the doubly-linked list.  Does not touch the table or
    /// `self.size`.  Severs the node's own pointers to break `Py<T>` cycles.
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
        let key = tail.borrow(py).key.clone();
        let size = tail.borrow(py).size;
        self.table.remove(&key);
        self.size = self.size.saturating_sub(size);
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

/// Instantiate a size-capped LRU cache.
///
/// Parameters
/// ----------
/// limit : int, optional
///     Maximum total payload bytes.  Defaults to 1 048 576 (1 MB).
#[pyfunction]
#[pyo3(signature = (limit = None))]
fn init_cache(limit: Option<u64>) -> Cache {
    Cache::new(limit.unwrap_or(DEFAULT_MAX_MEMORY_LIMIT))
}

#[pymodule]
fn ric_lib(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(init_cache, m)?)?;
    m.add_class::<Cache>()?;
    Ok(())
}
