import time
import threading
from llm.inference import run_llm
from rag.retriever import retrieve_context

class GPUWorker:
    def __init__(self, id):
        self.id = id
        self.alive = True
        self.active_requests = 0
        self.avg_latency = 0.2
        self._lock = threading.Lock()

    def process(self, request):
        with self._lock:
            self.active_requests += 1

        start = time.time()
        print(f"[Worker {self.id}] Processing request {request.id}")
        context = retrieve_context(request.query)
        result = run_llm(request.query, context)
        latency = time.time() - start

        with self._lock:
            self.active_requests -= 1
            self.avg_latency = (self.avg_latency + latency) / 2

        return {
            "id": request.id,
            "result": result,
            "latency": latency
        }