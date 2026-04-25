# Fix — Master Node Performance Monitor

## Context

All project phases are complete. One small gap remains:
the project document requires the Master Node to monitor system performance,
but `master/scheduler.py` currently only dispatches requests with no
live monitoring output.

This fix adds `master/monitor.py` and wires it into `main.py` and `main_nginx.py`.

---

## Files to Create / Modify

### 1. `master/monitor.py` (NEW FILE)

```python
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
                status = "ALIVE" if w.alive else "DEAD "
                print(f"[Monitor] Worker {w.id} | "
                      f"Status: {status} | "
                      f"Active: {w.active_requests} req | "
                      f"Total: {w.total_requests} req | "
                      f"Avg Latency: {w.avg_latency:.3f}s")
            print(f"[Monitor] --------------------------------------\n")
            time.sleep(self.interval)

    def stop(self):
        self.running = False
```

---

### 2. `main.py` (MODIFY)

Add this import at the top:
```python
from master.monitor import PerformanceMonitor
```

Inside `main()`, start the monitor before the load test and stop it after:
```python
monitor = PerformanceMonitor(workers, interval=5)
monitor.start()

run_load_test(scheduler, num_users=1000)

monitor.stop()
```

---

### 3. `main_nginx.py` (MODIFY)

Same change as `main.py` — add the import and wire the monitor
around the `run_http_load_test()` call.

```python
from master.monitor import PerformanceMonitor

monitor = PerformanceMonitor(workers, interval=5)
monitor.start()

run_http_load_test(num_users=200, label="nginx_round_robin")

monitor.stop()
```

---

## Acceptance Criteria

- [ ] `python main.py` prints a performance table every 5 seconds during the run
- [ ] Each worker shows correct Status, Active requests, Total requests, Avg Latency
- [ ] DEAD status appears correctly when a worker is killed during fault tolerance demo
- [ ] Monitor stops cleanly after load test finishes with no hanging threads

---

## Notes for Claude Code

- `total_requests` must exist on `GPUWorker` — if it does not exist yet,
  add it to `workers/gpu_worker.py` as `self.total_requests = 0`
  and increment it by 1 inside `process()` after each request completes
- `daemon=True` on the monitor thread is mandatory — without it the
  program will hang after the load test waiting for the monitor to stop
- Do not change any other files
- Python version is 3.9+
