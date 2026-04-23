# Phase 2 — Load Balancing Strategies Implementation Plan

## Context

This is a distributed LLM inference simulation project built for CSE354: Distributed Computing.
The skeleton (Phase 1) is already working and tested. `python main.py` runs successfully with
1000 concurrent threads routing through a Round Robin load balancer to 4 GPU worker nodes.

The project structure is:

```
cse354-project/
├── client/
│   ├── __init__.py
│   └── load_generator.py
├── master/
│   ├── __init__.py
│   └── scheduler.py
├── workers/
│   ├── __init__.py
│   └── gpu_worker.py
├── lb/
│   ├── __init__.py
│   └── load_balancer.py
├── rag/
│   ├── __init__.py
│   └── retriever.py
├── llm/
│   ├── __init__.py
│   └── inference.py
├── common/
│   ├── __init__.py
│   └── models.py
└── main.py
```

---

## Objective

Extend the load balancer to support three routing strategies and update the worker to
track the stats each strategy needs. Add a comparison test that runs all three strategies
and prints a side-by-side results table.

Do NOT change the folder structure. Do NOT touch `rag/`, `llm/`, `master/`, or `common/`.
Only modify the files listed below.

---

## Files to Modify

### 1. `workers/gpu_worker.py`

Add three new instance variables to `GPUWorker.__init__`:

- `self.alive = True` — boolean flag, used by the load balancer to skip dead workers
- `self.active_requests = 0` — integer counter, incremented when a request starts, decremented when it finishes
- `self.avg_latency = 0.2` — float, updated with a rolling average after each request completes

Protect `active_requests` and `avg_latency` updates with a `threading.Lock()` so concurrent
threads do not corrupt the values.

The `process()` method should:
1. Acquire lock → increment `active_requests` → release lock
2. Record `start = time.time()`
3. Call `retrieve_context()` and `run_llm()` exactly as before
4. Acquire lock → decrement `active_requests` → update `avg_latency` as rolling average → release lock
5. Return the same dict as before: `{"id": ..., "result": ..., "latency": ...}`

Rolling average formula: `self.avg_latency = (self.avg_latency + latency) / 2`

---

### 2. `lb/load_balancer.py`

Replace the entire file. The new `LoadBalancer` class must:

**`__init__(self, workers, strategy='round_robin')`**
- Store `self.workers = workers`
- Store `self.strategy = strategy`
- Initialize `self.index = 0` for round robin tracking
- Initialize `self.lock = threading.Lock()`

**`get_next_worker(self)`**
- Filter workers to only those where `worker.alive == True`
- If no active workers exist, raise `Exception("No available workers")`
- Apply the selected strategy:

  **Round Robin** (`strategy='round_robin'`):
  - Pick `active[self.index % len(active)]`
  - Increment `self.index`
  - Return the chosen worker

  **Least Connections** (`strategy='least_connections'`):
  - Return the worker with the lowest `active_requests` value
  - Use `min(active, key=lambda w: w.active_requests)`

  **Load Aware** (`strategy='load_aware'`):
  - Return the worker with the lowest combined score
  - Score formula: `worker.active_requests * worker.avg_latency`
  - Use `min(active, key=lambda w: w.active_requests * w.avg_latency)`

- Wrap the entire method body in `with self.lock:` to make it thread-safe

**`dispatch(self, request)`**
- Call `self.get_next_worker()`
- Call `worker.process(request)`
- Return the result

**`remove_worker(self, worker_id)`**
- Find the worker with matching `id`
- Set `worker.alive = False`
- Print `[LB] Worker {worker_id} removed from pool`

---

### 3. `client/load_generator.py`

Update `simulate_user()` to append each response latency to a shared `results` list:

```
simulate_user(scheduler, user_id, results)
```

Update `run_load_test()` to:
- Accept a `label` parameter (string) for logging which strategy is running
- Create a shared `results = []` list protected by a `threading.Lock()`
- Record `start = time.time()` before spawning threads
- Record `end = time.time()` after all threads join
- Calculate and return a dict with these keys:
  - `label` — the strategy name passed in
  - `num_users` — total users simulated
  - `total_time` — end minus start, rounded to 2 decimal places
  - `throughput` — num_users / total_time, rounded to 1 decimal place
  - `avg_latency` — mean of results list, rounded to 3 decimal places
  - `min_latency` — min of results list, rounded to 3 decimal places
  - `max_latency` — max of results list, rounded to 3 decimal places

Do NOT print the stats block inside `run_load_test()` anymore.
The caller (`main.py`) will handle printing.

---

### 4. `main.py`

Replace the entire file with a comparison runner that:

1. Defines `NUM_USERS = 200` and `NUM_WORKERS = 4` as constants at the top
2. Runs the load test three times — once per strategy — in this order:
   - `'round_robin'`
   - `'least_connections'`
   - `'load_aware'`
3. For each run:
   - Creates a fresh list of `GPUWorker` instances (do not reuse workers between runs)
   - Creates a `LoadBalancer` with the current strategy
   - Creates a `Scheduler`
   - Calls `run_load_test(scheduler, num_users=NUM_USERS, label=strategy_name)`
   - Stores the returned stats dict in a list
4. After all three runs, prints a formatted comparison table:

```
============================================================
  LOAD BALANCING STRATEGY COMPARISON — 200 users, 4 workers
============================================================
  Strategy            Total Time   Throughput   Avg Latency
  ----------------------------------------------------------
  round_robin           3.21s       62.3 req/s    0.214s
  least_connections     2.98s       67.1 req/s    0.209s
  load_aware            3.05s       65.6 req/s    0.211s
============================================================
```

Use f-strings and `str.ljust()` or formatted string padding to align the columns.

---

## Acceptance Criteria

The implementation is complete when:

- [ ] `python main.py` runs without errors
- [ ] All three strategies produce output in the comparison table
- [ ] Latency values are all approximately 0.2s (±0.05s) — confirms the pipeline still works end to end
- [ ] Throughput values differ between strategies — confirms each strategy is actually doing something different
- [ ] No race conditions — running the same strategy multiple times produces consistent results
- [ ] The `alive` flag works — manually setting `workers[0].alive = False` before a run causes that worker to be skipped with no crash

---

## Do Not Change

- `common/models.py` — Request and Response dataclasses stay as-is
- `master/scheduler.py` — no changes needed
- `rag/retriever.py` — stub stays as-is, RAG is Phase 3
- `llm/inference.py` — stub stays as-is
- Any `__init__.py` files
- The folder structure

---

## Notes for Claude Code

- All files already exist — this is modification only, not greenfield
- The project runs with `python main.py` from the project root
- If imports fail, `PYTHONPATH=.` needs to be set
- Python version is 3.9+
- No new dependencies needed — only stdlib (`threading`, `time`, `dataclasses`)
- The `time.sleep(0.2)` in `llm/inference.py` is intentional — it simulates GPU delay
- Do not add async/await — keep everything synchronous threading