# Phase 5 — Real LLM Integration

## Context

Phase 4 left the system with a fully working distributed pipeline — load balancing, fault
tolerance, RAG retrieval — but `llm/inference.py` was still a stub (`time.sleep(0.2)`).

Phase 5 replaces it with a real Ollama LLM call while keeping the stub as the default for
load testing. The rest of the codebase is completely untouched — `run_llm(query, context)`
signature is unchanged, so `GPUWorker.process()` requires no modification.

---

## What Changed

### `llm/inference.py` — full rewrite

The file now supports two modes, switched via an environment variable:

```python
USE_REAL_LLM = os.getenv("USE_REAL_LLM", "false").lower() == "true"
OLLAMA_URL   = "http://localhost:11434/api/generate"
MODEL_NAME   = "mistral"
```

**`run_llm(query, context)`** — public function, unchanged signature:
- If `USE_REAL_LLM` is `False` → calls `_stub_llm()` directly
- If `USE_REAL_LLM` is `True` → tries `_ollama_llm()`, catches any exception, logs
  `[LLM] Real LLM failed: {error}, falling back to stub`, then falls back to `_stub_llm()`

**`_stub_llm(query, context)`** — identical to the original:
```python
time.sleep(0.2)
return f"LLM Answer to '{query}' using [{context}]"
```

**`_ollama_llm(query, context)`** — new:
- Lazy-imports `requests` inside the function body so stub mode works with zero extra dependencies
- Builds a prompt that injects the RAG context and instructs the model to answer concisely
- POSTs to `OLLAMA_URL` with `{"model": MODEL_NAME, "prompt": ..., "stream": False}` and `timeout=30`
- Calls `response.raise_for_status()` and returns `response.json()["response"].strip()`
- Any exception bubbles up to `run_llm()` which handles the fallback

---

### `requirements.txt` — new file

```
chromadb
pypdf
requests
# anthropic  # alternative to Ollama
```

---

### `README.md` — rewritten

Added clear sections for:
- Setup (install deps, install Ollama, pull Mistral)
- Run in stub mode vs real LLM mode
- How to switch load balancing strategies
- Fault tolerance configuration
- Full folder structure

---

### `main.py` — comment block added

A comment block at the top explains the two run modes so the file is self-documenting:

```python
# Stub mode (default):   PYTHONPATH=. python3 main.py
# Real LLM mode:         USE_REAL_LLM=true PYTHONPATH=. python3 main.py
#   → Requires Ollama running with Mistral pulled (ollama pull mistral)
#   → Set NUM_USERS = 10 for real LLM mode — APIs can't handle 1000 threads
```

---

## Files Not Changed

`gpu_worker.py`, `load_balancer.py`, `scheduler.py`, `load_generator.py`,
`retriever.py`, `models.py`, `failure_simulator.py`

---

## How to Run

### Stub mode (default — for load testing)

```bash
PYTHONPATH=. python3 main.py
```

### Real LLM mode (for demo)

```bash
# Step 1 — install Ollama from ollama.com, then:
ollama pull mistral
ollama serve

# Step 2 — install Python dependency
pip install -r requirements.txt

# Step 3 — set NUM_USERS = 10 in main.py, then:
USE_REAL_LLM=true PYTHONPATH=. python3 main.py
```

---

## Design Decisions

**Why env var instead of a config file?**
Zero-overhead for the default case — no file to parse, no import cost. The default is
`"false"` so existing `python3 main.py` invocations require no changes.

**Why lazy-import `requests` inside `_ollama_llm()`?**
`requests` is already in `requirements.txt` (pulled in by chromadb), but importing it at
module level would add startup overhead and fail if someone runs the stub without it installed.
The lazy import means stub mode has no dependency on `requests` at all.

**Why automatic fallback instead of crashing?**
In a distributed system under load, a single backend failure should not take down the whole
pipeline. The fallback preserves the system's availability guarantee — every request gets
a response, even if Ollama goes down mid-run.

**Why keep NUM_USERS = 10 for real LLM mode?**
Ollama runs one model inference at a time (single GPU / CPU thread). Sending 1000 concurrent
HTTP requests would queue them all, each waiting for the previous to finish, resulting in
the last request waiting ~1000 × inference_time. 10 users gives a realistic demo latency
without overwhelming the local model server.

---

## Testing Steps

### Step 1 — Start the Ollama server

Open a terminal and run:
```bash
ollama serve
```
You should see `Listening on 127.0.0.1:11434`. Keep this terminal open for all subsequent steps.

### Step 2 — Pull the Mistral model

Open a **second terminal** and run:
```bash
ollama pull mistral
```
This downloads ~4 GB. One-time only.

### Step 3 — Install Python dependencies

```bash
cd distributed-llm-inference
source venv/bin/activate
pip install -r requirements.txt
```

### Step 4 — Test the real LLM (small scale)

Set `NUM_USERS = 5` in `main.py`, then run:
```bash
USE_REAL_LLM=true PYTHONPATH=. python3 main.py
```
Expected: real answers to ML questions instead of the `LLM Answer to '...'` template string.
Latency will be ~1–5s per request instead of 0.2s.

### Step 5 — Test the automatic fallback

While a run is active, stop Ollama (`Ctrl+C` in its terminal). You should see:
```
[LLM] Real LLM failed: ..., falling back to stub
```
The system must continue processing all remaining requests without crashing.

### Step 6 — Confirm stub mode is unchanged

Restore `NUM_USERS = 1000` in `main.py` and run without any env var:
```bash
PYTHONPATH=. python3 main.py
```
Expected: same behaviour as Phase 3 — ~0.2s avg latency, 1000 users, comparison table prints.

---

## Acceptance Criteria

- [x] `PYTHONPATH=. python3 main.py` runs with no env vars set — stub mode, unchanged behaviour
- [x] `USE_REAL_LLM=true` activates Ollama path; fallback fires automatically if Ollama is down
- [x] `requests` is never imported in stub mode
- [x] `run_llm()` signature unchanged — no other file required modification
- [x] `requirements.txt` exists with all project dependencies
