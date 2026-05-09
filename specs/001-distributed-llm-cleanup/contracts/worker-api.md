# Worker HTTP API Contract

Each worker laptop runs `worker_server.py` and exposes the following endpoints on port `8000 + WORKER_ID`.

## POST /process

Process a single inference request.

**Request body**:
```json
{
  "id": 42,
  "query": "what is supervised learning according to the lecture"
}
```

**Success response** (HTTP 200):
```json
{
  "id": 42,
  "result": "Supervised learning is a type of machine learning...",
  "latency": 0.312,
  "worker_id": 2
}
```

**Error response** (HTTP 500):
```json
{
  "detail": "WorkerDeadException: Worker 2 is dead"
}
```

**Behaviour**:
- Worker logs `[RECV]` immediately on arrival.
- Worker logs `[RESP]` immediately before returning.
- If `is_alive == False`, returns HTTP 500 immediately.

---

## GET /health

Liveness check used by NGINX and the heartbeat monitor.

**Response** (HTTP 200):
```json
{
  "status": "ok",
  "worker_id": 2
}
```

If the process is unreachable, the TCP connection fails — no body is returned.

---

## GET /stats

Current runtime statistics.

**Response** (HTTP 200):
```json
{
  "worker_id": 2,
  "status": "ALIVE",
  "active_requests": 3,
  "total_requests": 150,
  "failed_requests": 2,
  "avg_latency": 0.287,
  "gpu_utilization": 0.6,
  "llm_mode": "ollama"
}
```

---

## POST /simulate_failure

Marks the worker as dead without stopping the process. Used for failure simulation.

**Request body**: none

**Response** (HTTP 200):
```json
{
  "status": "failed",
  "worker_id": 2
}
```

**Effect**: Sets `is_alive = False`. Subsequent `/process` calls return HTTP 500. The process keeps running and listening so `/reset` can be called.

---

## POST /revive

Restores a failed worker to the alive state **without clearing statistics**. Use this during failure simulation demos to show recovery while preserving the accumulated request/latency metrics.

**Request body**: none

**Response** (HTTP 200):
```json
{
  "status": "revived",
  "worker_id": 2
}
```

**Effect**: Sets `is_alive = True` only. All counters (`total_requests`, `failed_requests`, `avg_latency`) are preserved. Logs `[RECOVERY] Worker 2 is back ONLINE`.

---

## POST /reset

Revives a failed worker **and clears all statistics**. Use this to start a fresh run with zeroed counters.

**Request body**: none

**Response** (HTTP 200):
```json
{
  "status": "reset",
  "worker_id": 2
}
```

**Effect**: Sets `is_alive = True`, zeroes all counters and latency accumulators.

---

## NGINX Proxy Notes

NGINX listens on port 8080 and proxies all routes to the upstream pool. All five endpoints above are reachable via NGINX at `http://<client-machine-ip>:8080/<endpoint>`.

`proxy_next_upstream error timeout` means NGINX will retry on connection errors — if a worker is dead, NGINX automatically routes to the next healthy upstream for `/process` requests.
