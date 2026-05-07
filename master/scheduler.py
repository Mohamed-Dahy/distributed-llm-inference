import queue
import threading
from concurrent.futures import ThreadPoolExecutor
import time


class Scheduler:
    def __init__(self, load_balancer, num_consumers=4, request_timeout=30):
        self.lb = load_balancer
        self.request_queue = queue.Queue()
        self.num_consumers = num_consumers
        self.request_timeout = request_timeout
        self.running = True
        self.response_map = {}  # Maps request_id to response
        self.lock = threading.Lock()
        
        # Persistent thread pool instead of spawning per request
        self.executor = ThreadPoolExecutor(max_workers=num_consumers)
        
        # Start persistent consumer threads
        for _ in range(num_consumers):
            self.executor.submit(self._consumer_loop)
        
        print(f"[Scheduler] Started with {num_consumers} consumer threads")

    def handle_request(self, request):
        print(f"[Scheduler] Queuing request {request.id} (queue size: {self.request_queue.qsize()})")
        
        response_queue = queue.Queue()
        queue_start_time = time.time()
        
        # Enqueue request + response queue
        self.request_queue.put({
            "request": request,
            "response_queue": response_queue,
            "enqueued_at": queue_start_time
        })
        
        # Wait for result with timeout
        try:
            response = response_queue.get(timeout=self.request_timeout)
            wait_time = time.time() - queue_start_time
            print(f"[Scheduler] Request {request.id} completed (wait: {wait_time:.3f}s)")
            return response
        except queue.Empty:
            print(f"[Scheduler] Request {request.id} TIMEOUT after {self.request_timeout}s")
            return {"id": request.id, "result": "TIMEOUT", "latency": -1, "worker_id": -1}

    def _consumer_loop(self):
        """Persistent consumer thread - continuously drains queue"""
        thread_id = threading.current_thread().ident
        print(f"[Scheduler] Consumer thread {thread_id} started")
        
        while self.running:
            try:
                # Get from queue with timeout to allow graceful shutdown
                item = self.request_queue.get(timeout=1.0)
                request = item["request"]
                response_queue = item["response_queue"]
                enqueued_at = item["enqueued_at"]
                
                # Calculate wait time in queue
                wait_time = time.time() - enqueued_at
                
                # Get current queue depth for load balancer awareness
                queue_depth = self.request_queue.qsize()
                
                try:
                    # Dispatch to load balancer with queue info
                    response = self.lb.dispatch(
                        request, 
                        queue_depth=queue_depth,
                        request_wait_time=wait_time
                    )
                    
                    # Add queue metrics to response
                    response["queue_wait_time"] = round(wait_time, 3)
                    response_queue.put(response)
                    
                except Exception as e:
                    print(f"[Scheduler] Error processing request {request.id}: {e}")
                    response_queue.put({
                        "id": request.id,
                        "result": "ERROR",
                        "latency": -1,
                        "worker_id": -1,
                        "error": str(e)
                    })
                finally:
                    self.request_queue.task_done()
                    
            except queue.Empty:
                # Timeout waiting for item - continue loop (allows graceful shutdown check)
                continue

    def shutdown(self):
        """Gracefully shutdown scheduler"""
        print("[Scheduler] Shutting down...")
        self.running = False
        
        # Wait for all queued requests to be processed
        self.request_queue.join()
        print("[Scheduler] All requests processed")
        
        # Shutdown thread pool
        self.executor.shutdown(wait=True)
        print("[Scheduler] Consumer threads stopped")

    def get_queue_stats(self):
        """Return queue statistics"""
        return {
            "queue_size": self.request_queue.qsize(),
            "num_consumers": self.num_consumers,
            "request_timeout": self.request_timeout
        }