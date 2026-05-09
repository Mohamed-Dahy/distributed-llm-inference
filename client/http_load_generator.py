import threading
import time

from client.load_generator import SAMPLE_QUERIES


def simulate_http_user(user_id: int, scheduler, logger, results: list, lock: threading.Lock):
    query = SAMPLE_QUERIES[user_id % len(SAMPLE_QUERIES)]

    # Log request sent before dispatching
    logger.log_sent(user_id, query)

    start = time.time()
    data = scheduler.handle_request(user_id, query)
    latency = time.time() - start

    result_text = data.get("result", "ERROR")
    worker_id = data.get("worker_id", -1)
    worker_latency_ms = round(data.get("latency", latency) * 1000) if data.get("latency", -1) >= 0 else -1

    # Log response received
    logger.log_response(worker_id, user_id, query, result_text, worker_latency_ms)

    with lock:
        results.append(latency)


def run_http_load_test(num_users: int = 20, label: str = "nginx_distributed", scheduler=None, logger=None) -> dict:
    results = []
    lock = threading.Lock()

    threads = []
    start = time.time()
    for i in range(num_users):
        t = threading.Thread(target=simulate_http_user, args=(i, scheduler, logger, results, lock))
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
