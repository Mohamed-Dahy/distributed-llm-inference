import sys
import os

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
worker_id = int(sys.argv[1])
max_capacity = int(os.environ.get("MAX_CAPACITY", 500))
worker = GPUWorker(worker_id, max_capacity=max_capacity)


@app.post("/process", response_model=QueryResponse)
def process(body: QueryRequest):
    request = Request(id=body.id, query=body.query)
    try:
        result = worker.process(request)
        return QueryResponse(
            id=result["id"],
            result=result["result"],
            latency=result["latency"],
            worker_id=worker_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok", "worker_id": worker_id}


@app.get("/stats")
def stats():
    return {
        "worker_id": worker_id,
        "status": "ALIVE" if worker.is_alive else "DEAD",
        "active_requests": worker.active_requests,
        "total_requests": worker.total_requests,
        "avg_latency": round(worker.avg_latency, 3),
        "gpu_utilization": worker.gpu_utilization,
    }


if __name__ == "__main__":
    port = 8000 + worker_id
    print(f"[Worker {worker_id}] Starting on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
