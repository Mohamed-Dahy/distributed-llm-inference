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
  REQUEST_TIMEOUT     — seconds before a request times out (default 1800)
  PERF_TARGET_SECONDS — SLA threshold for 1000-request run (default 1800)
"""

import os
import re
import subprocess
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
NUM_USERS = int(os.getenv("NUM_USERS", 1000))
NUM_CONSUMERS = int(os.getenv("NUM_CONSUMERS", 4))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 1800))
PERF_TARGET_SECONDS = int(os.getenv("PERF_TARGET_SECONDS", 1800))

WORKER_URLS = [
    os.getenv("WORKER_1", "http://127.0.0.1:8001"),
    os.getenv("WORKER_2", "http://127.0.0.1:8002"),
    os.getenv("WORKER_3", "http://127.0.0.1:8003"),
    os.getenv("WORKER_4", "http://127.0.0.1:8004"),
]

NGINX_CONF = os.path.join(os.path.dirname(__file__), "nginx", "nginx.conf")


# ── NGINX upstream patching ───────────────────────────────────────────────────

def _url_to_host_port(url: str) -> str:
    return url.replace("http://", "").replace("https://", "").rstrip("/")


def _nginx_reload():
    result = subprocess.run(
        ["nginx", "-c", os.path.abspath(NGINX_CONF), "-s", "reload"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[NGINX] reload failed: {result.stderr.strip()}")
    else:
        print("[NGINX] upstream reloaded")


def on_worker_dead(url: str):
    host_port = _url_to_host_port(url)
    with open(NGINX_CONF, "r") as f:
        conf = f.read()
    # Comment out the server line so NGINX stops routing to it
    patched = re.sub(
        r"(\s+)(server " + re.escape(host_port) + r"[^;]*;)",
        r"\1# \2  # auto-disabled: DEAD",
        conf,
    )
    if patched == conf:
        print(f"[NGINX] server entry for {host_port} not found in {NGINX_CONF}")
        return
    with open(NGINX_CONF, "w") as f:
        f.write(patched)
    print(f"[NGINX] Disabled dead worker {url} in upstream")
    _nginx_reload()


def on_worker_alive(url: str):
    host_port = _url_to_host_port(url)
    with open(NGINX_CONF, "r") as f:
        conf = f.read()
    # Restore the server line
    patched = re.sub(
        r"(\s+)# (server " + re.escape(host_port) + r"[^;]*;)  # auto-disabled: DEAD",
        r"\1\2",
        conf,
    )
    if patched == conf:
        return  # already active, nothing to do
    with open(NGINX_CONF, "w") as f:
        f.write(patched)
    print(f"[NGINX] Re-enabled revived worker {url} in upstream")
    _nginx_reload()


# ── Helpers ───────────────────────────────────────────────────────────────────

def restore_nginx_conf():
    """Uncomment any workers that were auto-disabled by a previous run."""
    with open(NGINX_CONF, "r") as f:
        conf = f.read()
    patched = re.sub(
        r"(\s+)# (server [^;]*;)  # auto-disabled: DEAD",
        r"\1\2",
        conf,
    )
    if patched != conf:
        with open(NGINX_CONF, "w") as f:
            f.write(patched)
        print("[NGINX] Restored auto-disabled workers from previous run")
        _nginx_reload()


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
    restore_nginx_conf()

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

    for url in WORKER_URLS:
        try:
            httpx.post(f"{url}/reset", timeout=2.0)
            print(f"[Client] Reset stats on {url}")
        except Exception:
            print(f"[Client] Could not reset {url} (skipping)")

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

    heartbeat = HTTPHeartbeatMonitor(
        WORKER_URLS,
        interval=2,
        timestamp=logger.timestamp,
        on_worker_dead=on_worker_dead,
        on_worker_alive=on_worker_alive,
    )
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

    # ── Final worker stats table ──────────────────────────────────────────────
    divider = "-" * 100
    header = (
        f"\n{'=' * 100}\n"
        f"  FINAL WORKER STATS\n"
        f"{'=' * 100}\n"
        f"  {'Worker':<30} {'Status':<6} {'Success':>8} {'W-Fail':>7} {'NGINX-Err':>10} {'Active':>7} {'Avg Lat':>9} {'GPU%':>6} {'Mode':<8}\n"
        f"  {divider}"
    )
    logger.log_raw(header)
    total_success = 0
    total_worker_fail = 0
    for url in WORKER_URLS:
        try:
            r = httpx.get(f"{url}/stats", timeout=3.0)
            d = r.json()
            worker_fail = d.get('failed_requests', 0)
            successful = d['total_requests']  # total_requests counts only successes; failed_requests is tracked separately
            total_success += successful
            total_worker_fail += worker_fail
            row = (
                f"  {url:<30} {d['status']:<6} "
                f"{successful:>8} {worker_fail:>7} {'N/A':>10} "
                f"{d['active_requests']:>7} {d['avg_latency']:>8.3f}s "
                f"{d['gpu_utilization']:>5.1f}% {d.get('llm_mode', '?'):<8}"
            )
        except Exception:
            row = f"  {url:<30} UNREACHABLE"
        logger.log_raw(row)
    # Client-visible outcomes are the ground truth.
    # Per-worker success counts undercount when NGINX retries route one client
    # request through multiple workers (the failed worker touch inflates W-Fail
    # while the successful retry lands in another worker's total).
    client_successes = summary.get("client_successes", total_success)
    client_errors = summary.get("client_errors", max(NUM_USERS - total_success - total_worker_fail, 0))
    logger.log_raw(f"  {divider}")
    logger.log_raw(
        f"  {'TOTAL (client)':<30} {'':6} {client_successes:>8} {total_worker_fail:>7} {client_errors:>10} "
        f"{'':7} {'':9} {'':6}"
    )
    logger.log_raw(
        f"  Note: Success/NGINX-Err = client-visible outcomes. W-Fail = per-worker internal failures"
        f" (may be retried by NGINX and succeed)."
    )
    logger.log_raw(f"  {'=' * 100}")

    logger.close()
    print(f"\n[Client] Results saved to: {logger.path}")
    print("[Client] Load test completed")


if __name__ == "__main__":
    main()
