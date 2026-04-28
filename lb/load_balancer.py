import threading
from common.models import WorkerDeadException, WorkerOverloadedException

class LoadBalancer:
    def __init__(self, workers, strategy='round_robin'):
        self.workers = workers
        self.strategy = strategy
        self.index = 0
        self.lock = threading.Lock()

    def get_alive_workers(self):
        active = [w for w in self.workers if w.is_alive]
        if not active:
            raise Exception("ALL WORKERS ARE DOWN")
        return active

    def _round_robin(self):
        active = self.get_alive_workers()
        worker = active[self.index % len(active)]
        self.index += 1
        return worker

    def _least_connections(self):
        return min(self.get_alive_workers(), key=lambda w: w.active_requests)

    def _load_aware(self):
        def score(w):
            if w.avg_latency == 0.0:
                return w.active_requests
            return w.active_requests * w.avg_latency
        return min(self.get_alive_workers(), key=score)

    def get_next_worker(self):
        with self.lock:
            if self.strategy == 'round_robin':
                return self._round_robin()
            elif self.strategy == 'least_connections':
                return self._least_connections()
            elif self.strategy == 'load_aware':
                return self._load_aware()
            else:
                raise Exception(f"Unknown strategy: {self.strategy}")

    def dispatch(self, request, max_retries=3):
        last_reason = None
        for attempt in range(1, max_retries + 1):
            try:
                worker = self.get_next_worker()
                return worker.process(request)
            except WorkerDeadException as e:
                last_reason = f"Worker {e.worker_id} dead"
            except WorkerOverloadedException as e:
                last_reason = f"Worker {e.worker_id} overloaded"
        print(f"[LB] Request {request.id} FAILED after {max_retries} retries ({last_reason})")
        return {"id": request.id, "result": "FAILED", "latency": -1}

    def remove_worker(self, worker_id):
        for worker in self.workers:
            if worker.id == worker_id:
                worker.is_alive = False
                print(f"[LB] Worker {worker_id} removed from pool")
                return
