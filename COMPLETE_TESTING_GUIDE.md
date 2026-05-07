# 🧪 COMPLETE TESTING GUIDE FOR SCHEDULER UPGRADE

## 🎯 Testing Hierarchy

```
Level 1: Quick Validation (5 min)      ← Start here
         ↓
Level 2: In-Process Mode Testing (10 min)
         ↓
Level 3: NGINX Mode Testing (15 min)
         ↓
Level 4: Performance Comparison (Optional)
```

---

## 📋 LEVEL 1: QUICK VALIDATION TEST (5 minutes)

### **Command**
```bash
PYTHONPATH=. python test_scheduler_integration.py
```

### **What It Tests**
✓ Scheduler initialization  
✓ ThreadPoolExecutor creation (4 workers)  
✓ Single request processing  
✓ Queue metrics tracking  
✓ Concurrent requests  
✓ Queue buildup and drain  
✓ Graceful shutdown  
✓ Load generator updates  

### **Expected Output**
```
======================================================================
  QUEUE-BASED SCHEDULER INTEGRATION TEST
======================================================================

✓ Test 1: Initializing components...
  ✅ Scheduler initialized with:
     - 2 workers
     - 2 consumer threads (was: thread-per-request explosion)
     - 10s timeout (was: no timeout)

✓ Test 2: Single request with queue tracking...
  ✅ Response received:
     - Queue Wait: 0.002s (NEW!)
     - Processing: 0.200s
     - Total: 0.202s

✓ Test 3: Multiple concurrent requests (queue buildup)...
  ✅ Concurrent requests test:
     - Queue size at peak: 2
     - Consumer threads: 2
     - Responses received: 5
     - Avg queue wait: 0.045s
     - Max queue wait: 0.089s

✓ Test 4: Graceful shutdown...
  ✅ Scheduler shut down gracefully
     - All pending requests processed
     - Consumer threads stopped

✓ Test 5: Checking load generator updates...
  ✅ Load generator properly updated:
     - Tracks queue_wait_time
     - Displays avg_queue_wait
     - Displays max_queue_wait

✓ Test 6: Checking worker queue awareness...
  ✅ Worker is queue-aware:
     - process() accepts queue_info parameter
     - Can make decisions based on queue state

======================================================================
  ✅ ALL INTEGRATION TESTS PASSED!
======================================================================
```

### **What to Check**
- [ ] All 6 tests show ✅
- [ ] No errors or exceptions
- [ ] Queue metrics appear (queue_wait_time)
- [ ] Consumer threads created

**If ANY test fails:** Debug that specific component before moving to Level 2

---

## 🏃 LEVEL 2: IN-PROCESS MODE TEST (10 minutes)

### **Command**
```bash
PYTHONPATH=. python main.py
```

### **Expected Output Sequence**

#### **1. Initialization (first 2 seconds)**
```
[Main] Logging to logs/run_20260507_142530.log

============================================================
  STRATEGY : round_robin
  USERS    : 25    WORKERS : 4
  QUEUE    : 4 consumer threads, 30s timeout (NEW!)
============================================================

[Scheduler] Started with 4 consumer threads          ← NEW!
[Scheduler] Consumer thread 12345 started
[Scheduler] Consumer thread 12346 started
[Scheduler] Consumer thread 12347 started
[Scheduler] Consumer thread 12348 started

[QueueMonitor] Started queue monitoring             ← NEW!
```

#### **2. Request Processing (next 5-10 seconds)**
```
[Scheduler] Queuing request 0 (queue size: 0)
[Scheduler] Queuing request 1 (queue size: 1)
[Scheduler] Queuing request 2 (queue size: 2)

[QueueMonitor] @5.0s │ Queue Size: 3 │ Max: 8 │ Consumers: 4    ← NEW!

[Worker 0] Processing request 0 (queue: 3, wait: 0.05s)
[Worker 1] Processing request 1 (queue: 2, wait: 0.04s)

[Client] ──── Response 0 ────
  Worker: 2
  Queue Wait: 0.050s | Processing: 0.200s | Total: 0.250s      ← NEW!
  Q: What is supervised learning?
  A: Supervised learning is...
```

#### **3. Summary (at the end)**
```
  Successful Requests: 25
  Failed Requests:     0
  Avg Queue Wait:      0.045s (NEW!)          ← NEW!
  Max Queue Wait:      0.089s (NEW!)          ← NEW!

============================================================
  LOAD BALANCING STRATEGY COMPARISON -- 25 users, 4 workers
============================================================
  Strategy             Time     Throughput    Avg Latency    Queue Wait
  ────────────────────────────────────────────────────────────────────
  round_robin          7.2s     3.47 req/s    0.229s         0.045s
  least_connections    6.8s     3.68 req/s    0.215s         0.038s
  load_aware           6.5s     3.85 req/s    0.206s         0.032s
  ============================================================
```

### **What to Check (In Order)**
- [ ] **4 consumer threads started** (not 25!)
  ```
  [Scheduler] Consumer thread XXXXX started  (appears 4 times)
  ```

- [ ] **QueueMonitor sampling every 5s** (NEW!)
  ```
  [QueueMonitor] @5.0s │ Queue Size: X │ Max: Y │ Consumers: 4
  ```

- [ ] **Queue wait time in responses** (NEW!)
  ```
  Queue Wait: 0.050s | Processing: 0.200s | Total: 0.250s
  ```

- [ ] **Queue metrics in summary** (NEW!)
  ```
  Avg Queue Wait:      0.045s
  Max Queue Wait:      0.089s
  ```

- [ ] **Strategy comparison shows Queue Wait column** (NEW!)
  ```
  Strategy             ... Queue Wait
  round_robin          ... 0.045s
  least_connections    ... 0.038s
  load_aware           ... 0.032s
  ```

### **Performance Expectations**
| Metric | Min | Typical | Max |
|--------|-----|---------|-----|
| Total Time | 5s | 6-7s | 10s |
| Throughput | 3 req/s | 3.5-4 req/s | 5 req/s |
| Avg Latency | 0.2s | 0.2-0.25s | 0.3s |
| Avg Queue Wait | 0.01s | 0.03-0.05s | 0.1s |

**If times are much longer:** Check if other processes are running

---

## 🌐 LEVEL 3: NGINX MODE TEST (15 minutes)

### **Setup**
```bash
# Terminal 1: Start NGINX
nginx -c nginx.conf
# Verify: curl http://127.0.0.1:8080/health should succeed

# Terminal 2: Run test
PYTHONPATH=. python main_nginx.py
```

### **Expected Output**

#### **1. Worker Server Startup (2-3 seconds)**
```
[Worker 1] Starting on port 8001
[Worker 2] Starting on port 8002

[Main] Worker on port 8001 is ready
[Main] Worker on port 8002 is ready

============================================================
  MODE     : NGINX (HTTP)
  USERS    : 35    WORKERS : 2
  NGINX    : http://127.0.0.1:8080
  SCHEDULER: Queue-based (4 consumer threads per worker) (NEW!)
  LLM MODE : STUB (0.2s sleep)
============================================================
```

#### **2. Requests Being Processed (5-10 seconds)**
```
[Heartbeat] Worker on port 8001 is ready
[Heartbeat] Worker on port 8002 is ready

[QueueMonitor] @5.0s │ Queue Size: 4 │ Max: 12 │ Consumers: 4

[HTTP Client] Response 0 | Worker 1 | Queue: 0.050s | Processing: 0.200s
[HTTP Client] Response 1 | Worker 2 | Queue: 0.048s | Processing: 0.202s

[Monitor] @5.0s │ System Performance
[Monitor]  W    Status   Active  Total  Failed  Latency     GPU
[Monitor]  ────────────────────────────────────────────────────
[Monitor]  1    ALIVE        2     10      0    0.201s   40.0%
[Monitor]  2    ALIVE        3     12      0    0.198s   60.0%
```

#### **3. Summary (at the end)**
```
  Successful Requests: 35
  Failed Requests:     0

============================================================
  NGINX LOAD TEST -- nginx_distributed
============================================================
  Users:        35
  Successful:   35
  Failed:       0
  Total Time:   10.2s
  Throughput:   3.43 req/s
  Avg Latency:  0.205s
  Min Latency:  0.200s
  Max Latency:  0.215s
============================================================
```

### **What to Check**
- [ ] NGINX is running on port 8080
  ```bash
  curl http://127.0.0.1:8080/health
  # Should return 200 OK
  ```

- [ ] Workers started successfully (port 8001, 8002)
  ```
  [Worker 1] Starting on port 8001
  [Worker 2] Starting on port 8002
  ```

- [ ] HTTP Client shows queue metrics (NEW!)
  ```
  Queue: 0.050s | Processing: 0.200s
  ```

- [ ] Requests succeed
  ```
  Successful: 35
  Failed: 0
  ```

- [ ] No timeout errors
  ```
  (should NOT see "TIMEOUT")
  ```

---

## 🧪 LEVEL 4: PERFORMANCE COMPARISON (Optional)

### **Purpose**
Compare old scheduler vs new scheduler on same load

### **Method 1: Run Multiple Times**
```bash
# Run 3 times and average results
PYTHONPATH=. python main.py
# Record: total_time, throughput, avg_queue_wait

PYTHONPATH=. python main.py
# Record again

PYTHONPATH=. python main.py
# Record again
```

### **Expected Improvements**
| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Memory (threads)** | ~50MB | ~15MB | 70% reduction |
| **Context Switches** | High | Low | ~50% reduction |
| **Timeout Hangs** | Possible | None | 100% fix |
| **Queue Visibility** | None | Full | ∞ (was 0) |

### **Method 2: Resource Monitoring**
```bash
# Terminal 1: Start process monitor
Get-Process python | Select Name, Handles, WorkingSet
# Run while main.py is executing
# Check: Handles should be low (~100-200 per process)
# Check: WorkingSet should be ~50-100MB total

# Terminal 2: Run test
PYTHONPATH=. python main.py
```

---

## 🔍 DETAILED INSPECTION TESTS

### **Test 1: Verify 4 Consumer Threads**
```bash
# While main.py is running:
Get-Process python | Select Handles
```
**Expected:** Low handle count (~100-200 per process, NOT 1000+)

### **Test 2: Verify Queue Metrics Accuracy**
```bash
# Edit main.py temporarily to set:
NUM_USERS = 5
# Run:
PYTHONPATH=. python main.py

# Manually check: queue_wait_time should be > 0 for at least some requests
# Because with 5 users and 4 workers, some should queue
```

### **Test 3: Verify Timeout Works**
```bash
# Edit workers/gpu_worker.py temporarily:
def process(self, request, queue_info=None):
    time.sleep(60)  # Simulate slow worker
    
# Then run:
PYTHONPATH=. python main.py
# With 30s timeout, requests should fail with TIMEOUT after 30s
# (not hang indefinitely)
```

### **Test 4: Verify Graceful Shutdown**
The scheduler should wait for all requests to complete:
```bash
# Add this to end of main.py's main() function:
print(f"[Main] Final queue stats: {scheduler.get_queue_stats()}")
# Should show queue_size: 0 (all processed)
```

---

## ✅ FINAL VALIDATION CHECKLIST

### **Code Changes Verified**
- [ ] `master/scheduler.py` has ThreadPoolExecutor
- [ ] `master/scheduler.py` has `_consumer_loop()` (not `_consume_once()`)
- [ ] `master/scheduler.py` has request timeout
- [ ] `workers/gpu_worker.py` accepts `queue_info` parameter
- [ ] `lb/load_balancer.py` passes queue metrics
- [ ] `master/queue_monitor.py` exists and monitors
- [ ] `client/load_generator.py` tracks queue_wait_time
- [ ] `main.py` creates QueueMonitor
- [ ] `main.py` calls scheduler.shutdown()

### **Functional Behavior Verified**
- [ ] Only 4 consumer threads created (not 25+)
- [ ] QueueMonitor displays queue size every 5s
- [ ] Responses include queue_wait_time
- [ ] Summary shows avg_queue_wait and max_queue_wait
- [ ] Graceful shutdown completes
- [ ] No request timeouts (unless intentionally tested)
- [ ] All requests complete successfully

### **Performance Verified**
- [ ] System completes faster (or similar speed)
- [ ] Memory usage lower (fewer threads)
- [ ] Queue buildup/drain visible in QueueMonitor
- [ ] Queue wait times make sense (should increase under load)

---

## 🐛 TROUBLESHOOTING

### **Issue: "ModuleNotFoundError: No module named 'master.queue_monitor'"**
```bash
# Solution: Make sure queue_monitor.py exists
ls master/queue_monitor.py
# If missing, create it from the provided code
```

### **Issue: "FAILED after 3 retries"**
```bash
# Reason: Workers might be overloaded or dead
# Solution:
# 1. Check worker ports are responding:
curl http://127.0.0.1:8001/health

# 2. Reduce NUM_USERS in main.py:
NUM_USERS = 10  # Instead of 25

# 3. Increase NUM_WORKERS:
NUM_WORKERS = 8  # Instead of 4
```

### **Issue: "Connection refused" on NGINX tests**
```bash
# Reason: NGINX not running
# Solution:
# Terminal 1: Start NGINX first
nginx -c nginx.conf
# Verify: curl http://127.0.0.1:8080/health

# Terminal 2: Run main_nginx.py
PYTHONPATH=. python main_nginx.py
```

### **Issue: Tests taking too long (> 20 seconds)**
```bash
# Reason: System is slow or OTHER processes consuming CPU
# Solution:
# 1. Close other applications
# 2. Run on idle system
# 3. Or reduce NUM_USERS temporarily:
NUM_USERS = 10
```

### **Issue: Queue wait time always 0"**
```bash
# Reason: Not enough load to cause queuing
# Solution:
# 1. Increase NUM_USERS:
NUM_USERS = 100

# 2. Decrease NUM_WORKERS:
NUM_WORKERS = 2

# This will cause queuing visible in queue_wait_time
```

---

## 📊 EXPECTED OUTPUTS BY TEST LEVEL

### **Level 1 (Quick Test)**
```
✅ ALL INTEGRATION TESTS PASSED!
```

### **Level 2 (In-Process)**
```
[Scheduler] Consumer thread XXXX started (4 times)
[QueueMonitor] @5.0s | Queue Size: X | Max: Y | Consumers: 4
Queue Wait: 0.XXs | Processing: 0.XXs | Total: 0.XXs
Avg Queue Wait: 0.XXs
Max Queue Wait: 0.XXs
```

### **Level 3 (NGINX)**
```
[Worker 1] Starting on port 8001
[Worker 2] Starting on port 8002
[HTTP Client] Response X | Worker Y | Queue: 0.XXs | Processing: 0.XXs
Successful: 35
Failed: 0
```

### **All Tests Pass → Ready for Production! 🚀**

---

## 🎯 QUICK TEST COMMAND

Run all tests in sequence:
```bash
echo "Test 1: Quick validation"
PYTHONPATH=. python test_scheduler_integration.py

echo ""
echo "Test 2: In-process mode"
PYTHONPATH=. python main.py

echo ""
echo "Test 3: Note - for NGINX test, start in separate terminals:"
echo "  Terminal 1: nginx -c nginx.conf"
echo "  Terminal 2: PYTHONPATH=. python main_nginx.py"
```

**Total testing time: ~30 minutes for full validation** ⏱️
