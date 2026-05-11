# Quickstart: Multi-Laptop Distributed LLM Inference

## Prerequisites

- All 5 laptops on the same LAN.
- Python 3.9+ installed on all laptops.
- NGINX installed on the **client laptop**.
- Ollama installed and running on each **worker laptop** (for `ollama` mode only).
- Dependencies installed on all laptops: `pip install -r requirements.txt`

---

## Step 1 – Configure NGINX (client laptop only)

Edit `nginx/nginx.conf` and replace the placeholder IPs with the real IPs of your 4 worker laptops:

```nginx
upstream gpu_workers {
    least_conn;
    server <WORKER_1_IP>:8001;
    server <WORKER_2_IP>:8002;
    server <WORKER_3_IP>:8003;
    server <WORKER_4_IP>:8004;
}
```

Start NGINX:
```bash
# macOS (Homebrew):
nginx -c $(pwd)/nginx/nginx.conf

# Linux:
sudo nginx -c $(pwd)/nginx/nginx.conf
```

---

## Step 2 – Start Workers (each worker laptop)

Copy the project to each worker laptop. Then on each:

**Stub mode** (no Ollama needed — for testing):
```bash
PYTHONPATH=. LLM_MODE=stub WORKER_ID=1 python workers/worker_server.py
```
Replace `WORKER_ID=1` with 2, 3, 4 on each respective laptop.

**Ollama mode** (real LLM):
```bash
# First make sure Ollama is running:
ollama serve &
ollama pull mistral

# Then start the worker:
PYTHONPATH=. LLM_MODE=ollama WORKER_ID=1 python workers/worker_server.py
```

Each worker prints: `[Worker 1] Starting on port 8001 | LLM mode: ollama`

---

## Step 3 – Start the Client (client laptop)

Set environment variables pointing to each worker's IP:

```bash
export WORKER_1=http://<WORKER_1_IP>:8001
export WORKER_2=http://<WORKER_2_IP>:8002
export WORKER_3=http://<WORKER_3_IP>:8003
export WORKER_4=http://<WORKER_4_IP>:8004
export NUM_USERS=20        # number of simulated concurrent users
export NUM_CONSUMERS=4     # consumer threads in client scheduler
export REQUEST_TIMEOUT=60  # seconds before a request times out
```

Run the client:
```bash
PYTHONPATH=. python client_nginx_only.py
```

The client will:
1. Wait for all 4 workers to be healthy.
2. Open a timestamped results file at `logs/results_YYYYMMDD_HHMMSS.txt`.
3. Send `NUM_USERS` requests through the queue → NGINX → workers.
4. Print and save every request sent and response received.
5. Print a summary table when done.

---

## Step 4 – Simulate Failure and Recovery

Use direct IP addresses (not NGINX) so you control exactly which worker is targeted.

**Trigger failure on Worker 2** (marks it dead, stats preserved):
```bash
curl -X POST http://<WORKER_2_IP>:8002/simulate_failure
```
The heartbeat monitor will print: `[Heartbeat] ALERT -- Worker http://<IP>:8002 is DOWN`

**Revive Worker 2** (restores alive state, stats preserved — use for demos):
```bash
curl -X POST http://<WORKER_2_IP>:8002/revive
```
The heartbeat monitor will print: `[Heartbeat] Worker http://<IP>:8002 is back ONLINE`

**Reset Worker 2** (restores alive state + clears stats — use for a fresh run):
```bash
curl -X POST http://<WORKER_2_IP>:8002/reset
```

**Summary of the three failure-related endpoints**:

| Endpoint | Effect | Stats |
|----------|--------|-------|
| `POST /simulate_failure` | Sets `is_alive = False` | Preserved |
| `POST /revive` | Sets `is_alive = True` | Preserved |
| `POST /reset` | Sets `is_alive = True` | Cleared to zero |

---

## Step 5 – Review Results

After the run, open the results file:
```bash
cat logs/results_YYYYMMDD_HHMMSS.txt
```

Each line looks like:
```
RESPONDS FROM: Worker 3 | Request #7 | Question: what is supervised learning... | Response: Supervised learning is... | Latency: 312 ms
```

---

## Test Scenarios for Failure Simulation

| Scenario | Steps | Expected outcome |
|----------|-------|------------------|
| Single worker failure | Start run, fail Worker 2 mid-run | Heartbeat logs ALERT; requests route to Workers 1, 3, 4 |
| Multi-worker failure | Fail Workers 2 and 3 | System continues with Workers 1 and 4 only |
| Total failure | Fail all 4 workers | Client logs ERROR for each pending request; no crash |
| Recovery | Fail Worker 2, revive after 10s | Heartbeat logs ONLINE; Worker 2 resumes receiving requests |
| Timeout test | Set `REQUEST_TIMEOUT=3`, use Ollama | Some requests log as TIMEOUT in results file |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Connection refused` on worker URL | Check worker is running: `curl http://<IP>:<PORT>/health` |
| `502 Bad Gateway` from NGINX | All workers are down — check worker processes |
| Requests all going to one worker | Check NGINX `least_conn` config; restart NGINX |
| Ollama timeout | Increase `REQUEST_TIMEOUT`; check `ollama serve` is running |
| `ModuleNotFoundError` | Run with `PYTHONPATH=.` prefix |
