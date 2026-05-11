# Tasks: Distributed LLM Inference – Cleanup & Multi-Laptop Setup

**Input**: Design documents from `specs/001-distributed-llm-cleanup/`
**Branch**: `001-distributed-llm-cleanup`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared state dependencies)
- **[US#]**: Which user story this task belongs to
- All file paths are relative to the repository root

---

## Phase 1: Setup (File Cleanup)

**Purpose**: Remove in-process-only files that conflict with the distributed HTTP architecture. Must complete before any other work to prevent stale imports.

**⚠️ CRITICAL**: All user story work is blocked until this phase is complete.

- [x] T001 Delete root-level in-process files: `main.py`, `main_nginx.py`, `SCHEDULER_USAGE_EXAMPLE.py`, `COMPLETE_TESTING_GUIDE.md`, `test_scheduler_integration.py`, `test_rag.py`
- [x] T002 [P] Delete entire `lb/` directory (`lb/load_balancer.py`, `lb/__init__.py`)
- [x] T003 [P] Delete individual `master/` source files: `master/scheduler.py`, `master/heartbeat.py`, `master/monitor.py`, `master/queue_monitor.py` (keep `master/__init__.py`)
- [x] T004 [P] Delete `workers/failure_simulator.py`

**Checkpoint**: Project root contains only distributed-mode files. Running `python -c "import workers.worker_server"` should not fail due to missing packages.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create `master/client_support.py` — the consolidated HTTP-aware support module that `client_nginx_only.py` imports. Must be complete before Phase 4 (US2) can begin. US1 (worker enhancements) can proceed in parallel with this phase.

**⚠️ CRITICAL**: Phase 4 depends on this phase.

- [x] T005 Create `master/client_support.py` with `ResultsLogger` class: `__init__(self, log_dir="logs")` opens a timestamped file `logs/results_YYYYMMDD_HHMMSS.txt` (auto-creates `logs/` if missing); `log_sent(req_id, query)` writes `[SENT] <timestamp> | Request #<id> | Q: <query>` to stdout and file; `log_response(worker_id, req_id, query, result, latency_ms)` writes `RESPONDS FROM: Worker <x> | Request #<id> | Question: <query> | Response: <result> | Latency: <ms> ms` to stdout and file; `close()` flushes and closes file
- [x] T006 Add `ClientScheduler` class to `master/client_support.py`: `__init__(self, nginx_url, num_consumers=4, request_timeout=60)` creates a `queue.Queue` and spawns `num_consumers` daemon `threading.Thread` workers; `_consumer_loop()` dequeues items, calls `httpx.post(f"{nginx_url}/process", json={"id": req_id, "query": query}, timeout=request_timeout)`, puts response dict onto the per-request `response_queue`; `handle_request(req_id, query)` enqueues item and blocks on `response_queue.get(timeout=request_timeout)` returning `{"id", "result", "latency", "worker_id"}` or `{"result": "TIMEOUT"}` on timeout; `get_queue_stats()` returns `{"queue_size": ..., "num_consumers": ...}`; `shutdown()` sets running=False and drains queue
- [x] T007 [P] Add `HTTPHeartbeatMonitor` class to `master/client_support.py`: `__init__(self, worker_urls, interval=2)` stores URLs and initialises `_last_status = {url: None}`; `start()` spawns a daemon thread; `_run()` polls `GET {url}/health` with 1s timeout every `interval` seconds; logs `[Heartbeat] ALERT -- Worker {url} is DOWN` on transition alive→dead and `[Heartbeat] Worker {url} is back ONLINE` on dead→alive; `stop()` sets `running=False`
- [x] T008 [P] Add `HTTPPerformanceMonitor` class to `master/client_support.py`: `__init__(self, worker_urls, interval=5)` stores URLs; `start()` spawns daemon thread; `_report()` polls `GET {url}/stats` every `interval` seconds and prints a table showing worker_id, status, active_requests, total_requests, failed_requests, avg_latency, gpu_utilization for each URL; handles unreachable URLs gracefully with `-- unreachable` row; `stop()` sets `running=False`
- [x] T009 [P] Add `QueueMonitor` class to `master/client_support.py`: port directly from the deleted `master/queue_monitor.py` with no logic changes — `__init__(self, scheduler, interval=5)`, `start()`, `_monitor()` polls `scheduler.get_queue_stats()`, tracks `max_queue_size`, prints queue depth table, `stop()`, `get_stats()`

**Checkpoint**: `from master.client_support import ClientScheduler, HTTPHeartbeatMonitor, HTTPPerformanceMonitor, QueueMonitor, ResultsLogger` succeeds with no errors.

---

## Phase 3: User Story 1 – Worker on a Laptop (Priority: P1) 🎯

**Goal**: Each of the 4 worker laptops can run `worker_server.py` in either STUB or Ollama mode, with full per-request logging, and supports failure + revive via HTTP.

**Independent Test**: Start the worker with `LLM_MODE=stub WORKER_ID=1 PYTHONPATH=. python workers/worker_server.py`, send `curl -X POST http://localhost:8001/process -H 'Content-Type: application/json' -d '{"id":1,"query":"test"}'`, verify JSON response contains `worker_id`, `result`, `latency`. Then `curl -X POST http://localhost:8001/simulate_failure` → next `/process` returns HTTP 500. Then `curl -X POST http://localhost:8001/revive` → `/process` returns HTTP 200 again.

- [x] T010 [US1] In `workers/worker_server.py`, add LLM_MODE bootstrap at the very top (before any other imports): read `LLM_MODE = os.environ.get("LLM_MODE", "stub")`; if `LLM_MODE == "ollama"` set `os.environ["USE_REAL_LLM"] = "true"` else set `os.environ["USE_REAL_LLM"] = "false"`; this must appear before `from workers.gpu_worker import GPUWorker` and any other project imports
- [x] T011 [P] [US1] In `workers/worker_server.py`, change worker ID resolution: first try `WORKER_ID` env var (`int(os.environ.get("WORKER_ID", 0))`), fall back to `sys.argv[1]` if env var is 0 or missing; print startup banner `[Worker {worker_id}] Starting on port {port} | LLM mode: {LLM_MODE}` before `uvicorn.run()`
- [x] T012 [US1] In the `process()` endpoint of `workers/worker_server.py`, add a `[RECV]` log line immediately on arrival (before calling `worker.process()`): `print(f"[RECV] {datetime.now().isoformat()} | Worker {worker_id} | Request #{body.id} | Q: {body.query}")`; add `from datetime import datetime` import
- [x] T013 [US1] In the `process()` endpoint of `workers/worker_server.py`, add a `[RESP]` log line immediately before the `return` statement: `print(f"[RESP] {datetime.now().isoformat()} | Worker {worker_id} | Request #{result['id']} | Latency: {round(result['latency']*1000)}ms | R: {result['result'][:120]}")`; also log on exception path before raising HTTPException
- [x] T014 [P] [US1] Add `POST /revive` endpoint to `workers/worker_server.py`: sets `worker.is_alive = True` inside `worker._lock`, prints `[RECOVERY] Worker {worker_id} is back ONLINE`, returns `{"status": "revived", "worker_id": worker_id}`; this is distinct from `/reset` which also clears stats
- [x] T015 [P] [US1] In `workers/worker_server.py`, add `llm_mode` field to the `/stats` response dict: `"llm_mode": os.environ.get("LLM_MODE", "stub")` so operators can verify mode remotely
- [x] T016 [P] [US1] Fix `nginx/nginx.conf`: remove the two Windows-only lines (`error_log C:/...` and `pid C:/...`); change the `upstream gpu_workers` block from 2 servers to 4 servers using placeholder IPs `WORKER_1_IP:8001`, `WORKER_2_IP:8002`, `WORKER_3_IP:8003`, `WORKER_4_IP:8004`; change `proxy_read_timeout 60s` to `180s`; change `proxy_next_upstream_tries 2` to `4`; add `location /simulate_failure { proxy_pass http://gpu_workers; }` and `location /reset { proxy_pass http://gpu_workers; }` blocks

**Checkpoint**: Worker starts, logs LLM mode, logs every request+response, `/simulate_failure` kills it, `/revive` restores it.

---

## Phase 4: User Story 2 – Client Sends Requests via Queue → NGINX (Priority: P1)

**Goal**: The client laptop runs `client_nginx_only.py`, queues requests through `ClientScheduler`, consumer threads POST to NGINX, all requests sent and responses received are logged, results are saved to a timestamped file.

**Prerequisite**: Phase 2 (Foundational) must be complete — `master/client_support.py` must exist.

**Independent Test**: With 1 worker running in stub mode and NGINX running, run `NUM_USERS=5 PYTHONPATH=. python client_nginx_only.py`, verify console shows `[SENT]` lines before dispatch and `RESPONDS FROM:` lines after, then open `logs/results_*.txt` and confirm 5 entries.

- [x] T017 [US2] Trim `client/load_generator.py`: delete the `simulate_user()` function and `run_load_test()` function entirely (both depend on the deleted in-process `Scheduler` and `GPUWorker`); keep `SAMPLE_QUERIES` list unchanged; keep `__init__.py`
- [x] T018 [US2] Rewrite `client_nginx_only.py`: remove the inline `HTTPHeartbeatMonitor` and `HTTPPerformanceMonitor` class definitions (they now live in `master/client_support.py`); add import `from master.client_support import ClientScheduler, HTTPHeartbeatMonitor, HTTPPerformanceMonitor, QueueMonitor, ResultsLogger`; read 4 worker URLs from env vars `WORKER_1..WORKER_4` with defaults `http://127.0.0.1:8001..8004`; update `wait_for_workers()` to accept the list of 4 URLs; keep the existing `main()` structure but wire through `ClientScheduler` and `ResultsLogger`
- [x] T019 [US2] In `client_nginx_only.py` `main()`, instantiate and wire all components: `logger = ResultsLogger()`, `scheduler = ClientScheduler(NGINX_URL, NUM_CONSUMERS, REQUEST_TIMEOUT)`, start `HTTPHeartbeatMonitor(worker_urls)`, `HTTPPerformanceMonitor(worker_urls)`, `QueueMonitor(scheduler)`; call `run_http_load_test(num_users=NUM_USERS, label="nginx_distributed", scheduler=scheduler, logger=logger)`; stop all monitors and call `logger.close()` after the run; read `NUM_CONSUMERS = int(os.getenv("NUM_CONSUMERS", 4))` and `REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 60))` from env
- [x] T020 [US2] Update `client/http_load_generator.py`: add `scheduler` and `logger` parameters to `run_http_load_test(num_users, label, scheduler, logger)`; inside `simulate_http_user()`, call `logger.log_sent(user_id, query)` before dispatching; replace the direct `httpx.post()` call with `scheduler.handle_request(user_id, query)` which returns the response dict; call `logger.log_response(data["worker_id"], user_id, query, data["result"], round(data["latency"]*1000))` after receiving the response; handle TIMEOUT and ERROR statuses in the log call
- [x] T021 [US2] Add performance gate to `client_nginx_only.py`: after `run_http_load_test()` returns its summary dict, read `PERF_TARGET_SECONDS = int(os.getenv("PERF_TARGET_SECONDS", 1800))`; if `num_users >= 1000`: compare `summary["total_time"]` against threshold; build line `[PERF] 1000-request target: PASS/FAIL (total={total}s, limit={limit}s, throughput={tput} req/s, avg_latency={lat}s)`; print to console and append to the results file via `logger`

**Checkpoint**: `client_nginx_only.py` runs, all imports succeed, requests flow through scheduler → NGINX, `logs/results_*.txt` is populated after run, performance gate prints PASS or FAIL.

---

## Phase 5: User Story 3 – Failure Simulation & Recovery (Priority: P2)

**Goal**: An operator can trigger failure on any individual worker, observe the heartbeat alert, and revive it, all via HTTP — without stopping any process.

**Prerequisite**: US1 (worker endpoints) and US2 (client + heartbeat monitor) must be complete.

**Independent Test**: With 4 workers and client running, from a separate terminal: `curl -X POST http://<WORKER_2_IP>:8002/simulate_failure` → heartbeat logs ALERT within 2s. Send 5 more client requests → they succeed via other workers. Then `curl -X POST http://<WORKER_2_IP>:8002/revive` → heartbeat logs ONLINE. Check `/stats` on Worker 2 to confirm `total_requests` is preserved (not zeroed).

- [x] T022 [US3] In `master/client_support.py`, confirm `HTTPHeartbeatMonitor._run()` handles a worker that starts alive, goes dead, then comes back: verify the `_last_status` dict correctly transitions `None → True → False → True` and logs ALERT/ONLINE only on transitions (not repeatedly); add an explicit `None` initial state check so the first poll never logs a false ALERT even if the worker was never seen before
- [x] T023 [P] [US3] Update `quickstart.md` "Simulate Failure and Recovery" section with the exact curl commands referencing the three endpoints (`/simulate_failure`, `/revive`, `/reset`) and a table of the 5 test scenarios from `plan.md`; include the expected heartbeat log output for each

**Checkpoint**: Failure → ALERT logged within heartbeat interval. Revive → ONLINE logged. Stats preserved across revive. Results file contains entries from surviving workers only during failure window.

---

## Phase 6: User Story 4 – Review Request-Response Log File (Priority: P2)

**Goal**: Every run produces a human-readable `logs/results_YYYYMMDD_HHMMSS.txt` file with one structured entry per request (including failed/timed-out ones).

**Prerequisite**: US2 (ResultsLogger and client rewrite) must be complete.

**Independent Test**: Run client with `NUM_USERS=10`, open the results file, verify exactly 10 entries exist, each with all 5 fields, and that the worker IDs vary across entries (showing load distribution).

- [x] T024 [US4] In `master/client_support.py` `ResultsLogger.log_response()`, handle failure statuses explicitly: if `result` is `"TIMEOUT"`, write `RESPONDS FROM: Worker -1 | Request #<id> | Question: <query> | Response: TIMEOUT | Latency: -1 ms`; if `result` is `"ERROR"`, write the same pattern with `Response: ERROR`; ensure these failure entries are appended to the file just like success entries
- [x] T025 [P] [US4] In `master/client_support.py` `ResultsLogger.__init__()`, add a header line at the top of the results file: `# Run started: <timestamp> | NGINX: <url> | Workers: <count> | Users: <num_users>`; this makes each file self-describing for submission; the header fields must be passed in as constructor params (`nginx_url`, `num_workers`, `num_users`)

**Checkpoint**: Results file has header, all 10 test entries, failure entries use `-1` worker and latency, file is self-describing.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup that applies across all stories.

- [x] T026 Update `CLAUDE.md`: remove all references to deleted files (`main.py`, `main_nginx.py`, `SCHEDULER_USAGE_EXAMPLE.py`, in-process mode sections); update the "Running the System" section to show only the two remaining entry points (`workers/worker_server.py` and `client_nginx_only.py`); add a "Multi-Laptop Setup" section pointing to `specs/001-distributed-llm-cleanup/quickstart.md`; update the Request Flow diagram to reflect the HTTP-only flow
- [x] T027 [P] Verify `master/__init__.py` exports the five classes from `client_support.py` for clean imports: add `from master.client_support import ClientScheduler, HTTPHeartbeatMonitor, HTTPPerformanceMonitor, QueueMonitor, ResultsLogger` to `master/__init__.py`
- [x] T028 [P] Final import check: run `PYTHONPATH=. python -c "from master.client_support import ClientScheduler, HTTPHeartbeatMonitor, HTTPPerformanceMonitor, QueueMonitor, ResultsLogger; print('OK')"` and `PYTHONPATH=. python -c "from client.load_generator import SAMPLE_QUERIES; print(len(SAMPLE_QUERIES))"` to confirm no broken imports remain

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS Phase 4
- **Phase 3 (US1)**: Depends on Phase 1 only — can run in parallel with Phase 2
- **Phase 4 (US2)**: Depends on Phase 2 (needs `master/client_support.py`) and Phase 1
- **Phase 5 (US3)**: Depends on Phase 3 (worker endpoints) and Phase 4 (client + heartbeat)
- **Phase 6 (US4)**: Depends on Phase 4 (ResultsLogger in client)
- **Phase 7 (Polish)**: Depends on all prior phases

### User Story Dependencies

| Story | Depends on | Can parallelize with |
|-------|-----------|----------------------|
| US1 (Phase 3) | Phase 1 cleanup | Phase 2 (foundational) |
| US2 (Phase 4) | Phase 1 + Phase 2 | Phase 3 if done |
| US3 (Phase 5) | US1 + US2 | US4 |
| US4 (Phase 6) | US2 | US3 |

### Within Each Phase

- All tasks marked `[P]` within a phase have no file-level conflicts and can run in parallel
- T010 (LLM_MODE bootstrap) must precede T011–T015 (other worker_server changes)
- T017 (trim load_generator) must precede T020 (update http_load_generator which imports it)
- T018 (rewrite client_nginx_only) must precede T019 and T021

---

## Parallel Execution Examples

### Phase 2 (Foundational) — run in parallel after T001–T004:
```
Task T005: ResultsLogger class in master/client_support.py
Task T006: ClientScheduler class in master/client_support.py
Task T007: HTTPHeartbeatMonitor class in master/client_support.py
Task T008: HTTPPerformanceMonitor class in master/client_support.py
Task T009: QueueMonitor class in master/client_support.py
```

### Phase 3 (US1) — run in parallel with Phase 2:
```
Task T011: WORKER_ID env var + startup banner in workers/worker_server.py
Task T014: POST /revive endpoint in workers/worker_server.py
Task T015: llm_mode in /stats response in workers/worker_server.py
Task T016: Fix nginx/nginx.conf
```
(T010 must complete before T011–T015 since it modifies module-level env setup)

---

## Implementation Strategy

### MVP First (US1 only — one working worker)

1. Phase 1: Cleanup
2. Phase 3: Enhance `worker_server.py` only
3. **STOP and VALIDATE**: Single worker accepts requests in stub mode, logs `[RECV]`/`[RESP]`, responds to `/simulate_failure` and `/revive`
4. Demo one-machine version

### Full Multi-Laptop Demo

1. Phase 1 → Phase 2 → Phase 3 → Phase 4
2. Deploy to 5 laptops using `quickstart.md`
3. **STOP and VALIDATE**: All 4 workers respond, client sends 20 requests, results file populated
4. Add Phase 5 (failure demo) → run failure/revive scenario
5. Add Phase 6 (log review) → verify log file format

---

## Notes

- No tests were requested — all phases are implementation-only
- `[P]` tasks touch different files and have no shared state dependencies at write time
- Commit after each phase checkpoint, not after each individual task
- The `logs/` directory must be created automatically by `ResultsLogger.__init__()` — do not rely on it existing
- Operator must manually edit `nginx/nginx.conf` with real IPs before each multi-laptop deployment (documented in `quickstart.md`)
