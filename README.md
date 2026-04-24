# distributed-llm-inference

A simulated distributed system for handling 1000+ concurrent LLM inference requests with load balancing, RAG integration, and fault tolerance — built for CSE354: Distributed Computing at Ain Shams University.

---

## Setup

1. **Python 3.9+** — verify with `python3 --version`

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Ollama** (for real LLM mode only):
   - Download from [ollama.com](https://ollama.com) and install
   - Pull the model:
     ```bash
     ollama pull mistral
     ```
   - Start the Ollama server:
     ```bash
     ollama serve
     ```

---

## Run

### Stub mode — for load testing (default)

No Ollama required. Uses a simulated 0.2s delay instead of real inference.

```bash
PYTHONPATH=. python3 main.py
```

### Real LLM mode — for demo

Requires Ollama running with Mistral pulled. Set `NUM_USERS = 10` in `main.py` first — real API calls cannot handle 1000 concurrent requests.

```bash
USE_REAL_LLM=true PYTHONPATH=. python3 main.py
```

If Ollama is unavailable mid-run, the system automatically falls back to stub mode per request.

---

## Switch Load Balancing Strategies

Edit `main.py` — the `strategies` list controls which algorithms run and in what order:

```python
strategies = ['round_robin', 'least_connections', 'load_aware']
```

- **`round_robin`** — distributes requests sequentially across workers
- **`least_connections`** — always picks the worker with the fewest active requests
- **`load_aware`** — picks the worker with the lowest `active_requests × avg_latency` score

---

## Fault Tolerance Configuration

Also in `main.py`:

```python
lb.remove_worker(0)                                          # kill a worker before the run starts
sim = FailureSimulator(workers, failure_delay=0.1, num_failures=1)  # kill N workers mid-run
```

- With at least 1 alive worker, retries succeed → 0 failed requests (fault tolerance working)
- Set `num_failures` equal to all remaining alive workers to force visible failures

---

## Folder Structure

```
distributed-llm-inference/
├── client/
│   └── load_generator.py       # spawns N concurrent user threads, collects latency stats
├── master/
│   └── scheduler.py            # thin dispatcher — logs and delegates to load balancer
├── workers/
│   ├── gpu_worker.py           # RAG → LLM pipeline per request, tracks alive/latency state
│   └── failure_simulator.py    # daemon thread that kills random workers after a delay
├── lb/
│   └── load_balancer.py        # three routing strategies + retry dispatch
├── rag/
│   ├── retriever.py            # ChromaDB vector search over ingested PDFs
│   ├── ingest.py               # PDF → text chunks → ChromaDB
│   └── Data/                   # place PDF knowledge base files here
├── llm/
│   └── inference.py            # stub (default) or Ollama real inference
├── common/
│   └── models.py               # Request / Response dataclasses + WorkerDeadException
├── main.py                     # entry point — configure NUM_USERS, NUM_WORKERS, strategies here
├── requirements.txt
└── test_rag.py                 # standalone RAG pipeline test
```

---

## Course

**CSE354: Distributed Computing** — 2nd Semester 2025/2026
Faculty of Engineering, Ain Shams University
