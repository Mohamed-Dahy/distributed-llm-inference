import threading

class LoadBalancer:
    def __init__(self, workers, strategy='round_robin'):
        self.workers = workers
        self.strategy = strategy
        self.index = 0
        self.lock = threading.Lock()

    def get_next_worker(self):
        with self.lock:
            active = [w for w in self.workers if w.alive]
            if not active:
                raise Exception("No available workers")

            if self.strategy == 'round_robin':
                worker = active[self.index % len(active)]
                self.index += 1
                return worker
            elif self.strategy == 'least_connections':
                return min(active, key=lambda w: w.active_requests)
            elif self.strategy == 'load_aware':
                return min(active, key=lambda w: w.active_requests * w.avg_latency)
            else:
                raise Exception(f"Unknown strategy: {self.strategy}")

    def dispatch(self, request):
        worker = self.get_next_worker()
        return worker.process(request)

    def remove_worker(self, worker_id):
        for worker in self.workers:
            if worker.id == worker_id:
                worker.alive = False
                print(f"[LB] Worker {worker_id} removed from pool")
                return
