"""
Client-only for multi-laptop NGINX setup.
Does NOT spawn workers — assumes they're running on separate machines/laptops.

Run this AFTER workers are already running:
  PYTHONPATH=. python client_nginx_only.py
"""

import time
import os
import threading
from dotenv import load_dotenv
load_dotenv()

import httpx
from client.http_load_generator import run_http_load_test

NUM_USERS = 35
WORKER_PORTS = [8001, 8002]
NGINX_URL = os.getenv("NGINX_URL", "http://127.0.0.1:8080")

USE_REAL_LLM = os.getenv("USE_REAL_LLM", "false").lower() == "true"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


class HTTPHeartbeatMonitor:
    def __init__(self, worker_urls, interval=2):
        self.worker_urls = worker_urls
        self.interval = interval
        self.running = True
        self._last_status = {url: False for url in worker_urls}

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        while self.running:
            time.sleep(self.interval)
            for url in self.worker_urls:
                try:
                    r = httpx.get(f"{url}/health", timeout=1.0)
                    current = r.status_code == 200
                except Exception:
                    current = False
                previous = self._last_status[url]
                if previous and not current:
                    print(f"[Heartbeat] ALERT -- Worker {url} is DOWN")
                elif not previous and current:
                    print(f"[Heartbeat] Worker {url} is back ONLINE")
                self._last_status[url] = current

    def stop(self):
        self.running = False


class HTTPPerformanceMonitor:
    def __init__(self, worker_urls, interval=5):
        self.worker_urls = worker_urls
        self.interval = interval
        self.running = True
        self._start_time = time.time()

    def start(self):
        self._start_time = time.time()
        t = threading.Thread(target=self._report, daemon=True)
        t.start()

    def _report(self):
        while self.running:
            elapsed = time.time() - self._start_time
            lines = [
                f"\n[Monitor] ──── System Performance  @{elapsed:5.1f}s ────",
                f"[Monitor]  {'Worker':<30} {'Status':<6} {'Active':>6} {'Total':>6} {'Failed':>6} {'Latency':>8} {'GPU':>6}",
                f"[Monitor]  {'-'*80}",
            ]
            for url in self.worker_urls:
                try:
                    r = httpx.get(f"{url}/stats", timeout=1.0)
                    d = r.json()
                    lines.append(
                        f"[Monitor]  {url:<30} {d['status']:<6} "
                        f"{d['active_requests']:>6} {d['total_requests']:>6} {d.get('failed_requests', 0):>6} "
                        f"{d['avg_latency']:>7.3f}s {d['gpu_utilization']:>5.1f}%"
                    )
                except Exception:
                    lines.append(f"[Monitor]  {url:<30} -- unreachable")
            lines.append(f"[Monitor] {'-'*82}")
            print('\n'.join(lines))
            time.sleep(self.interval)

    def stop(self):
        self.running = False


def wait_for_workers(worker_urls, timeout=30):
    deadline = time.time() + timeout
    remaining = set(worker_urls)
    while remaining and time.time() < deadline:
        for url in list(remaining):
            try:
                r = httpx.get(f"{url}/health", timeout=1.0)
                if r.status_code == 200:
                    print(f"[Client] Worker {url} is ready")
                    remaining.discard(url)
            except Exception:
                pass
        if remaining:
            time.sleep(0.5)
    if remaining:
        print(f"[Client] WARNING -- workers {remaining} did not respond in time")
        return False
    time.sleep(1.0)
    return True


def main():
    # Get worker URLs from environment or use defaults
    worker_urls = [
        os.getenv("WORKER_1", "http://127.0.0.1:8001"),
        os.getenv("WORKER_2", "http://127.0.0.1:8002"),
    ]

    print(f"\n{'='*80}")
    print(f"  CLIENT-ONLY MODE (Workers running on separate machines)")
    print(f"  NGINX      : {NGINX_URL}")
    print(f"  WORKERS    : {', '.join(worker_urls)}")
    print(f"  USERS      : {NUM_USERS}")
    if USE_REAL_LLM:
        llm_mode = "Groq API" if GROQ_API_KEY else "Ollama"
        print(f"  LLM MODE   : {llm_mode} (with response display)")
    else:
        print(f"  LLM MODE   : STUB (0.2s sleep)")
    print(f"{'='*80}\n")

    if not wait_for_workers(worker_urls):
        print("[Client] Aborting — not all workers are ready")
        return

    heartbeat = HTTPHeartbeatMonitor(worker_urls, interval=2)
    monitor = HTTPPerformanceMonitor(worker_urls, interval=5)
    heartbeat.start()
    monitor.start()

    run_http_load_test(num_users=NUM_USERS, label="nginx_distributed")

    heartbeat.stop()
    monitor.stop()
    print("\n[Client] Load test completed")


if __name__ == "__main__":
    main()
