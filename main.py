"""Simple demo / smoke-test — run with: .venv/bin/python main.py"""
import ric_lib

cache = ric_lib.init_cache(10)  # capacity of 10 items

cache.insert("user:1", {"name": "Alice", "score": 99})
cache.insert("user:2", {"name": "Bob",   "score": 42})

print(repr(cache))
print("user:1 →", cache.get("user:1"))
print("user:2 →", cache.get("user:2"))
print("contains 'user:1':", "user:1" in cache)

cache.remove("user:1")
print("after remove — contains 'user:1':", "user:1" in cache)
print("entries:", len(cache))
