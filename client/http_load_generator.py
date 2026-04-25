import threading
import time

import httpx

from client.load_generator import SAMPLE_QUERIES


def simulate_http_user(user_id, results, lock):
    query = SAMPLE_QUERIES[user_id % len(SAMPLE_QUERIES)]
    payload = {"id": user_id, "query": query}

    start = time.time()
    try:
        response = httpx.post(
            "http://127.0.0.1:8080/process",
            json=payload,
            timeout=30.0,
        )
        data = response.json()
        latency = time.time() - start

        with lock:
            results.append(latency)

        print(
            f"[HTTP Client] Response {data['id']} | "
            f"Worker {data['worker_id']} | "
            f"Latency: {latency:.3f}s"
        )

    except Exception as e:
        print(f"[HTTP Client] Request {user_id} FAILED: {e}")


def run_http_load_test(num_users=200, label="nginx_round_robin"):
    results = []
    lock = threading.Lock()

    threads = []
    start = time.time()
    for i in range(num_users):
        t = threading.Thread(target=simulate_http_user, args=(i, results, lock))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    total_time = round(time.time() - start, 3)
    throughput = round(len(results) / total_time, 2) if total_time > 0 else 0
    avg_latency = round(sum(results) / len(results), 3) if results else 0
    min_latency = round(min(results), 3) if results else 0
    max_latency = round(max(results), 3) if results else 0

    print()
    print("=" * 60)
    print(f"  NGINX LOAD TEST -- {label}")
    print("=" * 60)
    print(f"  Users:        {num_users}")
    print(f"  Successful:   {len(results)}")
    print(f"  Failed:       {num_users - len(results)}")
    print(f"  Total Time:   {total_time}s")
    print(f"  Throughput:   {throughput} req/s")
    print(f"  Avg Latency:  {avg_latency}s")
    print(f"  Min Latency:  {min_latency}s")
    print(f"  Max Latency:  {max_latency}s")
    print("=" * 60)

    return {
        "label": label,
        "num_users": num_users,
        "total_time": total_time,
        "throughput": throughput,
        "avg_latency": avg_latency,
        "min_latency": min_latency,
        "max_latency": max_latency,
    }
