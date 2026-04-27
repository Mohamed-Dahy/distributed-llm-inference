from dataclasses import dataclass

@dataclass
class Request:
    id: int
    query: str

class WorkerDeadException(Exception):
    def __init__(self, worker_id):
        self.worker_id = worker_id
        super().__init__(f"Worker {worker_id} is dead")

class WorkerOverloadedException(Exception):
    def __init__(self, worker_id):
        self.worker_id = worker_id
        super().__init__(f"Worker {worker_id} is overloaded")