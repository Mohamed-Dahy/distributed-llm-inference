# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the System

```bash
# From the project root
PYTHONPATH=. python3 main.py
```

No build step, no test runner, no linter configured. Python 3.9+ required, stdlib only — no external dependencies.

Scale and fault tolerance behaviour are controlled by constants at the top of `main.py`:

```python
NUM_USERS = 1000      # concurrent simulated users per strategy run
NUM_WORKERS = 4       # simulated GPU worker nodes

# Inside the loop:
lb.remove_worker(0)                                          # pre-kills worker 0 before the run
sim = FailureSimulator(workers, failure_delay=0.1, num_failures=2)  # kills 2 more mid-run
```

## Architecture

Request flow (synchronous threading — no async anywhere):

```
client threads (NUM_USERS × threading.Thread)
    → Scheduler.handle_request()
    → LoadBalancer.dispatch()          [retries up to max_retries=3 on WorkerDeadException]
        → LoadBalancer.get_next_worker()   [lock-protected; picks via strategy]
        → GPUWorker.process()
            → retrieve_context()       [rag/retriever.py — stub]
            → run_llm()                [llm/inference.py  — 0.2s sleep stub]
            → is_alive check (post-inference)
    → returns dict {"id", "result", "latency"}
```

`main.py` runs the full pipeline three times (once per strategy), collects stats dicts, then prints a comparison table.

## Key Design Details

**Two `is_alive` checks in `GPUWorker.process()`** — one at entry, one after `run_llm()` returns. The post-inference check is what actually catches mid-run failures: all 1000 threads dispatch almost simultaneously, so the entry check is always passed before `FailureSimulator` fires. Only the post-inference check fires after the 0.2s sleep.

**Failure only produces `"FAILED"` responses when all workers are dead.** With `num_failures=N` leaving any alive workers, `dispatch()`'s retry loop always finds a survivor and succeeds. To force visible failures: `remove_worker(0)` + `num_failures=3` = all 4 workers dead → `get_alive_workers()` raises `Exception("ALL WORKERS ARE DOWN")` → escapes the retry loop → `simulate_user()` catches it → `result="FAILED"`.

**Thread safety — two separate locks:**
- `LoadBalancer.lock` — wraps all of `get_next_worker()`, protecting the round-robin index and strategy dispatch.
- `GPUWorker._lock` — protects `active_requests` (inc/dec around inference) and `avg_latency` rolling average. The lock is NOT held during `run_llm()` — only around the counter updates.

**Worker stats used by strategies:**
- `active_requests` — used by `least_connections` (pick minimum)
- `avg_latency` — rolling average `(old + new) / 2`; used by `load_aware` (score = `active_requests × avg_latency`)

**`GPUWorker.process()` returns a plain `dict`**, not the `Response` dataclass in `common/models.py`. The `Response` dataclass is currently unused.

**`load_generator.py` collects full response dicts** (not just latencies). The summary separates successful responses (`result != "FAILED"`) from failed ones and prints dead worker IDs by inspecting `scheduler.lb.workers`.

**`SAMPLE_QUERIES`** in `load_generator.py` cycles through 20 ML-themed queries via `user_id % len(SAMPLE_QUERIES)` — currently assigned to `query` but the `Request` is still constructed with `f"Query {user_id}"` (the variable `query` is unused).

## Stub Extension Points

Replace these two function bodies to plug in real retrieval or a real LLM without touching anything else:
- `rag/retriever.py` → `retrieve_context(query)` — currently returns a formatted string
- `llm/inference.py` → `run_llm(query, context)` — currently sleeps 0.2s and returns a template string

## Implementation Status

| Feature | Status |
|---|---|
| Round Robin, Least Connections, Load-Aware LB | Done |
| Worker `is_alive` flag, failure detection, retry dispatch | Done |
| `FailureSimulator` background daemon thread | Done |
| Failed/successful request counting + dead worker report | Done |
| Heartbeat monitor (`master/heartbeat.py`) | Not implemented |
| ChromaDB RAG integration | Phase 3 stub only |
| Test suite | No test files exist |
| `requirements.txt` | Does not exist (no external deps currently) |
