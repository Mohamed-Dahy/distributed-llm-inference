# ── LLM mode ──────────────────────────────────────────────────────────────────
# Stub mode (default):   PYTHONPATH=. python main.py
# Real Groq mode:        USE_REAL_LLM=true PYTHONPATH=. python main.py
#   → Requires GROQ_API_KEY in .env (already configured)
#   → Set NUM_USERS = 5 for real LLM mode — Groq rate limits can't handle 1000
#   → Model: llama3-8b-8192 (override with GROQ_MODEL env var)
# ──────────────────────────────────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv()

from workers.gpu_worker import GPUWorker
from workers.failure_simulator import FailureSimulator
from lb.load_balancer import LoadBalancer
from master.scheduler import Scheduler
from master.monitor import PerformanceMonitor
from master.heartbeat import HeartbeatMonitor
from client.load_generator import run_load_test

NUM_USERS = 1000
NUM_WORKERS = 4

def main():
    strategies = ['round_robin', 'least_connections', 'load_aware']
    all_stats = []
    all_worker_stats = []

    for strategy in strategies:
        workers = [GPUWorker(i) for i in range(NUM_WORKERS)]
        lb = LoadBalancer(workers, strategy=strategy)
        #lb.remove_worker(0)  # Simulate one worker already down at start

        sim = FailureSimulator(workers, failure_delay=0.1, num_failures=2)
        sim.start()

        scheduler = Scheduler(lb)
        monitor = PerformanceMonitor(workers, interval=5)
        heartbeat = HeartbeatMonitor(workers, interval=2)
        monitor.start()
        heartbeat.start()

        print(f"\n--- Running strategy: {strategy} ---")
        stats = run_load_test(scheduler, num_users=NUM_USERS, label=strategy)
        all_stats.append(stats)

        monitor.stop()
        heartbeat.stop()

        worker_stats = monitor.get_worker_stats()
        all_worker_stats.append((strategy, worker_stats))

    # ── Strategy comparison table ─────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"  LOAD BALANCING STRATEGY COMPARISON -- {NUM_USERS} users, {NUM_WORKERS} workers")
    print("=" * 60)
    print(f"  {'Strategy':<22}{'Total Time':<13}{'Throughput':<14}{'Avg Latency'}")
    print(f"  {'-' * 56}")
    for s in all_stats:
        total = f"{s['total_time']}s"
        tput  = f"{s['throughput']} req/s"
        avg   = f"{s['avg_latency']}s"
        print(f"  {s['label']:<22}{total:<13}{tput:<14}{avg}")
    print("=" * 60)

    # ── Per-worker stats per strategy ─────────────────────────────────────────
    for strategy, wstats in all_worker_stats:
        print()
        print("=" * 78)
        print(f"  PER-WORKER STATS -- {strategy}")
        print("=" * 78)
        print(f"  {'Worker':<8}{'Status':<8}{'Total':<8}{'Failed':<8}"
              f"{'Avg Latency':<14}{'Avg GPU':<10}{'Peak GPU'}")
        print(f"  {'-' * 72}")
        for w in wstats:
            print(
                f"  {w['id']:<8}"
                f"{w['status']:<8}"
                f"{w['total_requests']:<8}"
                f"{w['failed_requests']:<8}"
                f"{w['avg_latency']:<14}"
                f"{w['avg_gpu_util']:<10}"
                f"{w['peak_gpu_util']}%"
            )
        print("=" * 78)

if __name__ == "__main__":
    main()
