# Data Model: Distributed LLM Inference

## Entities

### Worker
Represents one running instance of `worker_server.py` on a laptop.

| Field            | Type    | Description                                           |
|------------------|---------|-------------------------------------------------------|
| id               | int     | Unique identifier (1–4); assigned at startup          |
| port             | int     | HTTP port = 8000 + id (e.g., Worker 1 → port 8001)   |
| llm_mode         | enum    | `stub` or `ollama`                                    |
| is_alive         | bool    | True when worker is healthy; False after failure      |
| active_requests  | int     | Number of requests currently being processed          |
| total_requests   | int     | Cumulative count of successfully completed requests   |
| failed_requests  | int     | Cumulative count of requests that raised an exception |
| total_latency    | float   | Cumulative processing time in seconds                 |
| avg_latency      | float   | total_latency / total_requests                        |
| max_capacity     | int     | Maximum concurrent requests before rejection (default: 500) |

**State transitions**:
- `is_alive: True → False` via `/simulate_failure` or process termination
- `is_alive: False → True` via `/reset` (HTTP) or process restart

---

### Request
Issued by the client; forwarded through NGINX to a worker.

| Field      | Type   | Description                                        |
|------------|--------|----------------------------------------------------|
| id         | int    | Unique sequential integer assigned by the client   |
| query      | str    | Natural language question text                     |
| enqueued_at| float  | Unix timestamp when placed in the client queue     |

---

### Response
Returned by the worker through NGINX to the client.

| Field          | Type   | Description                                              |
|----------------|--------|----------------------------------------------------------|
| id             | int    | Matches the originating Request.id                       |
| result         | str    | LLM answer text, or one of: `TIMEOUT`, `ERROR`, `FAILED` |
| latency        | float  | Worker-side processing time in seconds                   |
| worker_id      | int    | ID of the worker that processed the request              |
| queue_wait_time| float  | Time spent waiting in the client queue (seconds)         |
| status         | enum   | `SUCCESS`, `TIMEOUT`, `ERROR`                            |

---

### LogEntry (client results file)
One line per response written to `logs/results_YYYYMMDD_HHMMSS.txt`.

| Field       | Format Example                                                    |
|-------------|-------------------------------------------------------------------|
| worker_id   | `RESPONDS FROM: Worker 2`                                         |
| request_num | `Request #42`                                                     |
| question    | `Question: what is supervised learning according to the lecture`  |
| response    | `Response: Supervised learning is...`                             |
| latency     | `Latency: 312 ms`                                                 |

Full line format:
```
RESPONDS FROM: Worker 2 | Request #42 | Question: ... | Response: ... | Latency: 312 ms
```

Failed/timeout entries:
```
RESPONDS FROM: Worker -1 | Request #42 | Question: ... | Response: TIMEOUT | Latency: -1 ms
```

---

### RunSummary
Printed to console at the end of a client run.

| Field              | Type   | Description                                             |
|--------------------|--------|---------------------------------------------------------|
| label              | str    | Run identifier string                                   |
| num_users          | int    | Total requests sent                                     |
| successful         | int    | Responses with status SUCCESS                           |
| failed             | int    | Responses with status TIMEOUT or ERROR                  |
| total_time         | float  | Wall-clock seconds for entire run                       |
| throughput         | float  | successful / total_time (req/s)                         |
| avg_latency        | float  | Mean worker-side latency (seconds)                      |
| min_latency        | float  | Minimum worker-side latency (seconds)                   |
| max_latency        | float  | Maximum worker-side latency (seconds)                   |
| perf_target_secs   | int    | SLA threshold in seconds (default: 1800 for 1000 reqs)  |
| perf_result        | enum   | `PASS` / `FAIL` / `N/A` (N/A when num_users < 1000)    |

---

## Relationships

```
Client (1)
  └── ClientScheduler (1)
        └── Queue (1) ──→ [Request, ...] ──→ Consumer Threads (N)
                                                  │
                                                  ▼
                                             NGINX (1)
                                                  │
                                    ┌─────────────┼─────────────┐
                                    ▼             ▼             ▼
                               Worker(1)      Worker(2)     Worker(3..4)
                                    │
                               GPUWorker.process()
                                    │
                               llm/inference.py (Ollama or Stub)
                                    │
                               rag/retriever.py (ChromaDB context)
```

## Configuration / Environment Variables

### Worker (`worker_server.py`)
| Variable    | Default | Description                              |
|-------------|---------|------------------------------------------|
| LLM_MODE    | `stub`  | `stub` or `ollama`                       |
| WORKER_ID   | —       | Integer worker ID (required)             |
| MAX_CAPACITY| `500`   | Max concurrent requests                  |
| OLLAMA_MODEL| `mistral` | Ollama model name (ollama mode only)   |
| OLLAMA_URL  | `http://localhost:11434/api/generate` | Ollama endpoint |

### Client (`client_nginx_only.py`)
| Variable        | Default                   | Description                            |
|-----------------|---------------------------|----------------------------------------|
| NGINX_URL       | `http://127.0.0.1:8080`   | NGINX upstream URL                     |
| WORKER_1..4         | `http://127.0.0.1:8001..4`| Direct worker URLs for health checks   |
| NUM_USERS           | `20`                      | Number of simulated concurrent users   |
| NUM_CONSUMERS       | `4`                       | Consumer threads in client scheduler   |
| REQUEST_TIMEOUT     | `60`                      | Seconds before a queued request times out |
| PERF_TARGET_SECONDS | `1800`                    | Max wall-clock seconds for 1000-request SLA validation |
