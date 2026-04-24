import chromadb
import threading
from rag.ingest import load_documents

documents = load_documents()

chroma_client = chromadb.PersistentClient(path="rag/chroma_db")
collection = chroma_client.get_or_create_collection(
    name="cse354_knowledge_base",
    metadata={"heuristic": "cosine"}
)

_fallback = False
_lock = threading.Lock()

if collection.count() == 0:
    if documents:
        collection.add(
            documents=[doc["text"] for doc in documents],
            ids=[doc["id"] for doc in documents]
        )
        print(f"[RAG] Knowledge base ready — {len(documents)} chunks indexed from {len(set(d['source'] for d in documents))} PDFs")
    else:
        _fallback = True
        print("[RAG] WARNING — No PDFs found in rag/Data/. Falling back to stub retrieval.")
else:
    print(f"[RAG] Knowledge base loaded from disk — {collection.count()} chunks")


def retrieve_context(query: str) -> str:
    if _fallback:
        return f"Relevant context for: {query}"

    try:
        with _lock:
            results = collection.query(
                query_texts=[query],
                n_results=2
            )
        chunks = results["documents"][0]
        return " | ".join(chunks)
    except Exception:
        return f"Context unavailable for: {query}"
