"""
client_nginx_only.py
Multi-laptop distributed client.

Workflow:
  1. Wait for all 4 worker laptops to be healthy.
  2. Start heartbeat, performance, and queue monitors.
  3. Send NUM_USERS requests through ClientScheduler → NGINX → workers.
  4. Log every request sent and every response received (console + results file).
  5. Print run summary; if NUM_USERS >= 1000 evaluate the 30-min SLA.

Environment variables:
  NGINX_URL           — default http://127.0.0.1:8080
  WORKER_1..WORKER_4  — direct worker URLs for health checks
  NUM_USERS           — simulated concurrent users (default 20)
  NUM_CONSUMERS       — scheduler consumer threads (default 4)
  REQUEST_TIMEOUT     — seconds before a request times out (default 60)
  PERF_TARGET_SECONDS — SLA threshold for 1000-request run (default 1800)
"""

import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

from master.client_support import (
    ClientScheduler,
    HTTPHeartbeatMonitor,
    HTTPPerformanceMonitor,
    QueueMonitor,
    ResultsLogger,
)
from client.http_load_generator import run_http_load_test

# ── Configuration ────────────────────────────────────────────────────────────
NGINX_URL = os.getenv("NGINX_URL", "http://127.0.0.1:8080")
NUM_USERS = int(os.getenv("NUM_USERS", 20))
NUM_CONSUMERS = int(os.getenv("NUM_CONSUMERS", 4))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 60))
PERF_TARGET_SECONDS = int(os.getenv("PERF_TARGET_SECONDS", 1800))

WORKER_URLS = [
    os.getenv("WORKER_1", "http://127.0.0.1:8001"),
    os.getenv("WORKER_2", "http://127.0.0.1:8002"),
    os.getenv("WORKER_3", "http://127.0.0.1:8003"),
    os.getenv("WORKER_4", "http://127.0.0.1:8004"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def wait_for_workers(worker_urls: list, timeout: int = 30) -> bool:
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
        print(f"[Client] WARNING — workers not ready: {remaining}")
        return False
    time.sleep(1.0)
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'=' * 80}")
    print("  CLIENT-ONLY MODE (Workers running on separate machines)")
    print(f"  NGINX      : {NGINX_URL}")
    print(f"  WORKERS    : {', '.join(WORKER_URLS)}")
    print(f"  USERS      : {NUM_USERS}")
    print(f"  CONSUMERS  : {NUM_CONSUMERS}")
    print(f"  TIMEOUT    : {REQUEST_TIMEOUT}s")
    print(f"{'=' * 80}\n")

    if not wait_for_workers(WORKER_URLS):
        print("[Client] Aborting — not all workers are ready")
        return

    logger = ResultsLogger(
        log_dir="logs",
        nginx_url=NGINX_URL,
        num_workers=len(WORKER_URLS),
        num_users=NUM_USERS,
    )

    scheduler = ClientScheduler(
        nginx_url=NGINX_URL,
        num_consumers=NUM_CONSUMERS,
        request_timeout=REQUEST_TIMEOUT,
    )

    heartbeat = HTTPHeartbeatMonitor(WORKER_URLS, interval=2)
    perf_monitor = HTTPPerformanceMonitor(WORKER_URLS, interval=5)
    queue_monitor = QueueMonitor(scheduler, interval=5)

    heartbeat.start()
    perf_monitor.start()
    queue_monitor.start()

    summary = run_http_load_test(
        num_users=NUM_USERS,
        label="nginx_distributed",
        scheduler=scheduler,
        logger=logger,
    )

    heartbeat.stop()
    perf_monitor.stop()
    queue_monitor.stop()
    scheduler.shutdown()

    # T021: Performance gate — evaluate 30-min SLA for runs ≥ 1000 requests
    if NUM_USERS >= 1000:
        total = summary["total_time"]
        tput = summary["throughput"]
        lat = summary["avg_latency"]
        status = "PASS" if total <= PERF_TARGET_SECONDS else "FAIL"
        perf_line = (
            f"[PERF] 1000-request target: {status} "
            f"(total={total:.0f}s, limit={PERF_TARGET_SECONDS}s, "
            f"throughput={tput} req/s, avg_latency={lat}s)"
        )
        logger.log_raw(perf_line)

    logger.close()
    print(f"\n[Client] Results saved to: {logger.path}")
    print("[Client] Load test completed")


if __name__ == "__main__":
    main()
