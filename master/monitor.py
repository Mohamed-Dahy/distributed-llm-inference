import threading
import time


class PerformanceMonitor:
    def __init__(self, workers, interval=5):
        self.workers = workers
        self.interval = interval
        self.running = True

    def start(self):
        t = threading.Thread(target=self._report, daemon=True)
        t.start()

    def _report(self):
        while self.running:
            print(f"\n[Monitor] -------- System Performance --------")
            for w in self.workers:
                status = "ALIVE" if w.is_alive else "DEAD "
                print(
                    f"[Monitor] Worker {w.id} | "
                    f"Status: {status} | "
                    f"Active: {w.active_requests} req | "
                    f"Total: {w.total_requests} req | "
                    f"Avg Latency: {w.avg_latency:.3f}s"
                )
            print(f"[Monitor] --------------------------------------\n")
            time.sleep(self.interval)

    def stop(self):
        self.running = False
