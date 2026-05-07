import threading
import time


class QueueMonitor:
    """Monitors scheduler queue health and displays metrics"""
    
    def __init__(self, scheduler, interval=5):
        self.scheduler = scheduler
        self.interval = interval
        self.running = True
        self._start_time = time.time()
        self.max_queue_size = 0
        self.total_samples = 0

    def start(self):
        t = threading.Thread(target=self._monitor, daemon=True)
        t.start()

    def _monitor(self):
        while self.running:
            time.sleep(self.interval)
            elapsed = time.time() - self._start_time
            
            stats = self.scheduler.get_queue_stats()
            queue_size = stats.get("queue_size", 0)
            
            # Track max queue size
            if queue_size > self.max_queue_size:
                self.max_queue_size = queue_size
            
            self.total_samples += 1
            
            print(
                f"\n[QueueMonitor] @{elapsed:5.1f}s │ "
                f"Queue Size: {queue_size:<4} │ "
                f"Max: {self.max_queue_size:<4} │ "
                f"Consumers: {stats.get('num_consumers', 0)}\n"
            )

    def stop(self):
        self.running = False

    def get_stats(self):
        return {
            "max_queue_size": self.max_queue_size,
            "total_samples": self.total_samples
        }
