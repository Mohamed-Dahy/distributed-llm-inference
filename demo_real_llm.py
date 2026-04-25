"""
Real LLM Demo — 5 concurrent users through the full pipeline.

Run:
    set PYTHONPATH=. && set USE_REAL_LLM=true && python demo_real_llm.py

Requires GROQ_API_KEY in .env
"""

from dotenv import load_dotenv
load_dotenv()

import threading
import time
from workers.gpu_worker import GPUWorker
from lb.load_balancer import LoadBalancer
from master.scheduler import Scheduler
from common.models import Request
from client.load_generator import SAMPLE_QUERIES

NUM_USERS = 5
NUM_WORKERS = 4


def simulate_user(scheduler, user_id, results, lock):
    query = SAMPLE_QUERIES[user_id % len(SAMPLE_QUERIES)]
    request = Request(id=user_id, query=query)

    print(f"\n[User {user_id}] Asking: {query}")
    start = time.time()
    try:
        response = scheduler.handle_request(request)
        latency = time.time() - start
        print(f"\n[User {user_id}] Answer ({latency:.2f}s):\n  {response['result']}\n")
        with lock:
            results.append({"id": user_id, "ok": True, "latency": latency})
    except Exception as e:
        print(f"[User {user_id}] FAILED: {e}")
        with lock:
            results.append({"id": user_id, "ok": False, "latency": -1})


def main():
    workers = [GPUWorker(i) for i in range(NUM_WORKERS)]
    lb = LoadBalancer(workers, strategy='round_robin')
    scheduler = Scheduler(lb)

    print(f"Starting real LLM demo — {NUM_USERS} concurrent users\n")
    print("=" * 60)

    results = []
    lock = threading.Lock()
    threads = []
    start = time.time()

    for i in range(NUM_USERS):
        t = threading.Thread(target=simulate_user, args=(scheduler, i, results, lock))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    total = round(time.time() - start, 2)
    latencies = [r["latency"] for r in results if r["ok"]]
    avg = round(sum(latencies) / len(latencies), 2) if latencies else 0

    print("=" * 60)
    print(f"  Completed:    {len(latencies)}/{NUM_USERS} successful")
    print(f"  Total Time:   {total}s")
    print(f"  Avg Latency:  {avg}s per request")
    print("=" * 60)


if __name__ == "__main__":
    main()
