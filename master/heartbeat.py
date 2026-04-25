import threading
import time


class HeartbeatMonitor:
    def __init__(self, workers, interval=2):
        self.workers = workers
        self.interval = interval
        self.running = True
        self._last_status = {w.id: w.is_alive for w in workers}

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        while self.running:
            time.sleep(self.interval)
            for w in self.workers:
                current = w.is_alive
                previous = self._last_status[w.id]
                if previous and not current:
                    print(f"[Heartbeat] ALERT -- Worker {w.id} is DOWN")
                elif not previous and current:
                    print(f"[Heartbeat] Worker {w.id} is back ONLINE")
                self._last_status[w.id] = current

    def stop(self):
        self.running = False
