import threading
import random
import time

class FailureSimulator:
    def __init__(self, workers, failure_delay=3.0, num_failures=1):
        self.workers = workers
        self.failure_delay = failure_delay
        self.num_failures = num_failures

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        time.sleep(self.failure_delay)
        alive = [w for w in self.workers if w.is_alive]
        targets = random.sample(alive, min(self.num_failures, len(alive)))
        for w in targets:
            w.simulate_failure()
