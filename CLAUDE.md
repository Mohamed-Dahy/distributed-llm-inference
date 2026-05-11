# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the System

```bash
pip install -r requirements.txt
```

### On each worker laptop (run one per laptop, IDs 1–4)

**Stub mode** (no Ollama needed — for testing):
```bash
PYTHONPATH=. LLM_MODE=stub WORKER_ID=1 python workers/worker_server.py
```

**Ollama mode** (real LLM — Ollama must be running):
```bash
ollama serve &
ollama pull mistral
PYTHONPATH=. LLM_MODE=ollama WORKER_ID=1 python workers/worker_server.py
```

### On the client laptop

Edit `nginx/nginx.conf` to set the real IP of each worker laptop, then start NGINX:
```bash
nginx -c $(pwd)/nginx/nginx.conf   # macOS/Linux
```

Run the client:
```bash
export WORKER_1=http://<IP1>:8001
export WORKER_2=http://<IP2>:8002
export WORKER_3=http://<IP3>:8003
export WORKER_4=http://<IP4>:8004
export NUM_USERS=20
PYTHONPATH=. python client_nginx_only.py
```

Results are saved to `logs/results_YYYYMMDD_HHMMSS.txt`.

For the full multi-laptop setup guide see [specs/001-distributed-llm-cleanup/quickstart.md](specs/001-distributed-llm-cleanup/quickstart.md).

## Failure Simulation

```bash
# Kill a worker (stats preserved):
curl -X POST http://<WORKER_IP>:<PORT>/simulate_failure

# Revive a worker (stats preserved):
curl -X POST http://<WORKER_IP>:<PORT>/revive

# Reset a worker (revive + clear stats):
curl -X POST http://<WORKER_IP>:<PORT>/reset
```

## Request Flow (HTTP/NGINX Mode)

```
client threads (NUM_USERS × threading.Thread)
    → ClientScheduler.handle_request()     [master/client_support.py]
        → enqueues {req_id, query, response_queue}
        → blocks on response_queue.get(timeout=REQUEST_TIMEOUT)
    ↓ (consumed by NUM_CONSUMERS persistent _consumer_loop threads)
    → httpx.post(NGINX_URL/process)        [NGINX routes via least_conn]
        → Worker laptop (worker_server.py)
            → GPUWorker.process()          [workers/gpu_worker.py]
                → retrieve_context(query)  [rag/retriever.py — ChromaDB]
                → run_llm(query, context)  [llm/inference.py — Ollama or stub]
            → logs [RECV] on arrival, [RESP] on return
    → response dict → response_queue.put()
    → ResultsLogger writes to logs/results_*.txt
```

## Key Design Details

**`ClientScheduler`** — lives in `master/client_support.py`. Uses `queue.Queue` + `ThreadPoolExecutor` consumer loop. Replaces direct `httpx.post()` calls with a bounded queue that prevents flooding NGINX.

**`master/client_support.py`** — consolidated module containing all client-side support classes:
- `ResultsLogger` — writes `[SENT]` and `RESPONDS FROM:` lines to stdout + timestamped file
- `ClientScheduler` — queue-based HTTP dispatcher to NGINX
- `HTTPHeartbeatMonitor` — polls `/health` on each worker; logs ALERT/ONLINE transitions
- `HTTPPerformanceMonitor` — polls `/stats` on each worker; prints a table every 5s
- `QueueMonitor` — polls `scheduler.get_queue_stats()`; tracks max queue depth

**`GPUWorker.process()`** — two `is_alive` checks: one at slot reservation, one after `run_llm()`. Both raise `WorkerDeadException` which propagates as HTTP 500 back to NGINX.

**Worker failure via HTTP** — `POST /simulate_failure` sets `is_alive = False` (HTTP 500 on next request). `POST /revive` sets `is_alive = True` (stats preserved). `POST /reset` sets `is_alive = True` and clears all stats.

**Performance SLA** — when `NUM_USERS >= 1000`, the client prints `[PERF] PASS/FAIL` against `PERF_TARGET_SECONDS` (default 1800s) after the run.

**RAG module** — `rag/retriever.py` connects to ChromaDB and ingests PDFs from `rag/Data/` at import time. Store persists at `rag/chroma_db/`. Falls back to stub if `rag/Data/` is empty.

## LLM Modes

`LLM_MODE=stub` → `USE_REAL_LLM=false` → `llm/inference.py` returns a canned response after 0.2s.
`LLM_MODE=ollama` → `USE_REAL_LLM=true` → `llm/inference.py` tries Groq (if `GROQ_API_KEY` set), then Ollama, then stub fallback.

Override Ollama model/URL: `OLLAMA_MODEL=mistral OLLAMA_URL=http://localhost:11434/api/generate`.

## Extension Points

- [rag/retriever.py](rag/retriever.py) → `retrieve_context(query)` — swap in a different vector store
- [llm/inference.py](llm/inference.py) → `run_llm(query, context)` — swap in a different LLM backend

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at [specs/001-distributed-llm-cleanup/plan.md](specs/001-distributed-llm-cleanup/plan.md)
<!-- SPECKIT END -->
