import time
import threading
from common.models import Request

def simulate_user(scheduler, user_id, results, lock):
    request = Request(id=user_id, query=f"Query {user_id}")
    try:
        response = scheduler.handle_request(request)
    except Exception:
        response = {"id": user_id, "result": "FAILED", "latency": -1}
    print(f"[Client] Response {response['id']} | Latency: {response['latency']:.3f}s")
    with lock:
        results.append(response)

def run_load_test(scheduler, num_users=200, label=''):
    results = []
    lock = threading.Lock()
    threads = []
    start = time.time()
    for i in range(num_users):
        t = threading.Thread(target=simulate_user, args=(scheduler, i, results, lock))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    end = time.time()

    total_time = round(end - start, 2)
    throughput = round(num_users / total_time, 1)

    successful = [r for r in results if r['result'] != 'FAILED' and r['latency'] != -1]
    failed = [r for r in results if r['result'] == 'FAILED' or r['latency'] == -1]

    latencies = [r['latency'] for r in successful]
    avg_latency = round(sum(latencies) / len(latencies), 3) if latencies else 0.0
    min_latency = round(min(latencies), 3) if latencies else 0.0
    max_latency = round(max(latencies), 3) if latencies else 0.0

    dead_workers = [w for w in scheduler.lb.workers if not w.is_alive]
    dead_ids = [f"Worker {w.id}" for w in dead_workers]

    print(f"\n  Successful Requests: {len(successful)}")
    print(f"  Failed Requests:     {len(failed)}")
    if dead_ids:
        print(f"  Dead Workers:        {dead_ids}")

    return {
        'label': label,
        'num_users': num_users,
        'total_time': total_time,
        'throughput': throughput,
        'avg_latency': avg_latency,
        'min_latency': min_latency,
        'max_latency': max_latency,
    }
