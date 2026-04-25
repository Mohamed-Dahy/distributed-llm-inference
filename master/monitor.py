import threading
import time


class PerformanceMonitor:
    def __init__(self, workers, interval=5):
        self.workers = workers
        self.interval = interval
        self.running = True
        self._gpu_samples = {w.id: [] for w in workers}

    def start(self):
        t = threading.Thread(target=self._report, daemon=True)
        t.start()

    def _sample(self):
        for w in self.workers:
            self._gpu_samples[w.id].append(w.gpu_utilization)

    def _report(self):
        while self.running:
            self._sample()
            print(f"\n[Monitor] -------- System Performance --------")
            for w in self.workers:
                status = "ALIVE" if w.is_alive else "DEAD "
                print(
                    f"[Monitor] Worker {w.id} | "
                    f"Status: {status} | "
                    f"Active: {w.active_requests} req | "
                    f"Total: {w.total_requests} req | "
                    f"Avg Latency: {w.avg_latency:.3f}s | "
                    f"GPU: {w.gpu_utilization}%"
                )
            print(f"[Monitor] --------------------------------------\n")
            time.sleep(self.interval)

    def stop(self):
        self.running = False
        self._sample()  # final snapshot when run ends

    def get_worker_stats(self):
        stats = []
        for w in self.workers:
            samples = self._gpu_samples[w.id]
            avg_util = round(sum(samples) / len(samples), 1) if samples else 0.0
            peak_util = max(samples) if samples else 0.0
            stats.append({
                "id": w.id,
                "status": "ALIVE" if w.is_alive else "DEAD",
                "total_requests": w.total_requests,
                "failed_requests": w.failed_requests,
                "avg_latency": round(w.avg_latency, 3),
                "avg_gpu_util": avg_util,
                "peak_gpu_util": peak_util,
            })
        return stats
