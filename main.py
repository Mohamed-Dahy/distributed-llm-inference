# ── LLM mode ──────────────────────────────────────────────────────────────────
# Stub mode (default):   PYTHONPATH=. python main.py
# Real Ollama mode:      USE_REAL_LLM=true PYTHONPATH=. python main.py
#   → Requires Ollama running locally with a model pulled (default: mistral)
#   → Set NUM_USERS = 5 for real LLM mode — Ollama processes serially per model
#   → Override model: OLLAMA_MODEL=llama3.2:1b ...
# All console output is also saved to logs/run_<timestamp>.log
# ──────────────────────────────────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv()

import os
import sys
from datetime import datetime

from workers.gpu_worker import GPUWorker
from workers.failure_simulator import FailureSimulator
from lb.load_balancer import LoadBalancer
from master.scheduler import Scheduler
from master.queue_monitor import QueueMonitor
from master.monitor import PerformanceMonitor
from master.heartbeat import HeartbeatMonitor
from client.load_generator import run_load_test

NUM_USERS = 5
NUM_WORKERS = 4


class Tee:
    """Mirror writes to multiple streams (terminal + log file)."""
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()
    def flush(self):
        for s in self.streams:
            s.flush()


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    log_path = f"logs/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    sys.stdout = Tee(sys.__stdout__, log_file)
    sys.stderr = Tee(sys.__stderr__, log_file)
    print(f"[Main] Logging to {log_path}")
    return log_file


def main():
    log_file = setup_logging()

    strategies = ['round_robin', 'least_connections', 'load_aware']
    all_stats = []
    all_worker_stats = []

    for strategy in strategies:
        workers = [GPUWorker(i, max_capacity=NUM_USERS) for i in range(NUM_WORKERS)]
        lb = LoadBalancer(workers, strategy=strategy)
        #lb.remove_worker(0)  # Simulate one worker already down at start

        sim = FailureSimulator(workers, failure_delay=0.1, num_failures=2)
        sim.start()

        # Initialize scheduler with queue-based configuration (NEW!)
        scheduler = Scheduler(lb, num_consumers=4, request_timeout=30)
        
        # Create and start monitoring components
        queue_monitor = QueueMonitor(scheduler, interval=5)
        monitor = PerformanceMonitor(workers, interval=5)
        heartbeat = HeartbeatMonitor(workers, interval=2)
        
        print(f"\n{'='*60}")
        print(f"  STRATEGY : {strategy}")
        print(f"  USERS    : {NUM_USERS}    WORKERS : {NUM_WORKERS}")
        print(f"  QUEUE    : 4 consumer threads, 30s timeout (NEW!)")
        print(f"{'='*60}\n")
        
        queue_monitor.start()
        monitor.start()
        heartbeat.start()
        
        stats = run_load_test(scheduler, num_users=NUM_USERS, label=strategy)
        all_stats.append(stats)

        queue_monitor.stop()
        monitor.stop()
        heartbeat.stop()
        
        # Graceful shutdown of scheduler (NEW!)
        scheduler.shutdown()

        worker_stats = monitor.get_worker_stats()
        all_worker_stats.append((strategy, worker_stats))

    # ── Strategy comparison table ─────────────────────────────────────────────
    print()
    print("=" * 80)
    print(f"  LOAD BALANCING STRATEGY COMPARISON -- {NUM_USERS} users, {NUM_WORKERS} workers")
    print("=" * 80)
    print(f"  {'Strategy':<20} {'Time':<8} {'Throughput':<12} {'Avg Latency':<12} {'Queue Wait':<12}")
    print(f"  {'-' * 76}")
    for s in all_stats:
        total = f"{s['total_time']}s"
        tput = f"{s['throughput']} req/s"
        avg = f"{s['avg_latency']}s"
        qwait = f"{s.get('avg_queue_wait', 0)}s"  # NEW!
        print(f"  {s['label']:<20} {total:<8} {tput:<12} {avg:<12} {qwait:<12}")
    print("=" * 80)

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

    log_file.close()

if __name__ == "__main__":
    main()
