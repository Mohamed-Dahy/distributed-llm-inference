# Research: Distributed LLM Inference Cleanup

## R-1: Consolidating `master/` into `master/client_support.py`

**Decision**: Keep the `master/` package but consolidate `scheduler.py`, `heartbeat.py`, `monitor.py`, and `queue_monitor.py` into a single file `master/client_support.py`. All four classes are rewritten as HTTP-aware equivalents. `client_nginx_only.py` imports from this file.

**`ClientScheduler`** (from `master/scheduler.py`): The queue + `ThreadPoolExecutor` consumer loop is kept intact. The only change is replacing `self.lb.dispatch(request)` with `httpx.post(f"{nginx_url}/process", json={"id": ..., "query": ...}, timeout=...)`. The response dict is built from the HTTP response JSON.

**`HTTPHeartbeatMonitor`** (from `master/heartbeat.py`): Instead of checking `w.is_alive` on a local object, polls `{worker_url}/health` via httpx every `interval` seconds. ALERT/ONLINE logic is identical.

**`HTTPPerformanceMonitor`** (from `master/monitor.py`): Instead of reading `w.active_requests`, `w.total_requests`, etc., polls `{worker_url}/stats` via httpx. Table format is preserved.

**`QueueMonitor`** (from `master/queue_monitor.py`): No changes — it already calls `scheduler.get_queue_stats()` which `ClientScheduler` implements.

**`ResultsLogger`** (new): Opens a timestamped file in `logs/`, provides `log_sent()` and `log_response()` methods that write to both stdout and the file simultaneously.

**Rationale**: Keeps the `master/` package as an organisational unit for all monitoring/scheduling support code, avoiding a fat `client_nginx_only.py`. Each module's logic is preserved; only the data source (in-process object vs HTTP endpoint) changes.

**Alternatives considered**:
- Delete `master/` entirely and inline everything in `client_nginx_only.py` — rejected by user preference; makes `client_nginx_only.py` too large and harder to maintain.
- Keep individual files in `master/` — rejected; leaves confusing partially-dead files alongside new ones.
- `asyncio` + `aiohttp` — cleaner for I/O but incompatible with existing threading model; rejected.

---

## R-2: Per-Request Logging and Results File

**Decision**: Single `ResultsLogger` class writes structured lines to stdout and a timestamped file simultaneously.

**Client sent format**: `[SENT] <timestamp> | Request #<id> | Q: <query>`
**Client received format**: `RESPONDS FROM: Worker <x> | Request #<id> | Question: <query> | Response: <answer> | Latency: <ms> ms`
**Worker received format**: `[RECV] <timestamp> | Worker <id> | Request #<id> | Q: <query>`
**Worker sent format**: `[RESP] <timestamp> | Worker <id> | Request #<id> | Latency: <ms>ms | R: <result>`

**Results file**: `logs/results_YYYYMMDD_HHMMSS.txt` — one file per run, appended as responses arrive.

**Rationale**: Human-readable format matches the user's exact specification. File-per-run avoids mixing results from multiple demo runs.

---

## R-3: NGINX Configuration for 4 Distributed Workers

**Decision**: Use `least_conn` upstream with 4 server entries. Extend `proxy_read_timeout` to `180s`. Add `/simulate_failure` and `/reset` proxy locations.

**Key changes from current config**:
- Remove Windows absolute paths for `error_log` and `pid`; use standard relative/Linux paths
- Change 2 upstream servers → 4 (with placeholder IPs to be filled in per deployment)
- Extend `proxy_read_timeout 60s` → `180s` (Ollama can be slow)
- Add `proxy_next_upstream_tries 4` (up from 2) to try all workers on failure
- Add `/simulate_failure` and `/reset` proxy locations

**Alternatives considered**:
- `ip_hash` — sticky sessions, unnecessary since requests are stateless; rejected.
- `round_robin` (default) — fair for equal-latency workers; `least_conn` is better when Ollama varies; kept `least_conn`.

---

## R-4: Worker LLM Mode Control

**Decision**: `worker_server.py` reads `LLM_MODE` env var (`stub`/`ollama`) and sets `os.environ["USE_REAL_LLM"]` before importing any modules that read it.

**Rationale**: `llm/inference.py` reads `USE_REAL_LLM` at import time (module-level). Setting it via `os.environ` before the import chain is the minimal-change approach — no refactor of `inference.py` needed.

**Startup convention**:
```bash
# Stub mode (no Ollama needed):
LLM_MODE=stub WORKER_ID=1 python worker_server.py

# Ollama mode (Ollama must be running):
LLM_MODE=ollama WORKER_ID=1 python worker_server.py
```

**Alternatives considered**:
- Pass mode as CLI arg — requires changing `sys.argv` handling; env var is cleaner for Docker/script use; rejected.
- Refactor `inference.py` to accept mode at call time — larger change, breaks existing API; rejected for this scope.

---

## R-5: Files to Delete

**Decision**: Delete files that are purely in-process-only. The `master/` directory itself is kept — only its individual source files are deleted once their content is incorporated into `master/client_support.py`.

**Files deleted**:
- `main.py`, `main_nginx.py` — in-process orchestrators
- `SCHEDULER_USAGE_EXAMPLE.py`, `COMPLETE_TESTING_GUIDE.md` — outdated docs/examples
- `test_scheduler_integration.py` — depends on deleted in-process scheduler
- `test_rag.py` — standalone test; optional move to `scripts/test_rag.py`
- `lb/load_balancer.py`, `lb/__init__.py` — in-process LB, not used in HTTP mode
- `master/scheduler.py`, `master/heartbeat.py`, `master/monitor.py`, `master/queue_monitor.py` — replaced by `master/client_support.py`
- `workers/failure_simulator.py` — in-process only; failure is now triggered via `/simulate_failure` HTTP endpoint

**What stays**: `master/__init__.py` (package identity). `workers/gpu_worker.py` (still used by `worker_server.py`). `client/load_generator.py` (keep only `SAMPLE_QUERIES`). `common/models.py` (keep `Request`, `WorkerDeadException`, `WorkerOverloadedException`).
