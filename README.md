# distributed-llm-inference

A distributed system for handling concurrent LLM inference requests with load balancing, RAG integration, and fault tolerance — built for CSE354: Distributed Computing at Ain Shams University.

---

## Setup

1. **Python 3.9+** — verify with `python3 --version`

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install NGINX** (required for load balancing):
   - macOS: `brew install nginx`
   - Ubuntu/Debian: `sudo apt install nginx`

4. **Install Ollama** (for real LLM mode only):
   - Download from [ollama.com](https://ollama.com) and install
   - Pull the model:
     ```bash
     ollama pull mistral
     ```

---

## Run

### Step 1 — Configure NGINX

Edit `nginx/nginx.conf` and replace the placeholder IPs with the real IP addresses of your worker laptops:

```nginx
server WORKER_1_IP:8001;
server WORKER_2_IP:8002;
server WORKER_3_IP:8003;
server WORKER_4_IP:8004;
```

Start NGINX on the client laptop:
```bash
nginx -c "$(pwd)/nginx/nginx.conf"
```

Stop NGINX when done:
```bash
nginx -s stop
```

---

### Step 2 — Start Workers (one per laptop)

Each worker laptop runs one instance. Set `WORKER_ID` to match the worker's number (1–4).

**Stub mode** — no Ollama needed, uses a simulated 0.2s delay:
```bash
PYTHONPATH=. LLM_MODE=stub WORKER_ID=2 python workers/worker_server.py
```

**Ollama mode** — real LLM inference with Mistral:
```bash
ollama serve &
ollama pull mistral
PYTHONPATH=. LLM_MODE=ollama WORKER_ID=2 python workers/worker_server.py
```

Workers listen on port `8000 + WORKER_ID` (e.g., Worker 2 → port 8002).

If Ollama is unavailable mid-run, the system automatically falls back to stub mode per request.

---

### Step 3 — Run the Client (on the client laptop)

```bash
export WORKER_1=http://<IP1>:8001
export WORKER_2=http://<IP2>:8002
export WORKER_3=http://<IP3>:8003
export WORKER_4=http://<IP4>:8004
export NUM_USERS=20
PYTHONPATH=. python client_nginx_only.py
```

Results are saved to `logs/results_YYYYMMDD_HHMMSS.txt`.

---

## Failure Simulation

```bash
# Kill a worker (stats preserved):
curl -X POST http://<WORKER_IP>:<PORT>/simulate_failure

# Revive a worker (stats preserved):
curl -X POST http://<WORKER_IP>:<PORT>/revive

# Reset a worker (revive + clear stats):
curl -X POST http://<WORKER_IP>:<PORT>/reset
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `WORKER_ID` | — | Worker number (1–4), required |
| `LLM_MODE` | `stub` | `stub` or `ollama` |
| `NGINX_URL` | `http://127.0.0.1:8080` | NGINX address (client) |
| `WORKER_1..4` | `http://127.0.0.1:8001..4` | Direct worker URLs (client) |
| `NUM_USERS` | `1000` | Number of concurrent simulated users |
| `NUM_CONSUMERS` | `4` | Scheduler consumer threads (client) |
| `REQUEST_TIMEOUT` | `1800` | Per-request timeout in seconds |
| `PERF_TARGET_SECONDS` | `1800` | SLA threshold for 1000-request runs |
| `OLLAMA_MODEL` | `mistral` | Ollama model name |
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | Ollama endpoint |

---

## Request Flow

```
client threads (NUM_USERS × threading.Thread)
    → ClientScheduler.handle_request()       [master/client_support.py]
        → enqueues {req_id, query, response_queue}
        → blocks on response_queue.get(timeout=REQUEST_TIMEOUT)
    ↓ (consumed by NUM_CONSUMERS persistent _consumer_loop threads)
    → httpx.post(NGINX_URL/process)          [NGINX routes via least_conn]
        → Worker laptop (workers/worker_server.py)
            → GPUWorker.process()            [workers/gpu_worker.py]
                → retrieve_context(query)    [rag/retriever.py — ChromaDB]
                → run_llm(query, context)    [llm/inference.py — Ollama or stub]
            → logs [RECV] on arrival, [RESP] on return
    → response dict → response_queue.put()
    → ResultsLogger writes to logs/results_*.txt
```

---

## Folder Structure

```
distributed-llm-inference/
├── client/
│   ├── load_generator.py        # sample queries for load testing
│   └── http_load_generator.py   # spawns N concurrent threads, collects latency stats
├── master/
│   └── client_support.py        # ResultsLogger, ClientScheduler, HeartbeatMonitor,
│                                #   PerformanceMonitor, QueueMonitor
├── workers/
│   ├── gpu_worker.py            # RAG → LLM pipeline per request, tracks alive/latency state
│   └── worker_server.py         # FastAPI server exposing /process, /health, /stats, etc.
├── lb/
│   └── load_balancer.py         # routing strategies (used in standalone/non-NGINX mode)
├── rag/
│   ├── retriever.py             # ChromaDB vector search over ingested PDFs
│   ├── ingest.py                # PDF → text chunks → ChromaDB
│   └── Data/                    # place PDF knowledge base files here
├── llm/
│   └── inference.py             # stub (default) or Ollama real inference
├── common/
│   └── models.py                # Request dataclass + WorkerDeadException / WorkerOverloadedException
├── nginx/
│   └── nginx.conf               # NGINX upstream config (least_conn, 4 workers)
├── client_nginx_only.py         # main entry point for multi-laptop mode
├── requirements.txt
└── logs/                        # results_*.txt and heartbeat_*.txt written here at runtime
```

---

## Course

**CSE354: Distributed Computing** — 2nd Semester 2025/2026  
Faculty of Engineering, Ain Shams University