import subprocess
import time
import sys
import os

from dotenv import load_dotenv
load_dotenv()

import httpx

from client.http_load_generator import run_http_load_test


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

    run_http_load_test(num_users=50, label="nginx_round_robin")

    print("\n[Main] Shutting down workers...")
    for p in processes:
        p.terminate()


if __name__ == "__main__":
    main()
