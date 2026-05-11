"""
master/client_support.py
Consolidated HTTP-aware support module for the distributed client.
Replaces: scheduler.py, heartbeat.py, monitor.py, queue_monitor.py (all deleted).
"""

import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx


# ---------------------------------------------------------------------------
# ResultsLogger — T005
# ---------------------------------------------------------------------------

class ResultsLogger:
    """
    Writes structured log lines to both stdout and a timestamped results file.
    One file is created per run at logs/results_YYYYMMDD_HHMMSS.txt.
    """

    def __init__(self, log_dir="logs", nginx_url="", num_workers=0, num_users=0, timestamp=""):
        os.makedirs(log_dir, exist_ok=True)
        timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.timestamp = timestamp
        self._path = os.path.join(log_dir, f"results_{timestamp}.txt")
        self._file = open(self._path, "a", buffering=1)
        self._lock = threading.Lock()
        header = (
            f"# Run started: {datetime.now().isoformat()} "
            f"| NGINX: {nginx_url} "
            f"| Workers: {num_workers} "
            f"| Users: {num_users}\n"
        )
        self._write(header)
        print(f"[Logger] Results file: {self._path}")

    def _write(self, line: str):
        with self._lock:
            self._file.write(line)

    def log_sent(self, req_id: int, query: str):
        line = f"[SENT] {datetime.now().isoformat()} | Request #{req_id} | Q: {query}\n"
        print(line, end="")
        self._write(line)

    def log_response(self, worker_id, req_id: int, query: str, result: str, latency_ms):
        worker_label = f"Worker {worker_id}" if worker_id != -1 else "Worker -1"
        line = (
            f"RESPONDS FROM: {worker_label} | Request #{req_id} | "
            f"Question: {query} | Response: {result} | Latency: {latency_ms} ms\n"
        )
        print(line, end="")
        self._write(line)

    def log_raw(self, line: str):
        """Write a raw line to file and stdout (e.g. for performance gate output)."""
        print(line)
        self._write(line + "\n")

    def close(self):
        with self._lock:
            self._file.flush()
            self._file.close()

    @property
    def path(self):
        return self._path


# ---------------------------------------------------------------------------
# ClientScheduler — T006
# ---------------------------------------------------------------------------

class ClientScheduler:
    """
    Queue-based scheduler for HTTP client.
    Consumer threads dequeue requests and POST to NGINX.
    """

    def __init__(self, nginx_url: str, num_consumers: int = 4, request_timeout: int = 60):
        self.nginx_url = nginx_url.rstrip("/")
        self.num_consumers = num_consumers
        self.request_timeout = request_timeout
        self._request_queue = queue.Queue()
        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=num_consumers)
        for _ in range(num_consumers):
            self._executor.submit(self._consumer_loop)
        print(f"[Scheduler] Started with {num_consumers} consumer threads → {self.nginx_url}")

    def handle_request(self, req_id: int, query: str) -> dict:
        response_queue = queue.Queue()
        enqueued_at = time.time()
        self._request_queue.put({
            "req_id": req_id,
            "query": query,
            "response_queue": response_queue,
            "enqueued_at": enqueued_at,
        })
        try:
            response = response_queue.get(timeout=self.request_timeout)
            return response
        except queue.Empty:
            print(f"[Scheduler] Request #{req_id} TIMEOUT after {self.request_timeout}s")
            return {"id": req_id, "result": "TIMEOUT", "latency": -1, "worker_id": -1, "queue_wait_time": -1}

    def _consumer_loop(self):
        while self._running:
            try:
                item = self._request_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            req_id = item["req_id"]
            query = item["query"]
            response_queue = item["response_queue"]
            enqueued_at = item["enqueued_at"]
            wait_time = time.time() - enqueued_at
            try:
                resp = httpx.post(
                    f"{self.nginx_url}/process",
                    json={"id": req_id, "query": query},
                    timeout=float(self.request_timeout),
                )
                resp.raise_for_status()
                data = resp.json()
                data["queue_wait_time"] = round(wait_time, 3)
                response_queue.put(data)
            except Exception as e:
                print(f"[Scheduler] Request #{req_id} ERROR: {e}")
                response_queue.put({
                    "id": req_id,
                    "result": "ERROR",
                    "latency": -1,
                    "worker_id": -1,
                    "queue_wait_time": round(wait_time, 3),
                    "error": str(e),
                })
            finally:
                self._request_queue.task_done()

    def get_queue_stats(self) -> dict:
        return {
            "queue_size": self._request_queue.qsize(),
            "num_consumers": self.num_consumers,
            "request_timeout": self.request_timeout,
        }

    def shutdown(self):
        print("[Scheduler] Shutting down...")
        self._running = False
        self._request_queue.join()
        self._executor.shutdown(wait=True)
        print("[Scheduler] Consumer threads stopped")


# ---------------------------------------------------------------------------
# HTTPHeartbeatMonitor — T007
# ---------------------------------------------------------------------------

class HTTPHeartbeatMonitor:
    """
    Sends a heartbeat to each worker every 3 seconds.
    On first failure: retries immediately.
    After 3 consecutive failures: worker declared DEAD (still polls every 3s).
    When a heartbeat succeeds after DEAD: worker announced ALIVE.
    """

    CONSECUTIVE_FAILURES_THRESHOLD = 3

    def __init__(self, worker_urls: list, interval: int = 3, log_dir: str = "logs", timestamp: str = ""):
        self.worker_urls = worker_urls
        self.interval = interval
        self._running = True
        # Per-worker state: consecutive failures and whether declared dead
        self._failures: dict = {url: 0 for url in worker_urls}
        self._dead: dict = {url: False for url in worker_urls}
        self._initialized: dict = {url: False for url in worker_urls}
        os.makedirs(log_dir, exist_ok=True)
        ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(log_dir, f"heartbeat_{ts}.txt")
        self._file = open(log_path, "a", buffering=1)
        self._lock = threading.Lock()
        header = f"# Heartbeat log started: {datetime.now().isoformat()} | Workers: {worker_urls}\n"
        self._file.write(header)
        print(f"[Heartbeat] Log file: {log_path}")

    def _log(self, line: str):
        print(line)
        with self._lock:
            if not self._file.closed:
                self._file.write(line + "\n")

    def _ping(self, url: str) -> bool:
        try:
            r = httpx.get(f"{url}/health", timeout=1.0)
            return r.status_code == 200
        except Exception:
            return False

    def _check_worker(self, url: str):
        alive = self._ping(url)
        ts = datetime.now().isoformat()

        if not self._initialized[url]:
            self._initialized[url] = True
            status = "ALIVE" if alive else "DOWN"
            self._log(f"[Heartbeat] {ts} | Worker {url} | Initial status: {status}")
            if not alive:
                self._failures[url] = 1
            return

        if alive:
            if self._dead[url]:
                self._dead[url] = False
                self._failures[url] = 0
                self._log(f"[Heartbeat] {ts} | Worker {url} | ALIVE — worker is back online")
            else:
                self._failures[url] = 0
                self._log(f"[Heartbeat] {ts} | Worker {url} | ALIVE")
        else:
            self._failures[url] += 1
            self._log(f"[Heartbeat] {ts} | Worker {url} | MISSED (consecutive failures: {self._failures[url]})")

            # Immediate retry on first failure
            if self._failures[url] == 1:
                time.sleep(0.2)
                alive = self._ping(url)
                ts = datetime.now().isoformat()
                if alive:
                    self._failures[url] = 0
                    self._log(f"[Heartbeat] {ts} | Worker {url} | ALIVE (recovered on immediate retry)")
                else:
                    self._failures[url] += 1
                    self._log(f"[Heartbeat] {ts} | Worker {url} | MISSED on immediate retry (consecutive failures: {self._failures[url]})")

            if self._failures[url] >= self.CONSECUTIVE_FAILURES_THRESHOLD and not self._dead[url]:
                self._dead[url] = True
                self._log(f"[Heartbeat] {ts} | Worker {url} | DEAD — {self.CONSECUTIVE_FAILURES_THRESHOLD} consecutive failures")

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        for url in self.worker_urls:
            self._check_worker(url)
        while self._running:
            time.sleep(self.interval)
            for url in self.worker_urls:
                self._check_worker(url)

    def stop(self):
        self._running = False
        with self._lock:
            self._file.flush()
            self._file.close()


# ---------------------------------------------------------------------------
# HTTPPerformanceMonitor — T008
# ---------------------------------------------------------------------------

class HTTPPerformanceMonitor:
    """
    Polls /stats on each worker URL and prints a performance table.
    """

    def __init__(self, worker_urls: list, interval: int = 5):
        self.worker_urls = worker_urls
        self.interval = interval
        self._running = True
        self._start_time = time.time()

    def start(self):
        self._start_time = time.time()
        t = threading.Thread(target=self._report, daemon=True)
        t.start()

    def _report(self):
        while self._running:
            elapsed = time.time() - self._start_time
            lines = [
                f"\n[Monitor] ──── System Performance  @{elapsed:5.1f}s ────",
                f"[Monitor]  {'Worker':<30} {'Status':<6} {'Active':>6} {'Total':>6} {'Failed':>6} {'Latency':>8} {'GPU':>6}",
                f"[Monitor]  {'-' * 78}",
            ]
            for url in self.worker_urls:
                try:
                    r = httpx.get(f"{url}/stats", timeout=1.0)
                    d = r.json()
                    lines.append(
                        f"[Monitor]  {url:<30} {d['status']:<6} "
                        f"{d['active_requests']:>6} {d['total_requests']:>6} "
                        f"{d.get('failed_requests', 0):>6} "
                        f"{d['avg_latency']:>7.3f}s {d['gpu_utilization']:>5.1f}%"
                    )
                except Exception:
                    lines.append(f"[Monitor]  {url:<30} -- unreachable")
            lines.append(f"[Monitor] {'-' * 80}")
            print("\n".join(lines))
            time.sleep(self.interval)

    def stop(self):
        self._running = False


# ---------------------------------------------------------------------------
# QueueMonitor — T009  (ported directly from deleted master/queue_monitor.py)
# ---------------------------------------------------------------------------

class QueueMonitor:
    """Monitors scheduler queue health and displays metrics."""

    def __init__(self, scheduler, interval: int = 5):
        self.scheduler = scheduler
        self.interval = interval
        self._running = True
        self._start_time = time.time()
        self.max_queue_size = 0
        self.total_samples = 0

    def start(self):
        t = threading.Thread(target=self._monitor, daemon=True)
        t.start()

    def _monitor(self):
        while self._running:
            time.sleep(self.interval)
            elapsed = time.time() - self._start_time
            stats = self.scheduler.get_queue_stats()
            queue_size = stats.get("queue_size", 0)
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
        self._running = False

    def get_stats(self) -> dict:
        return {
            "max_queue_size": self.max_queue_size,
            "total_samples": self.total_samples,
        }
