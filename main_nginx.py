import subprocess
import time
import sys
import os
import threading

from dotenv import load_dotenv
load_dotenv()

import httpx

from client.http_load_generator import run_http_load_test

NUM_USERS = 5
WORKER_PORTS = [8001, 8002, 8003, 8004]


class HTTPHeartbeatMonitor:
    def __init__(self, ports, interval=2):
        self.ports = ports
        self.interval = interval
        self.running = True
        self._last_status = {port: True for port in ports}

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        while self.running:
            time.sleep(self.interval)
            for port in self.ports:
                try:
                    r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
                    current = r.status_code == 200
                except Exception:
                    current = False
                previous = self._last_status[port]
                if previous and not current:
                    print(f"[Heartbeat] ALERT -- Worker on port {port} is DOWN")
                elif not previous and current:
                    print(f"[Heartbeat] Worker on port {port} is back ONLINE")
                self._last_status[port] = current

    def stop(self):
        self.running = False


class HTTPPerformanceMonitor:
    def __init__(self, ports, interval=5):
        self.ports = ports
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
                f"[Monitor]  {'W':<4} {'Status':<6} {'Active':>6} {'Total':>6} {'Failed':>6} {'Latency':>8} {'GPU':>6}",
                f"[Monitor]  {'─'*50}",
            ]
            for port in self.ports:
                try:
                    r = httpx.get(f"http://127.0.0.1:{port}/stats", timeout=1.0)
                    d = r.json()
                    lines.append(
                        f"[Monitor]  {d['worker_id']:<4} {d['status']:<6} "
                        f"{d['active_requests']:>6} {d['total_requests']:>6} {d.get('failed_requests', 0):>6} "
                        f"{d['avg_latency']:>7.3f}s {d['gpu_utilization']:>5.1f}%"
                    )
                except Exception:
                    lines.append(f"[Monitor]  port {port} -- unreachable")
            lines.append(f"[Monitor] {'─'*52}")
            print('\n'.join(lines))
            time.sleep(self.interval)

    def stop(self):
        self.running = False


def wait_for_workers(ports, timeout=30):
    deadline = time.time() + timeout
    remaining = set(ports)
    while remaining and time.time() < deadline:
        for port in list(remaining):
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
                if r.status_code == 200:
                    print(f"[Main] Worker on port {port} is ready")
                    remaining.discard(port)
            except Exception:
                pass
        if remaining:
            time.sleep(0.5)
    if remaining:
        print(f"[Main] WARNING -- workers on ports {remaining} did not respond in time")
        return False
    time.sleep(1.0)  # brief stabilization — lets uvicorn threadpool warm up
    return True


def main():
    processes = []
    for worker_id in range(1, len(WORKER_PORTS) + 1):
        p = subprocess.Popen(
            [sys.executable, "workers/worker_server.py", str(worker_id)],
            env={**os.environ, "PYTHONPATH": ".", "MAX_CAPACITY": str(NUM_USERS)},
        )
        processes.append(p)

    if not wait_for_workers(WORKER_PORTS):
        print("[Main] Aborting — not all workers are ready. Check for port conflicts from previous runs.")
        for p in processes:
            p.terminate()
        return

    print(f"\n{'='*60}")
    print(f"  MODE     : NGINX (HTTP)")
    print(f"  USERS    : {NUM_USERS}    WORKERS : {len(WORKER_PORTS)}")
    print(f"  NGINX    : http://127.0.0.1:8080")
    print(f"{'='*60}")
    print("  NOTE: Make sure NGINX is running with:")
    print(f"    nginx -c <abs-path>\\nginx\\nginx.conf")
    print(f"{'='*60}\n")

    heartbeat = HTTPHeartbeatMonitor(WORKER_PORTS, interval=2)
    monitor = HTTPPerformanceMonitor(WORKER_PORTS, interval=5)
    heartbeat.start()
    monitor.start()

    run_http_load_test(num_users=NUM_USERS, label="nginx_round_robin")

    heartbeat.stop()
    monitor.stop()

    print("\n[Main] Shutting down workers...")
    for p in processes:
        p.terminate()


if __name__ == "__main__":
    main()