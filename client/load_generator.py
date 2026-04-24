import time
import threading
from common.models import Request

SAMPLE_QUERIES = [
    "what is supervised learning and how does it work",
    "explain the gradient descent optimization algorithm",
    "what is overfitting and how do you prevent it",
    "how does a neural network learn from training data",
    "what is the difference between classification and regression",
    "explain the backpropagation algorithm in neural networks",
    "what is regularization and why is it used in machine learning",
    "how does logistic regression make predictions",
    "what is a support vector machine and how does it classify data",
    "explain the bias variance tradeoff in machine learning models",
    "what is the purpose of a cost function in machine learning",
    "how does k-means clustering group data points",
    "what is a decision tree and how does it split features",
    "explain how principal component analysis reduces dimensionality",
    "what is cross validation and why is it important for model evaluation",
    "how does the learning rate affect gradient descent convergence",
    "what is a convolutional neural network used for",
    "explain the difference between generative and discriminative models",
    "what is the expectation maximization algorithm",
    "how does naive bayes classify text data",
]

def simulate_user(scheduler, user_id, results, lock):
    query = SAMPLE_QUERIES[user_id % len(SAMPLE_QUERIES)]
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
