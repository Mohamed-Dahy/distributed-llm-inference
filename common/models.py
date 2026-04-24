from dataclasses import dataclass

@dataclass
class Request:
    id: int
    query: str

@dataclass
class Response:
    id: int
    result: str
    latency: float

class WorkerDeadException(Exception):
    def __init__(self, worker_id):
        self.worker_id = worker_id
        super().__init__(f"Worker {worker_id} is dead")