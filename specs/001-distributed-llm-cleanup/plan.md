# Implementation Plan: Distributed LLM Inference – Cleanup & Multi-Laptop Setup

**Branch**: `001-distributed-llm-cleanup` | **Date**: 2026-05-09 | **Spec**: [spec.md](spec.md)

## Summary

Refactor the existing distributed LLM inference system from its current mixed in-process / HTTP architecture into a clean multi-laptop deployment. The primary changes are: (1) consolidate all `master/` modules into one file `master/client_support.py` (HTTP-aware versions of scheduler, heartbeat, performance monitor, queue monitor, and results logger) and import it from `client_nginx_only.py`; (2) add comprehensive per-request/response logging with a timestamped results file; (3) extend `worker_server.py` with explicit STUB/Ollama mode control and full request logging; (4) fix `nginx/nginx.conf` for macOS/Linux and 4-worker upstreams; (5) delete only the files that are purely in-process-only with no HTTP equivalent.

---

## Technical Context

**Language/Version**: Python 3.9+
**Primary Dependencies**: FastAPI, uvicorn, httpx, python-dotenv, chromadb, sentence-transformers
**Storage**: Append-only timestamped log files in `logs/`; ChromaDB vector store in `rag/chroma_db/`
**Testing**: Manual integration test — start workers, run client, inspect console and log file
**Target Platform**: macOS / Linux laptops on a shared local network
**Project Type**: Distributed web service (worker HTTP servers + NGINX reverse proxy + client script)
**Performance Goals**: Support 20–50 concurrent simulated users; 1000 requests across 4 workers must complete within 30 minutes (1800s) wall clock; each individual request must complete in under 120s (Ollama timeout)
**Constraints**: All 5 laptops must be on the same LAN; worker IPs must be known before client launch; minimum throughput for 30-min target = 1000/1800 ≈ 0.56 req/s sustained
**Scale/Scope**: 4 worker laptops, 1 client laptop, 20–50 concurrent users per demo run

---

## Constitution Check

The project constitution is a blank template — no active gates. No violations to track.

---

## Project Structure

### Documentation (this feature)

```text
specs/001-distributed-llm-cleanup/
├── plan.md              ← this file
├── research.md          ← Phase 0
├── data-model.md        ← Phase 1
├── contracts/           ← Phase 1
│   └── worker-api.md
├── quickstart.md        ← Phase 1
└── tasks.md             ← Phase 2 (/speckit-tasks — not created here)
```

### Source Code — files to KEEP / CREATE / MODIFY (after cleanup)

```text
distributed-llm-inference/
├── client_nginx_only.py        ← REWRITE: imports from master.client_support; handles run lifecycle only
├── master/
│   ├── __init__.py             ← keep
│   └── client_support.py       ← CREATE: consolidates all master modules into HTTP-aware versions
│       (replaces: scheduler.py, heartbeat.py, monitor.py, queue_monitor.py)
├── nginx/
│   └── nginx.conf              ← FIX: remove Windows paths, add 4 worker upstreams
├── workers/
│   ├── worker_server.py        ← ENHANCE: explicit LLM mode env var + per-request logging
│   └── gpu_worker.py           ← keep (used by worker_server)
├── llm/
│   └── inference.py            ← keep (STUB/Ollama/Groq — no changes needed)
├── rag/
│   ├── retriever.py            ← keep
│   ├── ingest.py               ← keep
│   └── Data/                   ← keep (ML lecture PDFs)
├── client/
│   ├── http_load_generator.py  ← UPDATE: accept logger; log sent + received
│   └── load_generator.py       ← TRIM: keep SAMPLE_QUERIES only, remove in-process functions
├── common/
│   └── models.py               ← keep (Request, WorkerDeadException, WorkerOverloadedException)
├── requirements.txt            ← keep
├── .env                        ← keep (not committed)
└── CLAUDE.md                   ← keep (update run instructions)
```

### `master/client_support.py` — Contents

This single file consolidates and adapts all four in-process master modules into their HTTP-aware equivalents:

| Class | Source | What changes |
|-------|--------|-------------|
| `ClientScheduler` | `master/scheduler.py` | Replace `lb.dispatch()` with `httpx.post(NGINX_URL/process)` |
| `HTTPHeartbeatMonitor` | `master/heartbeat.py` + existing in `client_nginx_only.py` | Poll `/health` via httpx instead of reading `w.is_alive` |
| `HTTPPerformanceMonitor` | `master/monitor.py` + existing in `client_nginx_only.py` | Poll `/stats` via httpx instead of reading worker object fields |
| `QueueMonitor` | `master/queue_monitor.py` | Works unchanged — calls `scheduler.get_queue_stats()` |
| `ResultsLogger` | new | Write structured log lines to stdout + timestamped file |

### Files to DELETE

```text
main.py                         ← in-process orchestrator only
main_nginx.py                   ← old local-spawn launcher (replaced by client_nginx_only.py)
SCHEDULER_USAGE_EXAMPLE.py      ← example script, not operational
COMPLETE_TESTING_GUIDE.md       ← outdated, replaced by quickstart.md
test_scheduler_integration.py   ← in-process integration test
test_rag.py                     ← standalone RAG test (optional: move to docs instead)
lb/                             ← entire directory (in-process load balancer, not used in HTTP mode)
  ├── load_balancer.py
  └── __init__.py
master/scheduler.py             ← replaced by ClientScheduler in master/client_support.py
master/heartbeat.py             ← replaced by HTTPHeartbeatMonitor in master/client_support.py
master/monitor.py               ← replaced by HTTPPerformanceMonitor in master/client_support.py
master/queue_monitor.py         ← replaced by QueueMonitor in master/client_support.py
workers/failure_simulator.py    ← in-process only (failure now triggered via HTTP endpoint)
```

---

## Phase 0: Research

### R-1: Queue-Based Scheduler in the HTTP Client

**Decision**: Implement the scheduler directly inside `client_nginx_only.py` using Python's `queue.Queue` + `threading.Thread` consumer loop. No dependency on the deleted `master/scheduler.py`.

**Design**:
- `ClientScheduler` class owns a `queue.Queue` and spawns `NUM_CONSUMERS` daemon threads on init.
- Each consumer thread runs a `_consume()` loop: dequeue a `(request_id, query, response_queue)` tuple, POST to `NGINX_URL/process`, put result onto `response_queue`.
- The main thread enqueues a request and blocks on `response_queue.get(timeout=REQUEST_TIMEOUT)`.
- Queue size and consumer count are configurable via env vars (`NUM_CONSUMERS`, `REQUEST_TIMEOUT`).

**Rationale**: Mirrors the existing `master/scheduler.py` design but self-contained in the client file, eliminating the dependency on the deleted `master/` package.

**Alternatives considered**:
- `asyncio` + `aiohttp` — cleaner for I/O but requires rewriting all monitoring threads; overkill for a demo with <50 users.
- `ThreadPoolExecutor` submit-per-request — simpler but no bounded queue, can flood NGINX.

---

### R-2: Per-Request / Per-Response Logging + Results File

**Decision**: Add a `Logger` helper class (inline in `client_nginx_only.py` and in `worker_server.py`) that writes to both `sys.stdout` and a shared file handle opened at startup.

**Client log format (sent)**:
```
[SENT] 2026-05-09 14:03:01.123 | Request #42 | Q: what is supervised learning...
```

**Client log format (received — results file entry)**:
```
RESPONDS FROM: Worker 2 | Request #42 | Question: what is supervised learning... | Response: Supervised learning is... | Latency: 312 ms
```

**Worker log format (received)**:
```
[RECV] 2026-05-09 14:03:01.456 | Worker 1 | Request #42 | Q: what is supervised learning...
```

**Worker log format (sent)**:
```
[RESP] 2026-05-09 14:03:01.768 | Worker 1 | Request #42 | Latency: 312ms | R: Supervised learning is...
```

**Results file**: `logs/results_YYYYMMDD_HHMMSS.txt` — opened once at client startup, one entry appended per response (including TIMEOUT and ERROR entries). Directory created automatically if missing.

**Rationale**: File-per-run prevents log interleaving across runs and makes it easy to submit a specific run's output for grading.

**Alternatives considered**: JSON lines format — more machine-readable but less human-readable for submission; rejected.

---

### R-3: NGINX Config for 4 Distributed Workers

**Decision**: Update `nginx/nginx.conf` to list 4 upstream servers by placeholder IP. Operators set real IPs by editing the conf (or via env substitution).

**Key changes**:
- Remove Windows absolute paths (`C:/nginx-1.30.0/...`); use relative or standard macOS/Linux paths.
- Add 4 `server` lines to `upstream gpu_workers` block.
- Keep `least_conn` load balancing (fair under variable Ollama latencies).
- Extend `proxy_read_timeout` to `180s` to accommodate slow Ollama responses.
- Add `/simulate_failure` and `/reset` proxy locations so the client can trigger failure from one place.

**Template IPs**: `WORKER_1_IP:8001`, `WORKER_2_IP:8002`, `WORKER_3_IP:8003`, `WORKER_4_IP:8004`. Documented in quickstart.md that operators must substitute real IPs.

---

### R-4: Worker LLM Mode Control

**Decision**: `worker_server.py` reads `LLM_MODE` env var (`stub` or `ollama`). It sets `USE_REAL_LLM=true/false` accordingly before `gpu_worker` / `llm.inference` are imported, OR passes the mode into `run_llm` directly.

**Simplest approach**: Since `llm/inference.py` already checks `USE_REAL_LLM` at module load, the worker startup script just needs to document: set `LLM_MODE=stub` → `USE_REAL_LLM=false`; set `LLM_MODE=ollama` → `USE_REAL_LLM=true`. We add a check at the top of `worker_server.py` that reads `LLM_MODE` and sets `os.environ["USE_REAL_LLM"]` before the import of `gpu_worker` (which transitively imports `llm.inference`).

**Startup command (stub)**:
```bash
LLM_MODE=stub WORKER_ID=1 python worker_server.py
```
**Startup command (ollama)**:
```bash
LLM_MODE=ollama WORKER_ID=1 python worker_server.py
```

---

## Phase 1: Design

### Data Model (`data-model.md`)

See [data-model.md](data-model.md).

### API Contracts (`contracts/worker-api.md`)

See [contracts/worker-api.md](contracts/worker-api.md).

### Quickstart (`quickstart.md`)

See [quickstart.md](quickstart.md).

---

## Implementation Phases (for /speckit-tasks)

### Phase A – File Cleanup (no logic changes)
Delete in-process-only files listed in "Files to DELETE" above. Do this first to prevent stale imports from interfering. Note: the `master/` directory itself is NOT deleted — only its four individual source files are removed once their content is consolidated into `master/client_support.py`.

### Phase B – Create `master/client_support.py`
Create the consolidated support module containing five classes in this order:

1. **`ResultsLogger`** — accepts a file path, opens it on `__init__`, exposes `log_sent(req_id, query)` and `log_response(worker_id, req_id, query, result, latency_ms)`, closes file on `close()`. Writes every call to both stdout and file simultaneously.

2. **`ClientScheduler`** — adapted from `master/scheduler.py`. Replace `self.lb.dispatch(request)` with an `httpx.post(f"{nginx_url}/process", json={...}, timeout=...)` call. Keep the `queue.Queue` + `ThreadPoolExecutor` consumer loop unchanged. `get_queue_stats()` returns `{"queue_size": ..., "num_consumers": ...}`.

3. **`HTTPHeartbeatMonitor`** — adapted from `master/heartbeat.py` + the version already in `client_nginx_only.py`. Polls `{url}/health` via httpx every `interval` seconds. Logs ALERT/ONLINE transitions.

4. **`HTTPPerformanceMonitor`** — adapted from `master/monitor.py` + the version already in `client_nginx_only.py`. Polls `{url}/stats` via httpx every `interval` seconds. Prints per-worker table.

5. **`QueueMonitor`** — taken directly from `master/queue_monitor.py` with no changes (it already calls `scheduler.get_queue_stats()` which `ClientScheduler` implements).

### Phase C – Fix `nginx/nginx.conf`
- Remove Windows-specific `error_log` and `pid` paths (use standard Linux/macOS paths)
- Change 2 upstream server entries → 4 (placeholder IPs: `WORKER_1_IP`, etc.)
- Extend `proxy_read_timeout` from `60s` → `180s`
- Change `proxy_next_upstream_tries` from `2` → `4`
- Add proxy locations for `/simulate_failure` and `/reset`

### Phase D – Enhance `worker_server.py`
- At module top (before any other import): read `LLM_MODE` env var; if `ollama` set `os.environ["USE_REAL_LLM"] = "true"`, else set `"false"`
- Accept `WORKER_ID` from env var with `sys.argv[1]` as fallback
- In `process()` endpoint: log `[RECV]` line immediately on arrival, log `[RESP]` line before returning
- Print startup banner: `[Worker N] Starting on port XXXX | LLM mode: stub/ollama`
- Add **`POST /revive`** endpoint — sets `is_alive = True` only, does NOT reset stats; logs `[RECOVERY] Worker N is back ONLINE`
- Keep **`POST /reset`** endpoint as-is (revive + full stats clear — useful for a fresh run)
- Keep **`POST /simulate_failure`** endpoint as-is (sets `is_alive = False`)

**Failure/recovery flow for demo**:
```
curl -X POST http://<WORKER_IP>:<PORT>/simulate_failure   # kill
curl -X POST http://<WORKER_IP>:<PORT>/revive             # restore (stats preserved)
curl -X POST http://<WORKER_IP>:<PORT>/reset              # restore (stats cleared)
```

### Phase E – Rewrite `client_nginx_only.py`
- Remove the `HTTPHeartbeatMonitor` and `HTTPPerformanceMonitor` classes (now in `master/client_support.py`)
- Import: `from master.client_support import ClientScheduler, HTTPHeartbeatMonitor, HTTPPerformanceMonitor, QueueMonitor, ResultsLogger`
- In `main()`:
  - Create `ResultsLogger` (opens timestamped file in `logs/`)
  - Create `ClientScheduler(nginx_url, num_consumers, request_timeout)`
  - Create and start `HTTPHeartbeatMonitor`, `HTTPPerformanceMonitor`, `QueueMonitor`
  - Call `run_http_load_test(num_users, label, scheduler, logger)` (updated signature)
  - Stop monitors, close logger
- Read 4 worker URLs from `WORKER_1`..`WORKER_4` env vars; default to `127.0.0.1:8001–8004`
- **Performance gate**: after `run_http_load_test()` returns, if `num_users >= 1000`:
  - Compute `total_time` from the run result
  - Compare against `PERF_TARGET_SECONDS` (default: `1800`)
  - Print and append to results file:
    ```
    [PERF] 1000-request target: PASS (total=1423s, limit=1800s)
    ```
    or:
    ```
    [PERF] 1000-request target: FAIL (total=2104s, limit=1800s)
    ```
  - Also report `throughput` (req/s) and `avg_latency` alongside the PASS/FAIL line

### Phase F – Update `client/http_load_generator.py`
- Add `scheduler` and `logger` parameters to `run_http_load_test()`
- Inside `simulate_http_user()`: call `logger.log_sent(user_id, query)` before dispatch; call `logger.log_response(...)` after response received
- Dispatch via `scheduler` (calls `ClientScheduler.handle_request()`) instead of raw `httpx.post()`

### Phase G – Trim `client/load_generator.py`
- Remove `simulate_user()` and `run_load_test()` functions (both depend on in-process `Scheduler` and `GPUWorker`)
- Keep `SAMPLE_QUERIES` list unchanged

### Phase H – Update `CLAUDE.md`
- Remove references to `main.py`, `main_nginx.py`, `lb/`, and the old in-process mode
- Add reference to `quickstart.md` for multi-laptop setup
- Update run command section to show worker and client startup

---

## Failure Simulation — How to Test

### Method 1: HTTP endpoint (recommended for demo)

**Simulate failure** (sets `is_alive = False`, stats preserved):
```bash
curl -X POST http://<WORKER_IP>:<PORT>/simulate_failure
```
New requests to that worker return HTTP 500. NGINX stops routing to it. Heartbeat monitor logs `ALERT`.

**Revive** (sets `is_alive = True`, stats preserved — preferred for demos):
```bash
curl -X POST http://<WORKER_IP>:<PORT>/revive
```
Heartbeat monitor logs `ONLINE`. NGINX resumes routing to it. Stats show full history across the failure/recovery cycle.

**Reset** (sets `is_alive = True` + clears all stats — use for a fresh run):
```bash
curl -X POST http://<WORKER_IP>:<PORT>/reset
```

### Method 2: Kill the process (physical laptop failure simulation)
Stop the `worker_server.py` process on a laptop (`Ctrl+C` or `kill`). NGINX health checks will detect it is unreachable and stop routing within one `proxy_connect_timeout` (30s). The heartbeat monitor will log `ALERT`.

### Test Scenarios
1. **Single worker failure**: Trigger failure on Worker 2 mid-run → verify remaining requests route to Workers 1, 3, 4.
2. **Multi-worker failure**: Fail 3 of 4 workers → verify system continues with 1 alive worker.
3. **Total failure**: Fail all 4 workers → verify client logs ERROR for every pending request (no crash).
4. **Recovery**: Revive a failed worker → verify subsequent requests are routed to it again.
5. **Timeout**: Set `REQUEST_TIMEOUT=5` and send requests to Ollama → verify TIMEOUT entries appear in results file.
