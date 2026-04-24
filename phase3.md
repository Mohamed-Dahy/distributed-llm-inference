# Phase 3 — Fault Tolerance Implementation Plan

## Context

Phase 2 delivered a working three-strategy load balancer with per-worker alive flags and
latency metrics. `python main.py` runs 1000 concurrent users across 3 strategies and prints
a comparison table.

Phase 3 adds real fault tolerance: workers can die mid-run, the load balancer retries on
dead workers up to 3 times, failures are counted and reported in the summary, and a
background `FailureSimulator` thread randomly kills workers after a configurable delay to
simulate production failures.

---

## Naming Migration (Phase 2 → Phase 3)

Phase 2 used `worker.alive`. Phase 3 renames it to `worker.is_alive` so the new
`simulate_failure()` method and `get_alive_workers()` share one consistent flag.

| Old | New |
|---|---|
| `self.alive = True` in `GPUWorker` | `self.is_alive = True` |
| `w.alive` filter in `LoadBalancer` | `w.is_alive` via `get_alive_workers()` |
| `worker.alive = False` in `remove_worker()` | `worker.is_alive = False` |

---

## Files to Modify

### 1. `common/models.py`

Add `WorkerDeadException` below the existing dataclasses:

```python
class WorkerDeadException(Exception):
    def __init__(self, worker_id):
        self.worker_id = worker_id
        super().__init__(f"Worker {worker_id} is dead")
```

---

### 2. `workers/gpu_worker.py`

- Import `WorkerDeadException` from `common.models`
- Rename `self.alive = True` → `self.is_alive = True`
- Add `self.failed_requests = 0`
- At the very top of `process()`, before anything else:
  ```python
  if not self.is_alive:
      raise WorkerDeadException(self.id)
  ```
- Wrap the RAG → LLM processing block in try/except:
  - On any exception: acquire `_lock`, decrement `active_requests`, increment
    `failed_requests`, release, then re-raise
- Add `simulate_failure()`:
  ```python
  def simulate_failure(self):
      self.is_alive = False
      print(f"[FAILURE] Worker {self.id} has gone down!")
  ```

---

### 3. `lb/load_balancer.py`

**Add `get_alive_workers()`:**
```python
def get_alive_workers(self):
    active = [w for w in self.workers if w.is_alive]
    if not active:
        raise Exception("ALL WORKERS ARE DOWN")
    return active
```

**Refactor strategy logic into three private methods** (each calls `get_alive_workers()`):
```python
def _round_robin(self):
    active = self.get_alive_workers()
    worker = active[self.index % len(active)]
    self.index += 1
    return worker

def _least_connections(self):
    return min(self.get_alive_workers(), key=lambda w: w.active_requests)

def _load_aware(self):
    return min(self.get_alive_workers(), key=lambda w: w.active_requests * w.avg_latency)
```

**`get_next_worker()`** becomes a thin dispatcher:
```python
def get_next_worker(self):
    with self.lock:
        if self.strategy == 'round_robin':
            return self._round_robin()
        elif self.strategy == 'least_connections':
            return self._least_connections()
        elif self.strategy == 'load_aware':
            return self._load_aware()
        else:
            raise Exception(f"Unknown strategy: {self.strategy}")
```

**Rewrite `dispatch()` with retry loop:**
```python
def dispatch(self, request, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            worker = self.get_next_worker()
            return worker.process(request)
        except WorkerDeadException as e:
            print(f"[LB] Worker {e.worker_id} dead, retrying ({attempt}/{max_retries})...")
    return {"id": request.id, "result": "FAILED", "latency": -1}
```

**Update `remove_worker()`** to set `is_alive` instead of `alive`:
```python
def remove_worker(self, worker_id):
    for worker in self.workers:
        if worker.id == worker_id:
            worker.is_alive = False
            print(f"[LB] Worker {worker_id} removed from pool")
            return
```

---

### 4. `workers/failure_simulator.py` (new file)

```python
import threading
import random
import time

class FailureSimulator:
    def __init__(self, workers, failure_delay=3.0, num_failures=1):
        self.workers = workers
        self.failure_delay = failure_delay
        self.num_failures = num_failures

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        time.sleep(self.failure_delay)
        alive = [w for w in self.workers if w.is_alive]
        targets = random.sample(alive, min(self.num_failures, len(alive)))
        for w in targets:
            w.simulate_failure()
```

The thread is a **daemon** — it won't block program exit if still sleeping when all user
threads finish.

---

### 5. `client/load_generator.py`

Update `simulate_user()` — wrap `handle_request()` in try/except:
```python
def simulate_user(scheduler, user_id, results, lock):
    request = Request(id=user_id, query=f"Query {user_id}")
    try:
        response = scheduler.handle_request(request)
    except Exception:
        response = {"id": user_id, "result": "FAILED", "latency": -1}
    print(f"[Client] Response {response['id']} | Latency: {response['latency']:.3f}s")
    with lock:
        results.append(response)
```

Note: `results` now collects full response dicts (not just latency floats).

Update `run_load_test()` summary to:
- Separate latencies by excluding failed ones (`latency != -1`)
- Count failed vs successful
- Print dead workers at the end

```
Failed Requests:     X
Successful Requests: Y
Dead Workers:        [Worker 2]
```

---

### 6. `main.py`

- Import `FailureSimulator`
- Inside the strategy loop, after creating workers, before `run_load_test()`:
  ```python
  sim = FailureSimulator(workers, failure_delay=2.0, num_failures=1)
  sim.start()
  ```

---

## Do Not Change

- `rag/retriever.py`
- `llm/inference.py`
- `master/scheduler.py`
- `common/models.py` dataclasses (only add to them)
- Any `__init__.py` files
- Folder structure

---

## Testing Step by Step

### Step 1 — Smoke test
```bash
python main.py
```
Expected: all three strategies complete, comparison table prints, no import errors, no hangs.

### Step 2 — Verify failure fires
Look for mid-run output:
```
[FAILURE] Worker N has gone down!
[LB] Worker N dead, retrying (1/3)...
```

### Step 3 — Verify failed request summary
Each strategy's summary should include:
```
Failed Requests:     X
Successful Requests: Y
Dead Workers:        [Worker N]
```
`X + Y` must equal `NUM_USERS` (1000). Nothing silently dropped.

### Step 4 — Edge case: kill all workers
Temporarily set `num_failures = NUM_WORKERS` in `main.py`.
Expected: all requests return `"FAILED"` dicts, program exits cleanly, no crash.

### Step 5 — Race condition check
Run three times back to back:
```bash
for i in 1 2 3; do python main.py; done
```
Latency values (~0.2s avg) and counts should be consistent across runs.
