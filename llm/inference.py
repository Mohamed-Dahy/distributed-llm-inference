import time
import os
import httpx

USE_REAL_LLM = os.getenv("USE_REAL_LLM", "false").lower() == "true"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

def run_llm(query: str, context: str) -> str:
    if not USE_REAL_LLM:
        return _stub_llm(query, context)
    try:
        return _ollama_llm(query, context)
    except Exception as e:
        print(f"[LLM] Ollama failed: {e}, falling back to stub")
        return _stub_llm(query, context)

def _stub_llm(query: str, context: str) -> str:
    time.sleep(0.2)
    return f"LLM Answer to '{query}' using [{context}]"

def _ollama_llm(query: str, context: str) -> str:
    prompt = (
        f"Use the context below to answer the question concisely in 2-3 sentences.\n\n"
        f"Context: {context}\n\n"
        f"Question: {query}\n\n"
        f"Answer:"
    )
    response = httpx.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 150,
            },
        },
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["response"].strip()
