import time
import threading
from common.models import Request

# Questions targeted at the Stanford CS229 Machine Learning lectures in rag/Data/
SAMPLE_QUERIES = [
    "what is supervised learning according to the lecture",
    "explain how gradient descent works in linear regression",
    "what is the normal equation and when is it used",
    "what is overfitting and how does regularization help",
    "explain the perceptron learning algorithm",
    "what is logistic regression used for",
    "describe the Gaussian Discriminant Analysis algorithm",
    "what is the Naive Bayes classifier and what assumption does it make",
    "explain the kernel trick in support vector machines",
    "what is the bias-variance tradeoff",
    "describe the EM algorithm for Gaussian mixture models",
    "how does Principal Component Analysis reduce dimensionality",
    "what is k-means clustering and how does it work",
    "explain how decision trees split features",
    "what is reinforcement learning and how does it differ from supervised learning",
    "describe Markov Decision Processes",
    "what is value iteration in reinforcement learning",
    "explain backpropagation in neural networks",
    "what is cross-validation and why is it important",
    "describe the VC dimension and learning theory",
]

def simulate_user(scheduler, user_id, results, lock):
    query = SAMPLE_QUERIES[user_id % len(SAMPLE_QUERIES)]
    request = Request(id=user_id, query=query)
    try:
        response = scheduler.handle_request(request)
    except Exception:
        response = {"id": user_id, "result": "FAILED", "latency": -1}

    with lock:
        results.append(response)

        if response['result'] == 'FAILED':
            print(f"[Client] Request {response['id']} FAILED")
        else:
            result_text = response['result']
            preview = result_text if len(result_text) <= 400 else result_text[:400] + "..."
            
            # Display queue wait time (NEW!)
            queue_wait = response.get('queue_wait_time', 0)
            processing = response['latency']
            total = queue_wait + processing
            
            print(f"\n[Client] ──── Response {response['id']} ────")
            print(f"  Worker: {response.get('worker_id', 'N/A')}")
            print(f"  Queue Wait: {queue_wait:.3f}s | Processing: {processing:.3f}s | Total: {total:.3f}s")
            print(f"  Q: {query}")
            print(f"  A: {preview}\n")

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
    queue_waits = [r.get('queue_wait_time', 0) for r in successful]
    
    avg_latency = round(sum(latencies) / len(latencies), 3) if latencies else 0.0
    min_latency = round(min(latencies), 3) if latencies else 0.0
    max_latency = round(max(latencies), 3) if latencies else 0.0
    
    # NEW: Track queue statistics
    avg_queue_wait = round(sum(queue_waits) / len(queue_waits), 3) if queue_waits else 0.0
    max_queue_wait = round(max(queue_waits), 3) if queue_waits else 0.0

    dead_workers = [w for w in scheduler.lb.workers if not w.is_alive]
    dead_ids = [f"Worker {w.id}" for w in dead_workers]

    print(f"\n  Successful Requests: {len(successful)}")
    print(f"  Failed Requests:     {len(failed)}")
    print(f"  Avg Queue Wait:      {avg_queue_wait}s (NEW!)")
    print(f"  Max Queue Wait:      {max_queue_wait}s (NEW!)")
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
        'avg_queue_wait': avg_queue_wait,  # NEW!
        'max_queue_wait': max_queue_wait,  # NEW!
    }
