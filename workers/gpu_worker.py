import time
import threading
from llm.inference import run_llm
from rag.retriever import retrieve_context
from common.models import WorkerDeadException

class GPUWorker:
    def __init__(self, id):
        self.id = id
        self.is_alive = True
        self.active_requests = 0
        self.avg_latency = 0.2
        self.failed_requests = 0
        self._lock = threading.Lock()

    def process(self, request):
        if not self.is_alive:
            raise WorkerDeadException(self.id)

        with self._lock:
            self.active_requests += 1

        start = time.time()
        try:
            print(f"[Worker {self.id}] Processing request {request.id}")
            context = retrieve_context(request.query)
            result = run_llm(request.query, context)
            latency = time.time() - start

            if not self.is_alive:
                raise WorkerDeadException(self.id)

            with self._lock:
                self.active_requests -= 1
                self.avg_latency = (self.avg_latency + latency) / 2

            return {
                "id": request.id,
                "result": result,
                "latency": latency
            }
        except Exception:
            with self._lock:
                self.active_requests -= 1
                self.failed_requests += 1
            raise

    def simulate_failure(self):
        self.is_alive = False
        print(f"[FAILURE] Worker {self.id} has gone down!")
