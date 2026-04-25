# Phase 2B — NGINX Real Load Balancer Integration Plan

## Context

The project already has a working Python load balancer in `lb/load_balancer.py`
implementing Round Robin, Least Connections, and Load-Aware strategies.

This phase adds NGINX as a real production load balancer running alongside
the existing Python implementation. Workers become FastAPI HTTP servers.
NGINX routes incoming HTTP requests across them using its built-in algorithms.

This demonstrates that the project uses real industry-standard tools —
not just a simulated Python implementation.

The existing Python load balancer is NOT removed. Both run side by side
so the report can compare them directly.

---

## What Changes

```
BEFORE:
1000 threads → Python LoadBalancer → GPUWorker.process()

AFTER:
1000 threads → NGINX (port 80) → FastAPI Worker 1 (port 8001)
                               → FastAPI Worker 2 (port 8002)
                               → FastAPI Worker 3 (port 8003)
                               → FastAPI Worker 4 (port 8004)
```

The Python load balancer remains in `lb/load_balancer.py` for comparison.
A new `nginx/` folder contains the NGINX config and a new
`client/http_load_generator.py` sends real HTTP requests.

---

## Updated Project Structure

```
cse354-project/
├── client/
│   ├── __init__.py
│   ├── load_generator.py          ← unchanged (Python LB demo)
│   └── http_load_generator.py     ← NEW (sends HTTP requests through NGINX)
├── master/
│   ├── __init__.py
│   ├── scheduler.py
│   └── heartbeat.py
├── workers/
│   ├── __init__.py
│   ├── gpu_worker.py              ← unchanged
│   └── worker_server.py           ← NEW (FastAPI HTTP wrapper)
├── lb/
│   ├── __init__.py
│   └── load_balancer.py           ← unchanged
├── nginx/
│   └── nginx.conf                 ← NEW (NGINX configuration)
├── rag/
│   ├── __init__.py
│   ├── retriever.py
│   ├── ingest.py
│   └── docs/
├── llm/
│   ├── __init__.py
│   └── inference.py
├── common/
│   ├── __init__.py
│   └── models.py
├── main.py                        ← unchanged
├── main_nginx.py                  ← NEW (starts workers + runs HTTP test)
└── requirements.txt
```

---

## Step 0 — Install NGINX

**Windows:**
Download NGINX from https://nginx.org/en/download.html
Extract to `C:\nginx`
Add `C:\nginx` to your PATH

Verify:
```bash
nginx -v
```

**Mac:**
```bash
brew install nginx
```

**Linux (Ubuntu):**
```bash
sudo apt install nginx
```

---

## Step 1 — Install Python Dependencies

```bash
pip install fastapi uvicorn httpx
pip freeze > requirements.txt
```

- `fastapi` — turns each GPU worker into an HTTP server
- `uvicorn` — ASGI server that runs FastAPI
- `httpx` — async HTTP client for the load generator

---

## Files to Create

### 1. `nginx/nginx.conf` (NEW FILE)

This is the NGINX configuration file. It defines an upstream block
with 4 worker servers and proxies all incoming requests to them
using Round Robin (NGINX default).

```nginx
worker_processes 1;

events {
    worker_connections 1024;
}

http {

    upstream gpu_workers {
        # NGINX default is Round Robin
        # For Least Connections uncomment the next line:
        # least_conn;

        server 127.0.0.1:8001;
        server 127.0.0.1:8002;
        server 127.0.0.1:8003;
        server 127.0.0.1:8004;

        # Health check — mark worker down after 3 failed attempts
        # NGINX will automatically stop routing to failed workers
    }

    server {
        listen 8080;

        location /process {
            proxy_pass http://gpu_workers;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_connect_timeout 30s;
            proxy_read_timeout 60s;

            # NGINX health checking — remove failed workers automatically
            proxy_next_upstream error timeout invalid_header;
            proxy_next_upstream_tries 2;
        }

        location /health {
            proxy_pass http://gpu_workers;
        }
    }
}
```

NGINX listens on port 8080 and distributes to workers on 8001-8004.
`proxy_next_upstream` means if a worker fails, NGINX automatically
retries on the next worker — this is NGINX's built-in fault tolerance.

---

### 2. `workers/worker_server.py` (NEW FILE)

Wraps `GPUWorker` in a FastAPI HTTP server. Each worker instance
runs on a different port (8001, 8002, 8003, 8004).

**Imports needed:**
- `fastapi` — FastAPI, HTTPException
- `uvicorn`
- `pydantic` — BaseModel
- `sys`, `os`
- `GPUWorker` from `workers.gpu_worker`
- `Request` from `common.models`

**Pydantic models for HTTP request/response:**

```python
from pydantic import BaseModel

class QueryRequest(BaseModel):
    id: int
    query: str

class QueryResponse(BaseModel):
    id: int
    result: str
    latency: float
    worker_id: int
```

**FastAPI app setup:**

```python
app = FastAPI()
worker_id = int(sys.argv[1])  # passed as command line argument
worker = GPUWorker(worker_id)
```

**Routes:**

`POST /process`
- Accept a `QueryRequest` body
- Create a `Request(id=body.id, query=body.query)` dataclass
- Call `worker.process(request)`
- Return a `QueryResponse` with worker_id included

`GET /health`
- Return `{"status": "ok", "worker_id": worker_id}`
- Used by NGINX health checking

**Run with uvicorn:**

```python
if __name__ == "__main__":
    port = 8000 + worker_id
    print(f"[Worker {worker_id}] Starting on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
```

---

### 3. `client/http_load_generator.py` (NEW FILE)

Sends real HTTP requests through NGINX to the workers.
Uses `httpx` with threading (same pattern as existing load generator).

**Imports needed:**
- `threading`
- `time`
- `httpx`
- `SAMPLE_QUERIES` from `client.load_generator`

**`simulate_http_user(user_id, results, lock)` function:**

```python
def simulate_http_user(user_id, results, lock):
    query = SAMPLE_QUERIES[user_id % len(SAMPLE_QUERIES)]
    payload = {"id": user_id, "query": query}

    start = time.time()
    try:
        response = httpx.post(
            "http://127.0.0.1:8080/process",
            json=payload,
            timeout=30.0
        )
        data = response.json()
        latency = time.time() - start

        with lock:
            results.append(latency)

        print(f"[HTTP Client] Response {data['id']} | "
              f"Worker {data['worker_id']} | "
              f"Latency: {latency:.3f}s")

    except Exception as e:
        print(f"[HTTP Client] Request {user_id} FAILED: {e}")
```

**`run_http_load_test(num_users, label)` function:**

Same structure as `run_load_test()` in `load_generator.py`:
- Create results list and lock
- Spawn N threads each running `simulate_http_user()`
- Join all threads
- Calculate and return stats dict with same keys:
  `label`, `num_users`, `total_time`, `throughput`,
  `avg_latency`, `min_latency`, `max_latency`
- Print the stats block after joining

---

### 4. `main_nginx.py` (NEW FILE)

Entry point for the NGINX demo. It starts the 4 worker servers
as subprocesses, waits for them to be ready, runs the load test,
then shuts everything down cleanly.

**Imports needed:**
- `subprocess`
- `time`
- `sys`
- `httpx`
- `run_http_load_test` from `client.http_load_generator`

**`wait_for_workers(ports, timeout=15)` helper:**

Polls each port with `httpx.get(f"http://127.0.0.1:{port}/health")`
every 0.5 seconds until all workers respond or timeout is reached.
Prints `[Main] Worker on port {port} is ready` for each one.

**`main()` function:**

```python
def main():
    # Start 4 worker servers as subprocesses
    processes = []
    for worker_id in range(1, 5):
        p = subprocess.Popen(
            [sys.executable, "workers/worker_server.py", str(worker_id)],
            env={**os.environ, "PYTHONPATH": "."}
        )
        processes.append(p)

    # Wait until all workers are healthy
    ports = [8001, 8002, 8003, 8004]
    wait_for_workers(ports)

    print("\n[Main] All workers ready. Starting NGINX load test...\n")
    print("NOTE: Make sure NGINX is running with: nginx -c nginx/nginx.conf\n")

    # Run HTTP load test through NGINX
    run_http_load_test(num_users=200, label="nginx_round_robin")

    # Shutdown worker processes
    print("\n[Main] Shutting down workers...")
    for p in processes:
        p.terminate()
```

---

## How to Run the NGINX Demo

**Terminal 1 — Start NGINX:**

```bash
# Windows
nginx -c nginx/nginx.conf

# Mac/Linux
nginx -c $(pwd)/nginx/nginx.conf
```

**Terminal 2 — Run the demo:**

```bash
python main_nginx.py
```

**To stop NGINX when done:**

```bash
# Windows
nginx -s stop

# Mac/Linux
nginx -s stop
```

---

## How to Switch NGINX to Least Connections

Open `nginx/nginx.conf` and uncomment `least_conn;` inside the upstream block:

```nginx
upstream gpu_workers {
    least_conn;    ← uncomment this line
    server 127.0.0.1:8001;
    ...
}
```

Then reload NGINX without stopping it:
```bash
nginx -s reload
```

Run the test again. Compare throughput numbers between Round Robin
and Least Connections — same comparison you did in Python, now with
a real production load balancer.

---

## What to Show in Your Report

This integration lets you write:

> "The system was implemented with two load balancing layers:
> a Python-native implementation demonstrating algorithmic behavior,
> and a production NGINX reverse proxy demonstrating real infrastructure
> deployment. NGINX's `proxy_next_upstream` directive provides built-in
> fault tolerance by automatically rerouting requests away from failed
> worker nodes, complementing the application-level heartbeat monitor
> in `master/heartbeat.py`."

That paragraph alone demonstrates both implementation depth and wider reading.

---

## Acceptance Criteria

- [ ] `nginx -v` confirms NGINX is installed
- [ ] `python main_nginx.py` starts 4 FastAPI workers successfully
- [ ] NGINX routes requests — worker IDs in logs show distribution across all 4 workers
- [ ] Changing to `least_conn` in nginx.conf and reloading changes routing behavior
- [ ] Killing one worker mid-run — NGINX automatically stops routing to it
- [ ] Stats block prints correctly after the load test completes

---

## Do Not Change

- `lb/load_balancer.py` — Python LB stays for comparison
- `main.py` — original demo stays working
- `workers/gpu_worker.py` — core logic unchanged
- `rag/retriever.py`
- `llm/inference.py`
- Any `__init__.py` files

---

## Notes for Claude Code

- `main_nginx.py` is a separate entry point — does not replace `main.py`
- Worker servers are started as subprocesses using `sys.executable`
  to ensure they use the same Python/venv as the parent process
- NGINX must be installed and running separately — Claude Code cannot
  install or start NGINX, only create the config file
- `worker_server.py` takes worker_id as `sys.argv[1]` — port is `8000 + worker_id`
  so worker 1 = port 8001, worker 2 = port 8002, etc.
- The `wait_for_workers()` function is critical — without it the load test
  starts before workers are ready and all requests fail
- Use `log_level="warning"` in uvicorn to suppress per-request access logs
  that would flood the terminal
- Python version is 3.9+
- NGINX config file path in the plan uses relative path — adjust instructions
  to use absolute path if needed on Windows