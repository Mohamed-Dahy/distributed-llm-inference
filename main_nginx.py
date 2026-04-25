import subprocess
import time
import sys
import os
import threading

from dotenv import load_dotenv
load_dotenv()

import httpx

from client.http_load_generator import run_http_load_test


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

    def start(self):
        t = threading.Thread(target=self._report, daemon=True)
        t.start()

    def _report(self):
        while self.running:
            print(f"\n[Monitor] -------- System Performance --------")
            for port in self.ports:
                try:
                    r = httpx.get(f"http://127.0.0.1:{port}/stats", timeout=1.0)
                    d = r.json()
                    print(
                        f"[Monitor] Worker {d['worker_id']} | "
                        f"Status: {d['status']} | "
                        f"Active: {d['active_requests']} req | "
                        f"Total: {d['total_requests']} req | "
                        f"Avg Latency: {d['avg_latency']}s"
                    )
                except Exception:
                    print(f"[Monitor] Worker on port {port} -- unreachable")
            print(f"[Monitor] --------------------------------------\n")
            time.sleep(self.interval)

    def stop(self):
        self.running = False


def wait_for_workers(ports, timeout=15):
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


def main():
    processes = []
    for worker_id in range(1, 5):
        p = subprocess.Popen(
            [sys.executable, "workers/worker_server.py", str(worker_id)],
            env={**os.environ, "PYTHONPATH": "."},
        )
        processes.append(p)

    ports = [8001, 8002, 8003, 8004]
    wait_for_workers(ports)

    print("\n[Main] All workers ready. Starting NGINX load test...\n")
    print("NOTE: Make sure NGINX is running with:")
    print("  C:\\nginx-1.30.0\\nginx.exe -c <absolute-path>\\nginx\\nginx.conf\n")

    heartbeat = HTTPHeartbeatMonitor(ports, interval=2)
    monitor = HTTPPerformanceMonitor(ports, interval=5)
    heartbeat.start()
    monitor.start()

    run_http_load_test(num_users=40, label="nginx_round_robin")

    heartbeat.stop()
    monitor.stop()

    print("\n[Main] Shutting down workers...")
    for p in processes:
        p.terminate()


if __name__ == "__main__":
    main()
