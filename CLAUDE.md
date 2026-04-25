# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the System

```bash
pip install -r requirements.txt
```

**Stub mode** (default — no external services needed):
```bash
PYTHONPATH=. python3 main.py
```

**Real LLM mode** (requires `GROQ_API_KEY` in `.env`, keep `NUM_USERS` ≤ 5 due to rate limits):
```bash
USE_REAL_LLM=true PYTHONPATH=. python3 main.py
```

**NGINX mode** (requires NGINX running with `nginx/nginx.conf`; workers spawn automatically):
```bash
PYTHONPATH=. python3 main_nginx.py
```

**Real LLM demo** (5 users, full RAG → Groq pipeline, prints actual answers):
```bash
USE_REAL_LLM=true PYTHONPATH=. python3 demo_real_llm.py
```

**RAG pipeline test** (validates ChromaDB retrieval in isolation):
```bash
PYTHONPATH=. python3 test_rag.py
```

Scale and fault tolerance are configured at the top of `main.py` via `NUM_USERS`, `NUM_WORKERS`, `lb.remove_worker(0)`, and `FailureSimulator(failure_delay, num_failures)`.

## Two Modes of Operation

The system has two distinct architectures that share the `GPUWorker` core:

**In-process mode** (`main.py`): All components run in one Python process. `LoadBalancer` holds direct references to `GPUWorker` objects and calls `worker.process()` in-process. The three LB strategies (`round_robin`, `least_connections`, `load_aware`) are compared sequentially.

**HTTP/NGINX mode** (`main_nginx.py`): Each worker runs as a separate FastAPI process (`workers/worker_server.py`) on ports 8001–8004. NGINX at port 8080 acts as the actual load balancer, and `client/http_load_generator.py` sends HTTP requests directly to `http://127.0.0.1:8080/process`. The Python LB code is bypassed entirely — NGINX does the routing. Worker endpoints: `GET /health`, `GET /stats`, `POST /process`.

## Request Flow (In-Process Mode)

```
client threads (NUM_USERS × threading.Thread)
    → Scheduler.handle_request()          [master/scheduler.py — thin logger/delegator]
    → LoadBalancer.dispatch()             [lb/load_balancer.py — retries up to 3× on WorkerDeadException]
        → LoadBalancer.get_next_worker()  [lock-protected; selects via strategy]
        → GPUWorker.process()             [workers/gpu_worker.py]
            → retrieve_context(query)     [rag/retriever.py — ChromaDB or stub fallback]
            → run_llm(query, context)     [llm/inference.py — Groq API or 0.2s sleep stub]
            → post-inference is_alive check
    → returns dict {"id", "result", "latency"}
```

## Key Design Details

**Two `is_alive` checks in `GPUWorker.process()`** — one at entry, one after `run_llm()` returns. The post-inference check is what actually catches mid-run failures: all threads dispatch almost simultaneously, so the entry check is always passed before `FailureSimulator` fires. Only the post-inference check fires after the 0.2s sleep.

**Failure only produces `"FAILED"` responses when all workers are dead.** With any alive workers remaining, `dispatch()`'s retry loop always finds a survivor. To force visible failures: `remove_worker(0)` + `num_failures=3` kills all 4 workers → `get_alive_workers()` raises `Exception("ALL WORKERS ARE DOWN")` → escapes the retry loop → `simulate_user()` catches it → `result="FAILED"`.

**Thread safety — two separate locks:**
- `LoadBalancer.lock` — wraps all of `get_next_worker()`, protecting the round-robin index and strategy dispatch.
- `GPUWorker._lock` — protects `active_requests` (inc/dec) and `avg_latency` rolling average. NOT held during `run_llm()` — only around counter updates.

**Worker stats used by LB strategies:**
- `active_requests` — used by `least_connections` (pick minimum)
- `avg_latency` — rolling average `(old + new) / 2`; used by `load_aware` (score = `active_requests × avg_latency`)

**`GPUWorker.process()` returns a plain `dict`** (`{"id", "result", "latency"}`), not the `Response` dataclass in `common/models.py`. The `Response` dataclass is currently unused.

**RAG module initialises at import time** — `rag/retriever.py` connects to ChromaDB and ingests PDFs from `rag/Data/` when first imported. If `rag/Data/` is empty or missing, it silently falls back to stub retrieval. The ChromaDB store persists at `rag/chroma_db/`.

## Stub Extension Points

Replace these function bodies to plug in real retrieval or a real LLM without touching anything else:
- [rag/retriever.py](rag/retriever.py) → `retrieve_context(query)` — ChromaDB vector search (falls back to stub if no PDFs)
- [llm/inference.py](llm/inference.py) → `run_llm(query, context)` — Groq API (`USE_REAL_LLM=true`) or 0.2s sleep stub

## Known Quirks

- `SAMPLE_QUERIES` in [client/load_generator.py](client/load_generator.py) is used correctly — the `Request` is now constructed with the cycling query (fixed from an earlier bug where the variable was unused).
- `nginx/nginx.conf` has Windows-style absolute paths (`C:/nginx-1.30.0/...`) for `error_log` and `pid` — update these if running on Linux/macOS.
- `FailureSimulator` is a daemon thread — it fires once after `failure_delay` seconds and kills `num_failures` random alive workers, then exits. It does not reset between strategy runs in `main.py` (a new one is created per run).
