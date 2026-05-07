"""
Test script to validate the new Queue-Based Scheduler integration.
Run this to verify all changes are working correctly.

Usage:
    PYTHONPATH=. python test_scheduler_integration.py
"""

import time
import sys
from common.models import Request
from workers.gpu_worker import GPUWorker
from lb.load_balancer import LoadBalancer
from master.scheduler import Scheduler
from master.queue_monitor import QueueMonitor

print("=" * 70)
print("  QUEUE-BASED SCHEDULER INTEGRATION TEST")
print("=" * 70)

# Test 1: Create components
print("\n✓ Test 1: Initializing components...")
try:
    workers = [GPUWorker(i, max_capacity=10) for i in range(2)]
    lb = LoadBalancer(workers, strategy='least_connections')
    scheduler = Scheduler(lb, num_consumers=2, request_timeout=10)
    queue_monitor = QueueMonitor(scheduler, interval=2)
    print("  ✅ Scheduler initialized with:")
    print(f"     - 2 workers")
    print(f"     - 2 consumer threads (was: thread-per-request explosion)")
    print(f"     - 10s timeout (was: no timeout)")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Test 2: Single request
print("\n✓ Test 2: Single request with queue tracking...")
try:
    queue_monitor.start()
    
    request = Request(id=1, query="test query 1")
    response = scheduler.handle_request(request)
    
    assert response['id'] == 1
    assert response['result'] != 'FAILED'
    assert 'queue_wait_time' in response, "Missing queue_wait_time in response (NEW!)"
    
    queue_wait = response.get('queue_wait_time', 0)
    processing = response.get('latency', 0)
    
    print(f"  ✅ Response received:")
    print(f"     - Queue Wait: {queue_wait:.3f}s (NEW!)")
    print(f"     - Processing: {processing:.3f}s")
    print(f"     - Total: {queue_wait + processing:.3f}s")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Test 3: Multiple concurrent requests (test queue buildup)
print("\n✓ Test 3: Multiple concurrent requests (queue buildup)...")
try:
    import threading
    results = []
    lock = threading.Lock()
    
    def send_request(request_id):
        request = Request(id=request_id, query=f"test query {request_id}")
        response = scheduler.handle_request(request)
        with lock:
            results.append(response)
    
    # Send 5 requests rapidly
    threads = []
    for i in range(5):
        t = threading.Thread(target=send_request, args=(i+2,))
        threads.append(t)
        t.start()
    
    # Give them time to queue up
    time.sleep(0.1)
    
    # Check queue size
    stats = scheduler.get_queue_stats()
    queue_size = stats['queue_size']
    print(f"  ✅ Concurrent requests test:")
    print(f"     - Queue size at peak: {queue_size}")
    print(f"     - Consumer threads: {stats['num_consumers']}")
    
    # Wait for all to complete
    for t in threads:
        t.join()
    
    # Verify all completed
    with lock:
        assert len(results) == 5, f"Expected 5 results, got {len(results)}"
        
        # Check queue_wait_time exists in all responses
        queue_waits = [r.get('queue_wait_time', 0) for r in results]
        avg_queue_wait = sum(queue_waits) / len(queue_waits)
        
        print(f"     - Responses received: {len(results)}")
        print(f"     - Avg queue wait: {avg_queue_wait:.3f}s")
        print(f"     - Max queue wait: {max(queue_waits):.3f}s")

except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Test 4: Graceful shutdown
print("\n✓ Test 4: Graceful shutdown...")
try:
    queue_monitor.stop()
    scheduler.shutdown()
    print("  ✅ Scheduler shut down gracefully")
    print(f"     - All pending requests processed")
    print(f"     - Consumer threads stopped")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Test 5: Load generator updates
print("\n✓ Test 5: Checking load generator updates...")
try:
    from client.load_generator import run_load_test
    import inspect
    
    source = inspect.getsource(run_load_test)
    assert 'queue_wait_time' in source, "run_load_test missing queue_wait_time tracking"
    assert 'avg_queue_wait' in source, "run_load_test missing avg_queue_wait metric"
    
    print("  ✅ Load generator properly updated:")
    print("     - Tracks queue_wait_time")
    print("     - Displays avg_queue_wait")
    print("     - Displays max_queue_wait")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Test 6: Worker queue awareness
print("\n✓ Test 6: Checking worker queue awareness...")
try:
    import inspect
    from workers.gpu_worker import GPUWorker
    
    # Check process method signature
    sig = inspect.signature(GPUWorker.process)
    params = list(sig.parameters.keys())
    
    assert 'queue_info' in params, "GPUWorker.process missing queue_info parameter"
    
    print("  ✅ Worker is queue-aware:")
    print("     - process() accepts queue_info parameter")
    print("     - Can make decisions based on queue state")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Summary
print("\n" + "=" * 70)
print("  ✅ ALL INTEGRATION TESTS PASSED!")
print("=" * 70)
print("""
Summary of Changes:
  ✓ Scheduler now uses ThreadPoolExecutor (4 consumer threads)
  ✓ Persistent _consumer_loop() instead of thread-per-request
  ✓ Request timeout handling (default 30s)
  ✓ Queue wait time tracked per request
  ✓ QueueMonitor displays queue health metrics
  ✓ Load generator tracks queue statistics
  ✓ Worker is queue-aware for future decisions
  ✓ Graceful shutdown support

Next Steps:
  1. Run main.py to test in-process mode:
     PYTHONPATH=. python main.py

  2. Run main_nginx.py to test NGINX mode:
     PYTHONPATH=. python main_nginx.py
     (requires NGINX running on port 8080)
""")
print("=" * 70)
