import time
import threading
from llm.inference import run_llm
from rag.retriever import retrieve_context
from common.models import WorkerDeadException, WorkerOverloadedException


class GPUWorker:
    def __init__(self, id, max_capacity=10):
        self.id = id
        self.max_capacity = max_capacity

        # Worker state
        self.is_alive = True

        # Metrics
        self.active_requests = 0
        self.total_requests = 0
        self.failed_requests = 0
        self.total_latency = 0.0
        self.avg_latency = 0.0

        # Thread safety
        self._lock = threading.Lock()

    @property
    def gpu_utilization(self):
        with self._lock:
            util = (self.active_requests / self.max_capacity) * 100

        return round(min(max(util, 0.0), 100.0), 1)

    def process(self, request):
        start_time = time.time()

        # Reserve slot safely
        with self._lock:
            if not self.is_alive:
                raise WorkerDeadException(self.id)

            if self.active_requests >= self.max_capacity:
                raise WorkerOverloadedException(self.id)

            self.active_requests += 1

        try:
            print(f"[Worker {self.id}] Processing request {request.id}")

            # Double check worker before expensive task
            with self._lock:
                if not self.is_alive:
                    raise WorkerDeadException(self.id)

            context = retrieve_context(request.query)
            result = run_llm(request.query, context)

            latency = time.time() - start_time

            with self._lock:
                if not self.is_alive:
                    raise WorkerDeadException(self.id)

                self.total_requests += 1
                self.total_latency += latency
                self.avg_latency = (
                    self.total_latency / self.total_requests
                )

            return {
                "id": request.id,
                "result": result,
                "latency": round(latency, 3),
                "worker_id": self.id
            }

        except Exception:
            with self._lock:
                self.failed_requests += 1
            raise

        finally:
            with self._lock:
                self.active_requests = max(
                    0,
                    self.active_requests - 1
                )

    def simulate_failure(self):
        with self._lock:
            self.is_alive = False

        print(f"[FAILURE] Worker {self.id} has gone down!")

    def revive(self):
        with self._lock:
            self.is_alive = True

        print(f"[RECOVERY] Worker {self.id} is back ONLINE")

    def get_stats(self):
        with self._lock:
            util = round(min(max((self.active_requests / self.max_capacity) * 100, 0.0), 100.0), 1)
            return {
                "worker_id": self.id,
                "is_alive": self.is_alive,
                "active_requests": self.active_requests,
                "total_requests": self.total_requests,
                "failed_requests": self.failed_requests,
                "avg_latency": round(self.avg_latency, 3),
                "gpu_utilization": util,
                "max_capacity": self.max_capacity
            }