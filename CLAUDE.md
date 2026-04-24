# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the System

```bash
# Run all three load balancing strategies and print a comparison table
python main.py

# If imports fail (module not found)
export PYTHONPATH=.        # Mac/Linux
set PYTHONPATH=.           # Windows
```

No build step, no test runner, no linter configured. Python 3.9+ required. No external dependencies — stdlib only (`threading`, `time`, `dataclasses`).

Scale is controlled by two constants at the top of `main.py`:

```python
NUM_USERS = 1000    # concurrent simulated users per strategy run
NUM_WORKERS = 100   # simulated GPU worker nodes
```

## Architecture

Request flow (synchronous, threading-based — no async):

```
client threads (N × threading.Thread)
    → Scheduler.handle_request()
    → LoadBalancer.dispatch() / get_next_worker()
    → GPUWorker.process()
        → retrieve_context()   [rag/retriever.py — stub]
        → run_llm()            [llm/inference.py  — 0.2s sleep stub]
    → returns dict {"id", "result", "latency"}
```

`main.py` runs the full pipeline three times (once per strategy), collects stats dicts from `run_load_test()`, then prints a formatted comparison table.

## Key Design Details

**Thread safety — two separate locks:**
- `LoadBalancer._lock` — wraps the entire `get_next_worker()` body, protecting the round-robin index and the `active` worker filter.
- `GPUWorker._lock` — protects `active_requests` (inc/dec around the inference call) and the `avg_latency` rolling average update.

**Worker state tracked per node:**
- `alive: bool` — load balancer filters out `alive=False` workers; set via `lb.remove_worker(worker_id)`.
- `active_requests: int` — used by `least_connections` strategy.
- `avg_latency: float` — rolling average `(old + new) / 2`; used by `load_aware` strategy (score = `active_requests × avg_latency`).

**`GPUWorker.process()` returns a plain `dict`**, not the `Response` dataclass defined in `common/models.py`. The dataclass is unused in the current code.

**Stub extension points:** Replace the bodies of `rag/retriever.py::retrieve_context()` and `llm/inference.py::run_llm()` to plug in real ChromaDB retrieval or a real LLM without touching anything else.

## Implementation Status

| Feature | Status |
|---|---|
| Round Robin, Least Connections, Load-Aware LB | Done (`lb/load_balancer.py`) |
| Worker alive flag + task reassignment | Done (`workers/gpu_worker.py`, `lb/load_balancer.py`) |
| Per-request latency metrics + comparison table | Done (`client/load_generator.py`, `main.py`) |
| Fault tolerance / heartbeat monitor | Phase 3 — not yet implemented (`master/heartbeat.py` does not exist) |
| ChromaDB RAG integration | Phase 3 — stub only |
| Test suite | Phase 4 — no test files exist yet |
| `requirements.txt` | Does not exist yet (no external deps needed currently) |

`phase2.md` in the project root is the implementation plan that was used to build Phase 2 — useful reference for the design decisions and acceptance criteria.
