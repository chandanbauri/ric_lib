import time
import random
from ric_lib import init_cache

def generate_data(size_type, index):
    if size_type == "small":
        return {"id": index, "value": "a" * 10}
    elif size_type == "medium":
        return {"id": index, "value": "a" * 500}
    else: # large
        return {"id": index, "value": "a" * 5000}

def test_benchmark_performance():
    num_points = 2_000_000
    
    # 2 million items capacity to hold all 1M items without eviction, 
    # so we can purely measure insertion and retrieval times.
    cache_capacity = 1_000_000 
    cache = init_cache(capacity=cache_capacity)
    
    print(f"\n--- Starting benchmark with {num_points} data points ---")
    
    sizes = ["small", "medium", "large"]
    
    insert_times = []
    
    print("Starting insertion benchmark (this may take a while)...")
    start_total_insert = time.time()
    for i in range(num_points):
        key = f"key_{i}"
        size_type = sizes[i % 3]
        val = generate_data(size_type, i)
        
        t0 = time.time()
        cache.insert(key, val)
        t1 = time.time()
        
        insert_times.append(t1 - t0)
        
        if (i + 1) % 200_000 == 0:
            print(f"  Inserted {i + 1} items...")
            
    total_insert_time = time.time() - start_total_insert
    
    # Now retrieve
    print("Starting retrieval benchmark...")
    
    # Shuffle a subset of keys to avoid excessive memory usage from a 1M element list of strings
    # We can just generate random indices to retrieve
    retrieve_times = []
    
    start_total_retrieve = time.time()
    for i in range(num_points):
        # Pick a random key from 0 to num_points - 1
        rand_idx = random.randint(0, num_points - 1)
        key = f"key_{rand_idx}"
        
        t0 = time.time()
        try:
            val = cache.get(key)
        except KeyError:
            pass # Expected if the key was evicted
        except Exception as e:
            print(f"Error retrieving {key}: {e}")
        t1 = time.time()
        
        retrieve_times.append(t1 - t0)
        
        if (i + 1) % 200_000 == 0:
            print(f"  Retrieved {i + 1} items...")
            
    total_retrieve_time = time.time() - start_total_retrieve
    
    avg_insert = sum(insert_times) / num_points
    avg_retrieve = sum(retrieve_times) / num_points
    
    print(f"\n--- Benchmark Results ---")
    print(f"Total Insert Time: {total_insert_time:.2f} seconds")
    print(f"Average Insert Time: {avg_insert * 1e6:.2f} microseconds per item")
    print(f"Total Retrieve Time: {total_retrieve_time:.2f} seconds")
    print(f"Average Retrieve Time: {avg_retrieve * 1e6:.2f} microseconds per item")

if __name__ == '__main__':
    test_benchmark_performance()
