# Example: How to use the NEW Queue-Based Scheduler
# This shows the proper integration pattern

from master.scheduler import Scheduler
from master.queue_monitor import QueueMonitor
from workers.gpu_worker import GPUWorker
from lb.load_balancer import LoadBalancer

# ═══════════════════════════════════════════════════════════════

# INITIALIZATION

# 1. Create workers (same as before)
workers = [GPUWorker(i, max_capacity=25) for i in range(4)]

# 2. Create load balancer (same as before)
lb = LoadBalancer(workers, strategy='least_connections')

# 3. Create SCHEDULER with queue-based configuration (NEW!)
scheduler = Scheduler(
    lb,
    num_consumers=4,        # Number of persistent consumer threads
    request_timeout=30      # Timeout in seconds
)
print(f"✅ Scheduler initialized with persistent queue")

# 4. Create and start QUEUE MONITOR (NEW!)
queue_monitor = QueueMonitor(scheduler, interval=5)
queue_monitor.start()
print(f"✅ Queue monitor started")

# ═══════════════════════════════════════════════════════════════

# USAGE (in client)

from common.models import Request
import time

# Create a request
request = Request(id=1, query="What is machine learning?")

# Send request through scheduler
start = time.time()
response = scheduler.handle_request(request)
elapsed = time.time() - start

# ═══════════════════════════════════════════════════════════════

# RESPONSE (NEW FORMAT with queue metrics)

print("Response received:")
print(f"  ID: {response['id']}")
print(f"  Result: {response['result']}")
print(f"  Worker ID: {response['worker_id']}")
print(f"  Processing Latency: {response['latency']:.3f}s")
print(f"  Queue Wait Time: {response.get('queue_wait_time', 'N/A'):.3f}s")
print(f"  Total Time: {elapsed:.3f}s")

# ═══════════════════════════════════════════════════════════════

# MONITORING

# Queue stats available during execution
stats = scheduler.get_queue_stats()
print(f"\nQueue Stats:")
print(f"  Current Queue Size: {stats['queue_size']}")
print(f"  Number of Consumers: {stats['num_consumers']}")
print(f"  Request Timeout: {stats['request_timeout']}s")

# ═══════════════════════════════════════════════════════════════

# SHUTDOWN (Graceful)

print("\nShutting down scheduler...")
scheduler.shutdown()  # Waits for all pending requests to complete
queue_monitor.stop()
print("✅ Scheduler shut down gracefully")

# ═══════════════════════════════════════════════════════════════

# ADVANCED: Queue-Aware Decision Making (for future enhancements)

# When queue is too large, workers can take different actions:

def process_with_queue_awareness(request, queue_info):
    """
    Example of how workers can react to queue depth.
    queue_info = {"queue_depth": int, "wait_time": float}
    """
    queue_depth = queue_info.get("queue_depth", 0)
    wait_time = queue_info.get("wait_time", 0)
    
    # Strategy 1: Log warning if queue building up
    if queue_depth > 50:
        print(f"⚠️  Queue depth high: {queue_depth} requests waiting")
    
    # Strategy 2: Adjust processing (e.g., use faster model if overloaded)
    if queue_depth > 100:
        # Use faster but less accurate model
        use_fast_model = True
    
    # Strategy 3: Implement backpressure
    if wait_time > 10:  # Request waited > 10s
        print(f"🔴 Request waited {wait_time:.1f}s - consider scaling workers")
    
    return None

# ═══════════════════════════════════════════════════════════════

# MAIN FLOW DIAGRAM

"""
Client Thread 1         Client Thread 2         Client Thread 3
    │                       │                       │
    ├─ scheduler.handle_request()
    │  ├─ Enqueue (request, response_queue)
    │  └─ Wait for response (timeout=30s)
    │
    └─ Gets response:
       {
         "id": 1,
         "result": "...",
         "latency": 0.235s,
         "queue_wait_time": 0.050s  ← NEW!
       }

Meanwhile:

Consumer Thread 1        Consumer Thread 2        Consumer Thread 3
    │                       │                       │
    └─ _consumer_loop():
       ├─ Get request from queue
       ├─ Get queue_depth = 5
       ├─ dispatch(request, queue_depth=5, wait_time=0.050)
       │  └─ worker.process(request, queue_info={...})
       │     ├─ Log queue info
       │     ├─ Process request
       │     └─ Return response
       └─ Put response in response_queue


Monitoring:

QueueMonitor Thread
    └─ Every 5s:
       ├─ Get queue.qsize()
       ├─ Print queue metrics
       └─ Update max_queue_size
"""
