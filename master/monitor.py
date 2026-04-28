import threading
import time


class PerformanceMonitor:
    def __init__(self, workers, interval=5):
        self.workers = workers
        self.interval = interval
        self.running = True
        self._start_time = time.time()
        self._gpu_samples = {w.id: [] for w in workers}

    def start(self):
        self._start_time = time.time()
        t = threading.Thread(target=self._report, daemon=True)
        t.start()

    def _sample(self):
        for w in self.workers:
            self._gpu_samples[w.id].append(w.gpu_utilization)

    def _report(self):
        while self.running:
            self._sample()
            elapsed = time.time() - self._start_time
            lines = [
                f"\n[Monitor] ──── System Performance  @{elapsed:5.1f}s ────",
                f"[Monitor]  {'W':<4} {'Status':<6} {'Active':>6} {'Total':>6} {'Failed':>6} {'Latency':>8} {'GPU':>6}",
                f"[Monitor]  {'─'*50}",
            ]
            for w in self.workers:
                status = "ALIVE" if w.is_alive else "DEAD "
                lines.append(
                    f"[Monitor]  {w.id:<4} {status:<6} "
                    f"{w.active_requests:>6} {w.total_requests:>6} {w.failed_requests:>6} "
                    f"{w.avg_latency:>7.3f}s {w.gpu_utilization:>5.1f}%"
                )
            lines.append(f"[Monitor] {'─'*52}")
            print('\n'.join(lines))
            time.sleep(self.interval)

    def stop(self):
        self.running = False
        self._sample()  # final snapshot when run ends

    def get_worker_stats(self):
        stats = []
        for w in self.workers:
            samples = self._gpu_samples[w.id]
            avg_util = round(sum(samples) / len(samples), 1) if samples else 0.0
            peak_util = round(max(samples), 1) if samples else 0.0
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
