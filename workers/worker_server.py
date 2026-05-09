import sys
import os
from datetime import datetime

# T010: Bootstrap LLM_MODE before any project imports that read USE_REAL_LLM
LLM_MODE = os.environ.get("LLM_MODE", "stub").lower()
if LLM_MODE == "ollama":
    os.environ["USE_REAL_LLM"] = "true"
else:
    os.environ["USE_REAL_LLM"] = "false"

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from workers.gpu_worker import GPUWorker
from common.models import Request


class QueryRequest(BaseModel):
    id: int
    query: str


class QueryResponse(BaseModel):
    id: int
    result: str
    latency: float
    worker_id: int


app = FastAPI()

# T011: Accept WORKER_ID from env var, fall back to sys.argv[1]
_env_worker_id = int(os.environ.get("WORKER_ID", 0))
if _env_worker_id:
    worker_id = _env_worker_id
else:
    if len(sys.argv) < 2:
        print("Usage: WORKER_ID=<n> python workers/worker_server.py  OR  python workers/worker_server.py <id>")
        sys.exit(1)
    worker_id = int(sys.argv[1])

max_capacity = int(os.environ.get("MAX_CAPACITY", 500))
worker = GPUWorker(worker_id, max_capacity=max_capacity)


@app.post("/process", response_model=QueryResponse)
def process(body: QueryRequest):
    # T012: Log incoming request immediately
    print(f"[RECV] {datetime.now().isoformat()} | Worker {worker_id} | Request #{body.id} | Q: {body.query}")

    request = Request(id=body.id, query=body.query)
    try:
        result = worker.process(request)

        # T013: Log outgoing response before returning
        latency_ms = round(result["latency"] * 1000)
        preview = result["result"][:120]
        print(f"[RESP] {datetime.now().isoformat()} | Worker {worker_id} | Request #{result['id']} | Latency: {latency_ms}ms | R: {preview}")

        return QueryResponse(
            id=result["id"],
            result=result["result"],
            latency=result["latency"],
            worker_id=worker_id,
        )
    except Exception as e:
        print(f"[RESP] {datetime.now().isoformat()} | Worker {worker_id} | Request #{body.id} | ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok", "worker_id": worker_id}


@app.get("/stats")
async def stats():
    return {
        "worker_id": worker_id,
        "status": "ALIVE" if worker.is_alive else "DEAD",
        "active_requests": worker.active_requests,
        "total_requests": worker.total_requests,
        "failed_requests": worker.failed_requests,
        "avg_latency": round(worker.avg_latency, 3),
        "gpu_utilization": worker.gpu_utilization,
        "llm_mode": LLM_MODE,  # T015
    }


@app.post("/simulate_failure")
async def simulate_failure():
    worker.simulate_failure()
    return {"status": "failed", "worker_id": worker_id}


@app.post("/revive")
async def revive():
    # T014: Restore is_alive without clearing stats
    with worker._lock:
        worker.is_alive = True
    print(f"[RECOVERY] Worker {worker_id} is back ONLINE")
    return {"status": "revived", "worker_id": worker_id}


@app.post("/reset")
async def reset():
    with worker._lock:
        worker.is_alive = True
        worker.active_requests = 0
        worker.total_requests = 0
        worker.failed_requests = 0
        worker.total_latency = 0.0
        worker.avg_latency = 0.0
    return {"status": "reset", "worker_id": worker_id}


if __name__ == "__main__":
    port = 8000 + worker_id
    # T011: Print startup banner
    print(f"[Worker {worker_id}] Starting on port {port} | LLM mode: {LLM_MODE}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
