import time
import threading
from common.models import Request

def simulate_user(scheduler, user_id, results, lock):
    request = Request(id=user_id, query=f"Query {user_id}")
    response = scheduler.handle_request(request)
    print(f"[Client] Response {response['id']} | Latency: {response['latency']:.3f}s")
    with lock:
        results.append(response['latency'])

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
    avg_latency = round(sum(results) / len(results), 3)
    min_latency = round(min(results), 3)
    max_latency = round(max(results), 3)

    return {
        'label': label,
        'num_users': num_users,
        'total_time': total_time,
        'throughput': throughput,
        'avg_latency': avg_latency,
        'min_latency': min_latency,
        'max_latency': max_latency,
    }
