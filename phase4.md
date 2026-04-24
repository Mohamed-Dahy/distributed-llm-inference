# Phase 3B — Real RAG with Vector Database Implementation Plan

## Context

This is a distributed LLM inference simulation project (CSE354: Distributed Computing).
Phases 1, 2, and fault tolerance (Phase 3A) are already complete and working.

Current state of `rag/retriever.py` is a stub:
```python
def retrieve_context(query):
    return f"Relevant context for: {query}"
```

This phase replaces that stub with a real vector database using ChromaDB.
The knowledge base is populated from the actual CSE354 course material —
5 chapters of distributed systems lecture PDFs provided by the student.
This means retrieval returns real academic content from the course syllabus,
making the RAG pipeline genuinely meaningful.

The project structure is:
```
cse354-project/
├── client/
│   ├── __init__.py
│   └── load_generator.py
├── master/
│   ├── __init__.py
│   ├── scheduler.py
│   └── heartbeat.py
├── workers/
│   ├── __init__.py
│   └── gpu_worker.py
├── lb/
│   ├── __init__.py
│   └── load_balancer.py
├── rag/
│   ├── __init__.py
│   ├── retriever.py         ← replace this
│   ├── ingest.py            ← create this (PDF extraction + chunking)
│   └── Data/                ← create this folder, student places PDFs here
│       ├── chapter1.pdf
│       ├── chapter2.pdf
│       ├── chapter3.pdf
│       ├── chapter4.pdf
│       └── chapter5.pdf
├── llm/
│   ├── __init__.py
│   └── inference.py
├── common/
│   ├── __init__.py
│   └── models.py
└── main.py
```

---

## Objective

Replace the RAG stub with a real ChromaDB vector database that:
- Reads all 20 Machine Learning lecture PDFs from `rag/Data/` at startup
- Extracts and chunks the text into 6-sentence segments
- Embeds and indexes all chunks into ChromaDB once at startup (persisted to `rag/chroma_db/`)
- Performs real semantic similarity search on every incoming query
- Returns the top 2 most relevant chunks as context per request
- Is thread-safe so 1000 concurrent workers can query it simultaneously

Also update `client/load_generator.py` to send real machine learning
questions instead of generic `"Query N"` strings, so retrieval is meaningful.

---

## Step 0 — Install Dependencies

```bash
pip install chromadb pypdf
pip freeze > requirements.txt
```

- `chromadb` — vector database with built-in embedding model
- `pypdf` — extracts text from PDF files page by page

---

## Step 1 — `rag/Data/` folder

The folder already exists and contains 20 Machine Learning lecture PDFs
(`MachineLearning-Lecture01.pdf` through `MachineLearning-Lecture20.pdf`).
The ingest script reads ALL `.pdf` files in this folder automatically.

---

## Files to Create / Modify

### 1. `rag/ingest.py` (NEW FILE)

This module handles PDF extraction and chunking. It is imported by `retriever.py`
and runs once at startup. It exports a single function `load_documents()`.

**Imports needed:**
- `os`
- `pypdf` — specifically `pypdf.PdfReader`

**`chunk_text(text, chunk_size=3)` helper function (private):**

Splits a long string into chunks of approximately `chunk_size` sentences each.

Implementation:
1. Split the text by `.` to get individual sentences
2. Strip whitespace from each sentence, filter out empty strings and
   sentences shorter than 20 characters (they are usually page numbers,
   headers, or artifacts)
3. Group sentences into chunks of `chunk_size` sentences each
4. Join each group with `. ` and append a `.` at the end
5. Return the list of chunk strings

```python
def chunk_text(text: str, chunk_size: int = 3) -> list[str]:
```

**`load_documents()` function (exported):**

Reads all PDF files from `rag/docs/`, extracts text, chunks it, and returns
a list of dicts ready for ChromaDB ingestion.

Implementation:
1. Build the path to `rag/docs/` relative to this file's location using
   `os.path.dirname(__file__)` so it works regardless of where the script
   is called from
2. Find all `.pdf` files in that folder using `os.listdir()`
3. For each PDF file:
   - Open with `pypdf.PdfReader`
   - Extract text from every page with `page.extract_text()`
   - Concatenate all pages into one string
   - Call `chunk_text()` on the full text
   - For each chunk, create a dict:
     ```python
     {
         "id": f"{pdf_filename}_chunk_{chunk_index}",
         "text": chunk_string,
         "source": pdf_filename
     }
     ```
4. Print progress per file: `[Ingest] chapter1.pdf — 47 chunks extracted`
5. Return the full flat list of all chunks from all PDFs

```python
def load_documents() -> list[dict]:
```

If `rag/docs/` does not exist or contains no PDFs, print a warning and
return an empty list — do not crash.

---

### 2. `rag/retriever.py` (REPLACE ENTIRELY)

**Imports needed:**
- `chromadb`
- `threading`
- `load_documents` from `rag.ingest`

**Module-level initialization (runs once at import time):**

1. Call `load_documents()` to get all chunks from the PDFs
2. Create a ChromaDB in-memory client:
   ```python
   chroma_client = chromadb.Client()
   ```
3. Create a collection named `"cse354_knowledge_base"`:
   ```python
   collection = chroma_client.create_collection(
       name="cse354_knowledge_base",
       metadata={"heuristic": "cosine"}
   )
   ```
4. If documents list is not empty, add them to the collection in a
   single batch call:
   ```python
   collection.add(
       documents=[doc["text"] for doc in documents],
       ids=[doc["id"] for doc in documents]
   )
   ```
5. Create a module-level lock:
   ```python
   _lock = threading.Lock()
   ```
6. Print startup confirmation:
   ```
   [RAG] Knowledge base ready — 183 chunks indexed from 5 PDFs
   ```
   Show the actual count of chunks loaded.

7. If documents list is empty (PDFs not found), print:
   ```
   [RAG] WARNING — No PDFs found in rag/docs/. Falling back to stub retrieval.
   ```
   Set a module-level flag `_fallback = True` so `retrieve_context()` knows
   to return a stub response instead of querying an empty collection.

**`retrieve_context(query)` function:**

- If `_fallback` is True, return `f"Relevant context for: {query}"` immediately
- Acquire `_lock`
- Query the collection:
  ```python
  results = collection.query(
      query_texts=[query],
      n_results=2
  )
  ```
- Release the lock
- Extract the two chunks from `results['documents'][0]`
- Return them joined with ` | `
- Wrap everything in try/except — on any error return
  `f"Context unavailable for: {query}"`

```python
def retrieve_context(query: str) -> str:
```

---

### 3. `client/load_generator.py` (MODIFY)

Update the query strings from generic `"Query N"` to real distributed
systems questions so retrieval returns meaningful content.

Add this list at the top of the file (after imports):

```python
SAMPLE_QUERIES = [
    "how does load balancing work in distributed systems",
    "what is fault tolerance and how do nodes recover from failure",
    "explain GPU cluster task distribution for parallel processing",
    "what is retrieval augmented generation and how does it work",
    "how does round robin scheduling distribute requests",
    "what happens when a worker node fails during processing",
    "how do vector databases store and search embeddings",
    "explain least connections load balancing strategy",
    "what is horizontal scaling in distributed systems",
    "how does parallel processing improve system throughput",
    "what is a master node and what does it control",
    "explain consistency and availability tradeoffs in distributed systems",
    "how does a message queue help with task distribution",
    "what is latency and how does it affect system performance",
    "explain the difference between synchronous and asynchronous processing",
]
```

In `simulate_user()`, replace:
```python
request = Request(id=user_id, query=f"Query {user_id}")
```
with:
```python
query = SAMPLE_QUERIES[user_id % len(SAMPLE_QUERIES)]
request = Request(id=user_id, query=query)
```

---

## Acceptance Criteria

- [ ] `pip install chromadb pypdf` succeeds
- [ ] Student places 5 PDF chapters into `rag/docs/`
- [ ] `python main.py` runs without errors
- [ ] Startup log shows `[Ingest] chapterX.pdf — N chunks extracted` for each PDF
- [ ] Startup log shows `[RAG] Knowledge base ready — N chunks indexed from 5 PDFs`
- [ ] Worker logs show different context strings per query — real retrieval is happening
- [ ] Context strings contain actual sentences from the course material
- [ ] No crashes under 1000 concurrent threads
- [ ] If `rag/docs/` is empty, system still runs using fallback stub — no crash

---

## Verification Test

Save as `test_rag.py` in the project root and run `python test_rag.py`
before running the full load test:

```python
from rag.retriever import retrieve_context

queries = [
    "how does load balancing work in distributed systems",
    "what is fault tolerance and node recovery",
    "explain GPU cluster parallel processing",
    "what is a vector database and semantic search",
    "how does round robin scheduling work",
]

print("=" * 60)
for q in queries:
    result = retrieve_context(q)
    print(f"\nQuery:   {q}")
    print(f"Context: {result[:120]}...")
print("=" * 60)
```

Each query should return a different excerpt that is topically relevant
to the question — pulled from the actual course PDF chapters.

---

## Performance Note

ChromaDB's embedding model runs on CPU and adds ~50-150ms per query
depending on chunk count. Under 1000 concurrent threads, the `_lock`
serializes ChromaDB calls — total latency per request will increase
from ~0.2s (stub) to ~0.4-0.8s (real RAG).

This latency increase is a feature, not a bug — it demonstrates that
real semantic search has measurable cost. Record stats before and after
this change and include both in your report as a before/after comparison.
This is strong evidence for the "wider reading" and "deep understanding"
criteria in the marking rubric.

---

## Do Not Change

- `common/models.py`
- `master/scheduler.py`
- `master/heartbeat.py`
- `workers/gpu_worker.py`
- `lb/load_balancer.py`
- `llm/inference.py`
- `main.py`
- Any `__init__.py` files

---

## Notes for Claude Code

- Two files to create: `rag/ingest.py` and updated `rag/retriever.py`
- One file to modify: `client/load_generator.py` (query strings only)
- Create the folder `rag/docs/` if it does not exist — but do NOT put
  any files in it, the student places their PDFs there manually
- Use `chromadb.Client()` (in-memory) NOT `chromadb.PersistentClient()`
- Use `pypdf.PdfReader` NOT the deprecated `PyPDF2`
- The fallback mode is critical — system must not crash if docs folder is empty
- Collection must be created and populated at module import time, not per request
- The `_lock` around `collection.query()` is mandatory for thread safety
- Python version is 3.9+
- chunk_size=3 sentences is the sweet spot — too large = poor retrieval precision,
  too small = chunks lose context
- IDs must be unique across all PDFs — use `f"{filename}_chunk_{i}"` format