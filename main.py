from workers.gpu_worker import GPUWorker
from workers.failure_simulator import FailureSimulator
from lb.load_balancer import LoadBalancer
from master.scheduler import Scheduler
from client.load_generator import run_load_test

NUM_USERS = 1000
NUM_WORKERS = 4

def main():
    strategies = ['round_robin', 'least_connections', 'load_aware']
    all_stats = []

    for strategy in strategies:
        workers = [GPUWorker(i) for i in range(NUM_WORKERS)]
        lb = LoadBalancer(workers, strategy=strategy)
        lb.remove_worker(0)  # Simulate one worker already down at start

        sim = FailureSimulator(workers, failure_delay=0.1, num_failures=2)
        sim.start()

        scheduler = Scheduler(lb)
        print(f"\n--- Running strategy: {strategy} ---")
        stats = run_load_test(scheduler, num_users=NUM_USERS, label=strategy)
        all_stats.append(stats)

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

if __name__ == "__main__":
    main()
